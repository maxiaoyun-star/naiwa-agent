"""统一身份认证登录页。

界面刻意做得「不自动化」：验证码必须人眼看图输入。学校这套 CAS 带图形验证码，
自动识别既不可靠也容易被判定为异常行为 —— 让人输一次，比写个 OCR 稳妥得多。
"""

from __future__ import annotations

import io

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from ..campus.cas import CasError, LoginResult
from . import theme as T
from .widgets import Body, Card, Field, GhostButton, Muted, PrimaryButton, Screen, TopBar


class CaptchaImage(Widget):
    """把 CAS 返回的 PNG 直接贴上去，点一下换一张。"""

    def __init__(self, on_tap=None, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(110), dp(44)))
        super().__init__(**kwargs)
        self.on_tap = on_tap
        self._texture = None
        with self.canvas:
            self._bg = Color(*T.SURFACE_ALT)
            self._rect = Rectangle()
            self._line_color = Color(*T.LINE)
            self._line = Line(width=1)

        def _sync(*_args):
            self._rect.pos = self.pos
            self._rect.size = self.size
            self._line.rectangle = (self.x, self.y, self.width, self.height)

        self.bind(pos=_sync, size=_sync)

    def set_png(self, data: bytes) -> None:
        try:
            image = CoreImage(io.BytesIO(data), ext="png")
            self._texture = image.texture
            self._rect.texture = self._texture
        except Exception:  # noqa: BLE001 - 图坏了不该崩，重取一张即可
            self._texture = None

    def placeholder(self) -> None:
        self._texture = None
        self._rect.texture = None

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.on_tap is not None:
            self.on_tap()
            return True
        return super().on_touch_down(touch)


class LoginScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._loading = False

        self.add_widget(TopBar("登录学校账号", on_back=app.back))

        intro = Muted(
            "用一卡通号和统一身份认证密码登录。登录后 App 只保存会话凭证，"
            "默认不保存密码。",
            size_hint_y=None,
        )
        intro.bind(width=lambda *_: setattr(intro, "text_size", (intro.width, None)))
        intro.bind(texture_size=lambda *_: setattr(intro, "height", intro.texture_size[1] + dp(6)))
        self.add_widget(intro)

        card = Card(size_hint_y=None, height=dp(266), spacing=dp(6))
        self.username = Field(hint_text="一卡通号 / 学号", height=dp(44))
        self.password = Field(hint_text="密码", password=True, height=dp(44))
        card.add_widget(self.username)
        card.add_widget(self.password)

        captcha_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        self.captcha = Field(hint_text="验证码", height=dp(44))
        captcha_row.add_widget(self.captcha)
        self.captcha_image = CaptchaImage(on_tap=self.reload_captcha)
        captcha_row.add_widget(self.captcha_image)
        card.add_widget(captcha_row)

        self.remember = Muted("记住密码：关（推荐）", size_hint_y=None, height=dp(24))
        self.remember.bind(on_touch_down=self._toggle_remember)
        card.add_widget(self.remember)

        self.login_button = PrimaryButton("登录")
        self.login_button.bind(on_release=lambda *_: self.submit())
        card.add_widget(self.login_button)
        self.add_widget(card)

        self.reload_button = GhostButton("换一张验证码", height=dp(44))
        self.reload_button.bind(on_release=lambda *_: self.reload_captcha())
        self.add_widget(self.reload_button)

        self.status = Muted("", size_hint_y=None, height=dp(40))
        self.status.text_size = (dp(300), None)
        self.add_widget(self.status)
        self.add_widget(Widget())

        self._apply_remember_ui()

    # ------------------------------------------------------------------ 交互
    def _toggle_remember(self, _inst, touch):
        if not self.remember.collide_point(*touch.pos):
            return False
        value = not bool(self.app.settings.get("cas_save_password", False))
        self.app.settings.set("cas_save_password", value)
        self.app.settings.save()
        self._apply_remember_ui()
        return True

    def _apply_remember_ui(self) -> None:
        value = bool(self.app.settings.get("cas_save_password", False))
        self.remember.text = "记住密码：开（方便，但密码会加密存在手机上）" if value else "记住密码：关（推荐）"

    def on_pre_enter(self, *_args) -> None:
        username = self.app.settings.get("cas_username", "")
        if username and not self.username.text:
            self.username.text = username
        if self.app.campus.state.logged_in:
            self.status.text = f"当前已登录：{self.app.campus.state.display()}"
        self.reload_captcha()

    def reload_captcha(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.status.text = "正在取验证码…"
        self.captcha_image.placeholder()

        def done(png: bytes) -> None:
            self._loading = False
            self.captcha_image.set_png(png)
            self.status.text = ""

        def failed(exc: Exception) -> None:
            self._loading = False
            self.status.text = f"验证码加载失败：{exc}"

        self.app.run_bg(self.app.campus.refresh_captcha, done, failed)

    def submit(self) -> None:
        username = (self.username.text or "").strip()
        password = self.password.text or ""
        captcha = (self.captcha.text or "").strip()
        if not username or not password:
            self.status.text = "学号和密码都要填"
            return
        if not captcha:
            self.status.text = "请按图输入验证码"
            return

        self.login_button.disabled = True
        self.status.text = "正在登录…"

        def done(result: LoginResult) -> None:
            self.login_button.disabled = False
            if result.ok:
                self.status.text = f"登录成功：{result.username}"
                self.password.text = ""
                self.captcha.text = ""
                self.app.on_login_success()
                self.app.back()
            else:
                self.status.text = result.message or "登录失败"
                self.captcha.text = ""
                self.reload_captcha()

        def failed(exc: Exception) -> None:
            self.login_button.disabled = False
            self.status.text = f"登录出错：{exc}"
            self.reload_captcha()

        self.app.run_bg(
            lambda: self.app.campus.submit_login(username, password, captcha),
            done,
            failed,
        )


__all__ = ["LoginScreen", "CaptchaImage"]
