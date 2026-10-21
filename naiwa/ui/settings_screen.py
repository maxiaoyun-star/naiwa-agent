"""设置页：模型、推理模式、云端 API、教务接口、账号。

刻意保持表单化：每一项都是「标题 + 说明 + 输入 + 保存」，因为这里是给用户
一次性配置好就再也不打开的地方，不需要花哨交互。
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from .. import config, defaults
from ..llm.remote import PROVIDER_PRESETS
from ..llm.router import MODE_AUTO, MODE_LOCAL, MODE_REMOTE
from . import theme as T
from .widgets import (
    Body,
    Card,
    Chip,
    Field,
    GhostButton,
    H2,
    Muted,
    PrimaryButton,
    Screen,
    TopBar,
    fit_height,
)

MODES = ((MODE_AUTO, "自动"), (MODE_LOCAL, "仅本地"), (MODE_REMOTE, "仅云端"))


class SettingsScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._fields: dict[str, Field] = {}
        self._chips: dict[str, Chip] = {}
        self._downloading = False

        self.add_widget(TopBar("设置", on_back=app.back))

        scroll = ScrollView(do_scroll_x=False, bar_width=0)
        self.content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=[dp(1), dp(2), dp(1), dp(24)],
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        self.add_widget(scroll)

        self._build_model()
        self._build_mode()
        self._build_remote()
        self._build_portal()
        self._build_account()
        self._build_about()

    # ------------------------------------------------------------------ 组件
    def _section(self, title: str) -> Card:
        card = Card(size_hint_y=None, spacing=dp(8), padding=[dp(14), dp(14)])
        card.add_widget(H2(title))
        self.content.add_widget(card)
        return card

    def _hint(self, card: Card, text: str) -> Muted:
        label = Muted(text)
        label.size_hint_y = None
        label.bind(width=lambda *_: setattr(label, "text_size", (label.width, None)))
        label.bind(texture_size=lambda *_: setattr(label, "height", label.texture_size[1] + dp(4)))
        card.add_widget(label)
        return label

    def _field(self, card: Card, key: str, hint: str, value: str = "", password: bool = False) -> Field:
        field = Field(hint_text=hint, text=value, password=password, height=dp(44))
        card.add_widget(field)
        self._fields[key] = field
        return field

    def _chip_row(self, card: Card, items, group: str) -> dict[str, Chip]:
        # 平台可能有 5 个以上，横向滚动比换行更省纵向空间
        scroll = ScrollView(
            size_hint_y=None,
            height=dp(38),
            do_scroll_x=True,
            do_scroll_y=False,
            bar_width=0,
        )
        row = BoxLayout(orientation="horizontal", size_hint_x=None, spacing=dp(8))
        row.bind(minimum_width=row.setter("width"))
        chips = {}
        for key, label in items:
            chip = Chip(label)
            chip.bind(on_release=lambda inst, k=key: self._select(group, k))
            chips[key] = chip
            row.add_widget(chip)
        scroll.add_widget(row)
        card.add_widget(scroll)
        self._chips[group] = chips
        return chips

    def _select(self, group: str, key: str) -> None:
        for chip_key, chip in self._chips.get(group, {}).items():
            chip.set_active(chip_key == key)
        if group == "mode":
            self.app.settings.set("llm_mode", key)
            self.app.settings.save()
            self.app.llm.reload()
            self._say(f"已切换到「{dict(MODES)[key]}」模式")
        elif group == "provider":
            self.app.settings.set("remote_provider", key)
            preset = PROVIDER_PRESETS[key]
            self._fields["remote_base"].text = preset["base"]
            self._fields["remote_model"].text = preset["model"]
            self._say(preset["hint"])

    # ------------------------------------------------------------------ 模型
    def _build_model(self) -> None:
        card = self._section("本地模型")
        self.model_status = fit_height(Body("检查中…", font_size=sp(14)))
        card.add_widget(self.model_status)

        self._field(card, "model_url", "模型下载直链（https://…）", self.app.settings.get("model_url", ""))
        self.download_progress = Muted("", size_hint_y=None, height=dp(18))
        card.add_widget(self.download_progress)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        self.download_button = PrimaryButton("下载模型", height=dp(44))
        self.download_button.font_size = sp(14)
        self.download_button.bind(on_release=lambda *_: self.download_model())
        row.add_widget(self.download_button)

        reload_button = GhostButton("重新加载", height=dp(44))
        reload_button.bind(on_release=lambda *_: self.app.load_local_model())
        row.add_widget(reload_button)
        card.add_widget(row)

        self._hint(
            card,
            f"文件名必须是 {defaults.MODEL_FILENAME}。\n"
            f"也可以放到这个目录，App 启动会自动识别：\n{config.models_dir()}",
        )

    def download_model(self) -> None:
        if self._downloading:
            return
        url = (self._fields["model_url"].text or "").strip()
        if url:
            self.app.settings.set("model_url", url)
        if not url and not defaults.DEFAULT_MODEL_URL:
            self._say("先填下载地址")
            return

        self._downloading = True
        self.download_button.disabled = True
        self.download_progress.text = "开始下载…"

        def progress(done: int, total: int) -> None:
            if total > 0:
                percent = done * 100 // total
                text = f"{percent}% · {config.human_size(done)} / {config.human_size(total)}"
            else:
                text = config.human_size(done)
            Clock.schedule_once(lambda _dt: setattr(self.download_progress, "text", text), 0)

        def work():
            return self.app.model_manager.download(url or None, progress)

        def done(path) -> None:
            self._downloading = False
            self.download_button.disabled = False
            self.download_progress.text = f"下载完成：{path.name}"
            self._refresh()
            self.app.load_local_model()

        def failed(exc: Exception) -> None:
            self._downloading = False
            self.download_button.disabled = False
            self.download_progress.text = f"下载失败：{exc}"

        self.app.run_bg(work, done, failed)

    # ------------------------------------------------------------------ 模式
    def _build_mode(self) -> None:
        card = self._section("推理模式")
        self._chip_row(card, MODES, "mode")
        self._hint(card, "自动 = 有本地模型就用本地，失败再走云端。\n仅云端 = 完全不加载本地模型。")

    # ------------------------------------------------------------------ 云端
    def _build_remote(self) -> None:
        card = self._section("云端模型（可选）")
        items = [(key, preset["label"]) for key, preset in PROVIDER_PRESETS.items()]
        self._chip_row(card, items, "provider")
        self._field(card, "remote_base", "接口地址", self.app.settings.get("remote_base", ""))
        self._field(card, "remote_model", "模型名", self.app.settings.get("remote_model", ""))
        self._field(card, "remote_key", "API Key", self.app.secrets.get("remote_api_key", ""), password=True)

        save = PrimaryButton("保存云端配置", height=dp(42))
        save.font_size = sp(14)
        save.bind(on_release=lambda *_: self.save_remote())
        card.add_widget(save)
        self._hint(card, "只支持国内合规平台。本地模型能跑就不用配这里。")

    def save_remote(self) -> None:
        self.app.settings.set("remote_base", (self._fields["remote_base"].text or "").strip())
        self.app.settings.set("remote_model", (self._fields["remote_model"].text or "").strip())
        self.app.settings.save()
        key = (self._fields["remote_key"].text or "").strip()
        if key:
            self.app.secrets.set("remote_api_key", key)
        self.app.llm.reload()
        self._say("云端配置已保存")

    # ------------------------------------------------------------------ 教务接口
    def _build_portal(self) -> None:
        card = self._section("教务接口")
        self._hint(
            card,
            "门户的课表/考试接口地址没有公开文档，需要用电脑登录后按 F12 抓一次，"
            "把 JSON 接口地址填到这里（详见 docs/CAS接入说明.md）。",
        )
        self._field(card, "portal_schedule", "课表接口地址", self.app.settings.get("portal_api_schedule", ""))
        self._field(card, "portal_exams", "考试接口地址", self.app.settings.get("portal_api_exams", ""))
        self._field(card, "portal_profile", "个人信息接口（可选）", self.app.settings.get("portal_api_profile", ""))

        save = PrimaryButton("保存接口配置", height=dp(42))
        save.font_size = sp(14)
        save.bind(on_release=lambda *_: self.save_portal())
        card.add_widget(save)

    def save_portal(self) -> None:
        mapping = {
            "portal_schedule": "portal_api_schedule",
            "portal_exams": "portal_api_exams",
            "portal_profile": "portal_api_profile",
        }
        for field_key, setting_key in mapping.items():
            self.app.settings.set(setting_key, (self._fields[field_key].text or "").strip())
        self.app.settings.save()
        self._say("教务接口已保存")

    # ------------------------------------------------------------------ 账号
    def _build_account(self) -> None:
        card = self._section("学校账号")
        self.account_label = Body("未登录", font_size=sp(14))
        self.account_label.size_hint_y = None
        self.account_label.height = dp(28)
        card.add_widget(self.account_label)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        login_button = GhostButton("去登录", height=dp(44))
        login_button.bind(on_release=lambda *_: self.app.go("login"))
        row.add_widget(login_button)
        logout_button = GhostButton("退出登录", height=dp(44))
        logout_button.bind(on_release=lambda *_: self.logout())
        row.add_widget(logout_button)
        card.add_widget(row)

    def logout(self) -> None:
        self.app.campus.logout()
        self.app.on_session_changed()
        self._say("已退出登录，本地凭证已清除")

    # ------------------------------------------------------------------ 关于
    def _build_about(self) -> None:
        card = self._section("关于")
        self._hint(card, f"{config.APP_NAME} v{config.VERSION} · {config.BUILD_STAGE}")
        self._hint(card, "本地推理：llama.cpp + Qwen GGUF；不联网也能对话，数据不出手机。")

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        clear_chat = GhostButton("清空对话", height=dp(44))
        clear_chat.bind(on_release=lambda *_: self.app.clear_chat())
        row.add_widget(clear_chat)
        clear_all = GhostButton("清除全部数据", height=dp(44))
        clear_all.bind(on_release=lambda *_: self.app.clear_all_data())
        row.add_widget(clear_all)
        card.add_widget(row)

    # ------------------------------------------------------------------ 状态
    def _say(self, text: str) -> None:
        if hasattr(self, "status_line"):
            self.status_line.text = text
        else:
            line = Muted("", size_hint_y=None, height=dp(22))
            line.text = text
            self.content.add_widget(line)
            self.status_line = line

    def _refresh(self) -> None:
        installed, detail = self.app.model_manager.status()
        if installed:
            self.model_status.text = f"已安装 · {detail}"
        else:
            self.model_status.text = "还没安装模型文件：下载，或用数据线放到下面的目录再点「重新加载」"

        mode = self.app.settings.get("llm_mode", MODE_AUTO)
        for key, chip in self._chips.get("mode", {}).items():
            chip.set_active(key == mode)

        provider = self.app.settings.get("remote_provider", defaults.DEFAULT_REMOTE_PROVIDER)
        for key, chip in self._chips.get("provider", {}).items():
            chip.set_active(key == provider)

        if not self._fields["remote_base"].text:
            preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["zhipu"])
            self._fields["remote_base"].text = preset["base"]
            self._fields["remote_model"].text = self.app.settings.get("remote_model") or preset["model"]

        state = self.app.campus.state
        if state.logged_in:
            self.account_label.text = f"已登录：{state.username} {state.name}".strip()
        else:
            self.account_label.text = "未登录"

    def on_pre_enter(self, *_args) -> None:
        self._refresh()


__all__ = ["SettingsScreen"]
