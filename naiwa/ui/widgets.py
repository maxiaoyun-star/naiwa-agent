"""纯白 UI 组件库。

全部手绘，不依赖 KivyMD。每个组件的约束是：白底、1px 浅灰描边、16px 圆角、
近黑强调色，字号遵循 12 / 14 / 16 / 20 / 26 五档。
"""

from __future__ import annotations

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen as _KivyScreen
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from . import theme as T


# ------------------------------------------------------------------ 基础图形
def rounded_bg(widget: Widget, color, radius: float, border_color=None) -> tuple:
    """给控件加一个圆角背景（可选描边）。

    返回 ``(rect, fill_color, border_color)``，其中后两个是 Color 指令，
    需要动态改色（比如按钮按下、Tab 高亮）时直接改它们的 ``rgba``。
    """
    with widget.canvas.before:
        color_instr = Color(*color)
        rect = RoundedRectangle(radius=[radius])
    border = None
    line_color = None
    if border_color is not None:
        with widget.canvas.before:
            line_color = Color(*border_color)
            border = Line(rounded_rectangle=(0, 0, 0, 0, radius), width=1)

    def _sync(*_args) -> None:
        rect.pos = widget.pos
        rect.size = widget.size
        if border is not None:
            border.rounded_rectangle = (widget.x, widget.y, widget.width, widget.height, radius)

    widget.bind(pos=_sync, size=_sync)
    _sync()
    return rect, color_instr, line_color


# ------------------------------------------------------------------ 文字
def _text(**kwargs):
    kwargs.setdefault("font_name", T.FONT_REGULAR)
    kwargs.setdefault("color", T.TEXT)
    return kwargs


class H1(Label):
    def __init__(self, text: str = "", **kwargs):
        kwargs.update(_text(font_size=sp(26), bold=True, size_hint_y=None))
        super().__init__(text=text, **kwargs)
        self.height = dp(34)


class H2(Label):
    def __init__(self, text: str = "", **kwargs):
        kwargs.update(_text(font_size=sp(20), bold=True, size_hint_y=None))
        super().__init__(text=text, **kwargs)
        self.height = dp(28)


class Body(Label):
    def __init__(self, text: str = "", **kwargs):
        kwargs.update(_text(font_size=sp(15)))
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "top")
        super().__init__(text=text, **kwargs)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)))


class Muted(Body):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("color", T.MUTED)
        kwargs["font_size"] = kwargs.get("font_size", sp(13))
        super().__init__(text=text, **kwargs)


class Divider(Widget):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(1))
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(*T.LINE)
            self._line = Line(width=1)

        def _sync(*_args):
            self._line.points = [self.x, self.center_y, self.right, self.center_y]

        self.bind(pos=_sync, size=_sync)


# ------------------------------------------------------------------ 容器
class Card(BoxLayout):
    """白底圆角卡片。

    传了 ``height`` 就用固定高度；没传就跟着内容高度走（``minimum_height``），
    这样表单类卡片不用手工算高度。
    """

    def __init__(self, radius: float | None = None, bg=None, border: bool = True, **kwargs):
        explicit_height = "height" in kwargs
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [T.PAD, T.PAD])
        kwargs.setdefault("spacing", T.PAD_S)
        kwargs.setdefault("size_hint_y", None)
        super().__init__(**kwargs)
        if not explicit_height and self.size_hint_y is None:
            self.bind(minimum_height=self.setter("height"))
        rounded_bg(
            self,
            bg if bg is not None else T.SURFACE,
            radius if radius is not None else T.RADIUS,
            border_color=T.LINE if border else None,
        )


