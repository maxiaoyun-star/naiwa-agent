"""首页。

信息层级：先告诉你「现在能不能用」（模型状态），再给入口（聊 / 查 / 我的）。
纯白背景上只有卡片描边和文字，靠间距分组，不靠色块。
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from .. import config
from . import theme as T
from .widgets import Body, Card, H1, H2, Muted, PrimaryButton, Screen, StatusPill, fit_height


class TapCard(Card):
    """整块可点的卡片。"""

    def __init__(self, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.on_tap = on_tap

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.on_tap is not None:
            self.on_tap()
            return True
        return super().on_touch_down(touch)


class Tile(TapCard):
    def __init__(self, title: str, desc: str, on_tap=None, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(96))
        kwargs.setdefault("padding", [dp(14), dp(12)])
        super().__init__(on_tap=on_tap, **kwargs)
        self.add_widget(H2(title))
        self.add_widget(Muted(desc, size_hint_y=None, height=dp(20)))
        self.add_widget(Widget())


class HomeScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app

        self.add_widget(self._header())
        self.add_widget(Widget(size_hint_y=None, height=dp(4)))
        self.add_widget(self._status_card())
        self.add_widget(Widget(size_hint_y=None, height=dp(10)))
        self.add_widget(self._ask_row())
        self.add_widget(Widget(size_hint_y=None, height=dp(14)))
        self.add_widget(self._tiles())
        self.add_widget(Widget())

        footer = Muted(f"{config.APP_NAME} v{config.VERSION} · {config.BUILD_STAGE}", halign="center")
        footer.size_hint_y = None
        footer.height = dp(26)
        self.add_widget(footer)

        Clock.schedule_once(self._refresh, 0.1)

    # ------------------------------------------------------------------ 结构
    def _header(self) -> BoxLayout:
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(90), padding=[0, dp(4)])
        box.add_widget(H1(config.APP_NAME))
        box.add_widget(Muted("长春理工大学 · 校园智能体 · 模型跑在手机上"))
        return box

    def _status_card(self) -> Card:
        card = Card()  # 高度跟着内容走
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22))
        caption = Muted("模型状态", size_hint_x=None, width=dp(60))
        caption.valign = "middle"
        row.add_widget(caption)
        row.add_widget(Widget())
        self.pill = StatusPill("检查中")
        row.add_widget(self.pill)
        card.add_widget(row)

        self.status_text = fit_height(Body("正在检查本地模型…", font_size=sp(14)))
        card.add_widget(self.status_text)

        self.status_action = PrimaryButton("加载本地模型", height=dp(36))
        self.status_action.font_size = sp(14)
        self.status_action.bind(on_release=self._on_action)
        card.add_widget(self.status_action)
        return card

    def _ask_row(self) -> TapCard:
        card = TapCard(
            on_tap=lambda: self.app.go("chat"),
            size_hint_y=None,
            height=dp(56),
            padding=[dp(16), dp(6)],
        )
        hint = Body("问点什么…… 课表、考试、办事流程", color=T.FAINT, font_size=sp(15))
        hint.valign = "middle"
        card.add_widget(hint)
        return card

    def _tiles(self) -> GridLayout:
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(202))
        grid.add_widget(Tile("查课表", "今天 / 本周 / 某一天", lambda: self.app.go("schedule")))
        grid.add_widget(Tile("查考试", "时间、考场、座位", self._open_exams))
        grid.add_widget(Tile("学校账号", "统一身份认证登录", lambda: self.app.go("login")))
        grid.add_widget(Tile("设置", "模型、API、教务接口", lambda: self.app.go("settings")))
        return grid

    # ------------------------------------------------------------------ 行为
    def _open_exams(self) -> None:
        target = self.app.sm.get_screen("schedule")
        target.tab_index = 1
        self.app.go("schedule")

    def _on_action(self, *_args) -> None:
        if self.app.model_manager.existing() is None:
            self.app.go("settings")
            return
        self.app.load_local_model()

    def _refresh(self, _dt=None) -> None:
        label, detail = self.app.llm.status()
        self.pill.text = label
        self.pill._resize()  # noqa: SLF001 - 由 text 变化驱动宽度
        ready = self.app.llm.local_ready()
        if ready:
            path = self.app.model_manager.existing()
            self.status_text.text = f"本地模型已加载：{path.name}" if path else "本地模型已加载"
            self.status_action.text = "已就绪"
            self.status_action.disabled = True
        elif self.app.model_manager.existing() is None:
            self.status_text.text = "还没安装本地模型，点下面按钮下载或导入"
            self.status_action.text = "去安装模型"
            self.status_action.disabled = False
        else:
            self.status_text.text = detail
            self.status_action.text = "加载本地模型"
            self.status_action.disabled = False

    def on_pre_enter(self, *_args) -> None:
        Clock.schedule_once(self._refresh, 0.05)


__all__ = ["HomeScreen", "TapCard", "Tile"]
