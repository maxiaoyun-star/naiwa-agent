"""对话页：流式输出 + 快捷问题。

线程模型：推理在后台线程跑，token 通过 ``Clock.schedule_once`` 回到主线程刷新 Label。
Kivy 的 UI 只能主线程碰，这一点踩过坑就记住了。
"""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from ..agent.runtime import QUICK_PROMPTS, Reply
from ..llm.prompt import offline_reply
from . import theme as T
from .widgets import ChatBubble, Chip, Field, Muted, PrimaryButton, Screen, StatusPill, TopBar


class ChatScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._busy = False
        self._acc: list[str] = []
        self._bubble: ChatBubble | None = None

        bar = TopBar("对话", on_back=app.back, right_width=dp(72))
        self.pill = StatusPill("离线")
        bar.slot.add_widget(self.pill)
        self.add_widget(bar)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=0)
        # 用 GridLayout 而不是 BoxLayout：BoxLayout 纵向时会把子控件贴到底部，
        # 消息少的时候气泡会沉在屏幕下沿；GridLayout 是从上往下排的。
        self.list = GridLayout(
            cols=1,
            size_hint_y=None,
            spacing=dp(2),
            padding=[dp(2), dp(6)],
        )
        # 消息少的时候让列表填满视口，否则 ScrollView 会把内容放在底部
        self.list.bind(minimum_height=self._sync_list_height)
        self.scroll.bind(height=self._sync_list_height)
        self.scroll.add_widget(self.list)
        self.add_widget(self.scroll)

        self.add_widget(self._chips())

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))
        self.input = Field(hint_text="问点什么…", height=dp(44))
        self.input.bind(on_text_validate=self._on_enter)
        row.add_widget(self.input)
        self.send_button = PrimaryButton("发送", size_hint=(None, 1), width=dp(66), height=dp(44))
        self.send_button.font_size = sp(15)
        self.send_button.bind(on_release=self._on_send)
        row.add_widget(self.send_button)
        self.add_widget(row)

    # ------------------------------------------------------------------ 结构
    def _chips(self) -> ScrollView:
        scroll = ScrollView(
            size_hint_y=None,
            height=dp(44),
            do_scroll_x=True,
            do_scroll_y=False,
            bar_width=0,
        )
        box = BoxLayout(orientation="horizontal", size_hint_x=None, spacing=dp(8), padding=[0, dp(6)])
        box.bind(minimum_width=box.setter("width"))
        for prompt in QUICK_PROMPTS:
            chip = Chip(prompt)
            chip.bind(on_release=lambda inst: self.send(inst.text))
            box.add_widget(chip)
        scroll.add_widget(box)
        return scroll

    # ------------------------------------------------------------------ 消息
    def add_bubble(self, text: str, mine: bool = False) -> ChatBubble:
        bubble = ChatBubble(text, mine=mine)
        self.list.add_widget(bubble)
        self._scroll_bottom()
        return bubble

    def _scroll_bottom(self) -> None:
        Clock.schedule_once(lambda _dt: setattr(self.scroll, "scroll_y", 0), 0.06)

    def _sync_list_height(self, *_args) -> None:
        try:
            self.list.height = max(self.list.minimum_height, self.scroll.height)
        except Exception:  # noqa: BLE001 - 布局计算期间属性可能还没准备好
            pass

    def _on_enter(self, _inst) -> None:
        self.send()

    def _on_send(self, *_args) -> None:
        self.send()

    # ------------------------------------------------------------------ 发送
    def send(self, text: str | None = None) -> None:
        content = (text if text is not None else self.input.text or "").strip()
        if not content:
            return
        if self._busy:
            self._bubble = None
            return
        self.input.text = ""
        self.add_bubble(content, mine=True)
        self._busy = True
        self.send_button.disabled = True
        self._acc = []
        self._bubble = self.add_bubble("…", mine=False)

        def on_token(piece: str) -> None:
            Clock.schedule_once(lambda _dt: self._stream(piece), 0)

        def work() -> None:
            try:
                reply = self.app.runtime.answer(content, on_token=on_token)
            except Exception as exc:  # noqa: BLE001 - 任何异常都要变成一句话，而不是闪退
                reply = Reply(offline_reply("", content) + f"\n（{exc}）", source="template")
            Clock.schedule_once(lambda _dt: self._finish(reply), 0)

        threading.Thread(target=work, daemon=True).start()

    def _stream(self, piece: str) -> None:
        if self._bubble is None:
            return
        self._acc.append(piece)
        self._bubble.set_text("".join(self._acc))
        self._scroll_bottom()

    def _finish(self, reply: Reply) -> None:
        final = (reply.text or "").strip()
        if self._bubble is not None:
            if final and final != "".join(self._acc).strip():
                self._bubble.set_text(final)
            elif not final:
                self.list.remove_widget(self._bubble)
        self._bubble = None
        self._busy = False
        self.send_button.disabled = False
        self._scroll_bottom()

        if reply.action:
            self._handle_action(reply.action)

    def _handle_action(self, action: str) -> None:
        if action == "open_login":
            self.add_bubble("点右上角「我的」可以登录，或者直接说「登录」。", mine=False)
        elif action == "open_endpoints":
            self.app.go("settings")

    # ------------------------------------------------------------------ 生命周期
    def on_pre_enter(self, *_args) -> None:
        label, _detail = self.app.llm.status()
        self.pill.text = label
        self.pill._resize()  # noqa: SLF001
        if not self.list.children:
            self.add_bubble(
                "你好，我是奶娃。课表、考试、校园办事都能问我；"
                "本地模型装好后断网也能聊。",
                mine=False,
            )

    def clear(self) -> None:
        self.list.clear_widgets()
        self.app.memory.clear()
        self.add_bubble("清空了，重新开始吧。", mine=False)


__all__ = ["ChatScreen"]