class Screen(_KivyScreen):
    """统一的白底页面容器。

    必须是真正的 ``kivy.uix.screenmanager.Screen``（ScreenManager 只接受 Screen 实例，
    并且依赖它的 on_pre_enter / on_enter 事件和 ``manager`` 属性），
    所以这里继承 Screen，内部再挂一个纵向 BoxLayout 当内容容器，
    并把 ``add_widget`` 转发进去 —— 页面代码就还能像用 BoxLayout 一样写。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        inset_top, inset_bottom = 0.0, 0.0
        try:
            from .. import platform_compat

            inset_top, inset_bottom = platform_compat.insets_dp()
        except Exception:  # noqa: BLE001
            pass

        self._body = BoxLayout(
            orientation="vertical",
            # Android 15+ 强制 edge-to-edge，顶部/底部要让出状态栏与导航栏
            padding=[T.PAD, T.PAD + dp(inset_top), T.PAD, T.PAD + dp(inset_bottom)],
            spacing=T.PAD_S,
        )
        with self._body.canvas.before:
            self._bg = Color(*T.BG)
            self._rect = RoundedRectangle(radius=[0])

        def _sync(*_args):
            self._rect.pos = self._body.pos
            self._rect.size = self._body.size

        self._body.bind(pos=_sync, size=_sync)
        _KivyScreen.add_widget(self, self._body)

    # 页面里的控件统一进 body，保持纵向排列语义
    def add_widget(self, widget, *args, **kwargs):
        body = getattr(self, "_body", None)
        if body is None or widget is body:
            return _KivyScreen.add_widget(self, widget, *args, **kwargs)
        return body.add_widget(widget, *args, **kwargs)

    def clear_widgets(self, *args, **kwargs):
        body = getattr(self, "_body", None)
        if body is None:
            return _KivyScreen.clear_widgets(self, *args, **kwargs)
        return body.clear_widgets(*args, **kwargs)


class TopBar(BoxLayout):
    """顶部导航：返回 + 标题 + 右侧插槽。"""

    def __init__(self, title: str = "", on_back=None, right_width: float = 36, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        kwargs.setdefault("padding", [0, 0, 0, 0])
        kwargs.setdefault("spacing", dp(6))
        super().__init__(**kwargs)

        self.back = Button(
            text="‹",
            font_name=T.FONT_REGULAR,
            font_size=sp(30),
            color=T.TEXT,
            size_hint=(None, 1),
            width=dp(36) if on_back else 0,
            background_normal="",
            background_color=(0, 0, 0, 0),
        )
        if on_back:
            self.back.bind(on_release=lambda *_: on_back())
        self.add_widget(self.back)

        self.title = Label(
            text=title,
            font_name=T.FONT_REGULAR,
            font_size=sp(19),
            bold=True,
            color=T.TEXT,
            halign="left",
            valign="middle",
        )
        self.title.bind(size=lambda *_: setattr(self.title, "text_size", self.title.size))
        self.add_widget(self.title)

        self.slot = BoxLayout(
            orientation="horizontal",
            size_hint=(None, 1),
            width=dp(right_width),
            spacing=dp(4),
        )
        self.add_widget(self.slot)


# ------------------------------------------------------------------ 按钮
class PrimaryButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(50))
        super().__init__(text=text, **kwargs)
        self.font_name = T.FONT_REGULAR
        self.font_size = sp(16)
        self.bold = True
        self.color = T.ACCENT_TEXT
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        self.background_down = ""
        with self.canvas.before:
            self._color = Color(*T.ACCENT)
            self._rect = RoundedRectangle(radius=[T.RADIUS_S])

        def _sync(*_args):
            self._rect.pos = self.pos
            self._rect.size = self.size

        self.bind(pos=_sync, size=_sync, state=self._on_state)

    def _on_state(self, *_args):
        self._color.rgba = (0.28, 0.30, 0.33, 1) if self.state == "down" else T.ACCENT


class GhostButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(50))
        super().__init__(text=text, **kwargs)
        self.font_name = T.FONT_REGULAR
        self.font_size = sp(15)
        self.color = T.TEXT
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        rounded_bg(self, T.SURFACE, T.RADIUS_S, border_color=T.LINE)


class Chip(Button):
    """快捷问题 / Tab 小胶囊。"""

    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        super().__init__(text=text, **kwargs)
        self.font_name = T.FONT_REGULAR
        self.font_size = sp(13)
        self.color = T.TEXT
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        _rect, self._fill, _line = rounded_bg(self, T.SURFACE_ALT, T.RADIUS_S)
        self.bind(texture_size=self._resize)
        self.height = dp(34)

    def _resize(self, *_args):
        self.width = max(dp(56), self.texture_size[0] + dp(26))
        self.height = dp(34)

    def set_active(self, active: bool) -> None:
        self._fill.rgba = T.ACCENT if active else T.SURFACE_ALT
        self.color = T.ACCENT_TEXT if active else T.TEXT


# ------------------------------------------------------------------ 输入
class Field(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("write_tab", False)
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(48))
        super().__init__(**kwargs)
        self.font_name = T.FONT_REGULAR
        self.font_size = sp(16)
        self.background_normal = ""
        self.background_active = ""
        self.background_color = (0, 0, 0, 0)
        self.foreground_color = T.TEXT
        self.cursor_color = T.TEXT
        self.hint_text_color = T.FAINT
        self.padding = [dp(4), dp(14), dp(4), dp(10)]
        with self.canvas.after:
            self._line_color = Color(*T.LINE)
            self._line = Line(width=1)

        def _sync(*_args):
            self._line.points = [self.x, self.y, self.right, self.y]

        self.bind(pos=_sync, size=_sync, focus=self._on_focus)

    def _on_focus(self, _inst, value):
        self._line_color.rgba = T.ACCENT if value else T.LINE


class ChatBubble(BoxLayout):
    """对话气泡：自己的在右（近黑），奶娃的在左（白底描边）。"""

    def __init__(self, text: str, mine: bool = False, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", [0, dp(3), 0, dp(3)])
        super().__init__(**kwargs)

        card = BoxLayout(
            orientation="vertical",
            size_hint=(0.82, None),
            padding=[dp(14), dp(11), dp(14), dp(11)],
        )
        rounded_bg(
            card,
            T.ACCENT if mine else T.SURFACE,
            T.RADIUS,
            border_color=None if mine else T.LINE,
        )
        self.label = Body(
            text=text,
            color=T.ACCENT_TEXT if mine else T.TEXT,
            font_size=sp(15),
        )
        card.add_widget(self.label)
        card.bind(minimum_height=card.setter("height"))
        self.label.bind(texture_size=self._sync_height)

        if mine:
            self.add_widget(Widget(size_hint_x=0.18))
            self.add_widget(card)
        else:
            self.add_widget(card)
            self.add_widget(Widget(size_hint_x=0.18))

        self._card = card
        self._sync_height()

    def _sync_height(self, *_args):
        self.label.text_size = (self.label.width, None)
        self._card.height = self.label.texture_size[1] + dp(22)
        self.height = self._card.height + dp(6)

    def set_text(self, text: str) -> None:
        self.label.text = text
        self._sync_height()


class StatusPill(Label):
    """右上角状态：本地推理 / API / 离线。"""

    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("font_size", sp(11))
        super().__init__(text=text, **kwargs)
        self.font_name = T.FONT_REGULAR
        self.color = T.MUTED
        self.padding = [dp(10), dp(4)]
        self.height = dp(24)
        rounded_bg(self, T.SURFACE_ALT, dp(12))
        self.bind(texture_size=self._resize)

    def _resize(self, *_args):
        self.width = self.texture_size[0] + dp(20)


class Empty(Label):
    """空状态提示。"""

    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("font_size", sp(13))
        super().__init__(text=text, **kwargs)
        self.font_name = T.FONT_REGULAR
        self.color = T.FAINT
        self.halign = "center"
        self.valign = "middle"
        self.bind(size=lambda *_: setattr(self, "text_size", self.size))


def spacer(height: float = 8) -> Widget:
    return Widget(size_hint_y=None, height=dp(height))


def hbox(*children, **kwargs) -> BoxLayout:
    kwargs.setdefault("orientation", "horizontal")
    kwargs.setdefault("size_hint_y", None)
    kwargs.setdefault("spacing", T.PAD_S)
    box = BoxLayout(**kwargs)
    for child in children:
        box.add_widget(child)
    return box


__all__ = [
    "Card", "Screen", "TopBar", "PrimaryButton", "GhostButton", "Chip",
    "Field", "ChatBubble", "StatusPill", "Empty", "Divider",
    "H1", "H2", "Body", "Muted", "spacer", "hbox", "rounded_bg",
]
