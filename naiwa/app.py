"""应用装配：服务、导航、后台任务。

所有跨页面的服务（设置、模型、LLM、校园、记忆）都挂在 App 实例上，
Screen 通过 ``self.app`` 访问，避免到处传参。
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Callable

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from . import config
from .agent.memory import ConversationMemory
from .agent.runtime import AgentRuntime
from .campus.service import CampusService
from .llm.router import LLMRouter
from .model_manager import ModelManager
from .store import Secrets, SessionStore, Settings
from .ui import theme as T
from .ui.chat import ChatScreen
from .ui.home import HomeScreen
from .ui.login import LoginScreen
from .ui.schedule import ScheduleScreen
from .ui.settings_screen import SettingsScreen


class NaiwaApp(App):
    title = config.APP_NAME

    # ------------------------------------------------------------------ 构建
    def build(self):
        T.apply_window()
        T.register_fonts()

        self.settings = Settings()
        self.secrets = Secrets()
        self.sessions = SessionStore()
        self.model_manager = ModelManager(self.settings)
        self.llm = LLMRouter(self.settings, self.secrets)
        self.campus = CampusService(self.settings, self.sessions)
        self.memory = ConversationMemory()
        self.runtime = AgentRuntime(self.settings, self.llm, self.campus, self.memory)

        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.sm.add_widget(HomeScreen(app=self, name="home"))
        self.sm.add_widget(ChatScreen(app=self, name="chat"))
        self.sm.add_widget(ScheduleScreen(app=self, name="schedule"))
        self.sm.add_widget(LoginScreen(app=self, name="login"))
        self.sm.add_widget(SettingsScreen(app=self, name="settings"))
        self.sm.current = "home"
        self._stack: list[str] = ["home"]
        self._loading_model = False

        self._install_exception_hooks()
        Window.bind(on_keyboard=self._on_key)
        Clock.schedule_once(self._boot, 0.5)
        return self.sm

    # ------------------------------------------------------------------ 错误记录
    def _install_exception_hooks(self) -> None:
        """把未捕获异常写进 crash.log。

        Android 上没有控制台，闪退后什么线索都没有 —— 用户反馈的三个问题里有两个
        根本无法复现。这里至少保证下次能读到 traceback。
        """
        original_hook = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            try:
                self.log_error("uncaught", exc_value, exc_type, exc_tb)
            finally:
                original_hook(exc_type, exc_value, exc_tb)

        sys.excepthook = _hook

        def _thread_hook(args) -> None:
            if args.exc_value is not None:
                self.log_error(
                    f"thread:{getattr(args.thread, 'name', '?')}",
                    args.exc_value,
                    args.exc_type,
                    args.exc_traceback,
                )

        try:
            threading.excepthook = _thread_hook  # type: ignore[assignment]
        except Exception:  # noqa: BLE001
            pass

    def log_error(self, where: str, exc: BaseException, exc_type=None, exc_tb=None) -> str:
        """写一条错误到 crash.log（只保留最近 30 条），返回日志文本。"""
        try:
            stamp = time.strftime("%m-%d %H:%M:%S")
            text = "".join(
                traceback.format_exception(
                    exc_type or type(exc), exc, exc_tb or exc.__traceback__
                )
            )
            line = f"[{stamp}] {where}: {text}\n"
            print(f"[naiwa] {line}")
            path = config.logs_dir() / "crash.log"
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
            return self.read_error_log()
        except Exception:  # noqa: BLE001
            return ""

    def read_error_log(self) -> str:
        try:
            path = config.logs_dir() / "crash.log"
            if not path.is_file():
                return "还没有错误记录。"
            data = path.read_text(encoding="utf-8", errors="replace")
            return data[-6000:] if data else "还没有错误记录。"
        except OSError as exc:
            return f"读不到日志：{exc}"

    def _boot(self, _dt=None) -> None:
        """启动后延迟执行：别和首帧抢 CPU。"""
        if self.llm.remote_ready():
            self.llm.reload()
        if self.settings.get("llm_mode") in ("auto", "local") and self.model_manager.existing():
            self.load_local_model()
        if self.campus.state.logged_in:
            self.run_bg(self.campus.ensure_alive, self._on_alive_checked, lambda _e: None)

    def _on_alive_checked(self, alive: bool) -> None:
        if not alive:
            self.on_session_changed()

    # ------------------------------------------------------------------ 导航
    def go(self, name: str) -> None:
        if name == self.sm.current:
            return
        self._stack.append(name)
        self.sm.current = name

    def back(self) -> None:
        if len(self._stack) <= 1:
            return
        self._stack.pop()
        target = self._stack[-1]
        self.sm.current = target

    def _on_key(self, _window, key, *_args):
        if key in (27, 1001):  # ESC / Android 返回键
            if self.sm.current != "home":
                self.back()
                return True
        return False

    # ------------------------------------------------------------------ 后台任务
    def run_bg(
        self,
        fn: Callable,
        on_done: Callable | None = None,
        on_error: Callable | None = None,
    ) -> None:
        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                if on_error is not None:
                    Clock.schedule_once(lambda _dt: on_error(exc), 0)
                return
            if on_done is not None:
                Clock.schedule_once(lambda _dt: on_done(result), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ 模型
    def load_local_model(self) -> None:
        if self._loading_model:
            return
        if self.model_manager.existing() is None:
            self._toast("还没安装模型文件，先去设置里下载")
            return
        self._loading_model = True
        home = self.sm.get_screen("home")
        home.status_text.text = "正在加载本地模型（首次约 5–20 秒）…"

        def progress(message: str) -> None:
            Clock.schedule_once(lambda _dt: setattr(home.status_text, "text", message), 0)

        def done(ok: bool) -> None:
            self._loading_model = False
            home._refresh()  # noqa: SLF001
            if not ok:
                self._toast(f"本地模型加载失败：{self.llm.local_error[:120]}")

        def failed(exc: Exception) -> None:
            self._loading_model = False
            home._refresh()  # noqa: SLF001
            self._toast(f"加载出错：{exc}")

        self.run_bg(lambda: self.llm.load_local(progress), done, failed)

    # ------------------------------------------------------------------ 状态变更
    def on_login_success(self) -> None:
        self._toast("登录成功")
        self.on_session_changed()

    def on_session_changed(self) -> None:
        if "settings" in self.sm.screen_names:
            self.sm.get_screen("settings")._refresh()  # noqa: SLF001
        if "home" in self.sm.screen_names:
            self.sm.get_screen("home")._refresh()  # noqa: SLF001

    def clear_chat(self) -> None:
        self.sm.get_screen("chat").clear()
        self._toast("对话已清空")

    def clear_all_data(self) -> None:
        try:
            self.memory.clear()
            self.campus.logout()
            self.secrets.clear()
        except OSError:
            pass
        self.sm.get_screen("chat").clear()
        self.on_session_changed()
        self._toast("本地数据已清除（模型文件保留）")

    # ------------------------------------------------------------------ 提示
    def _toast(self, text: str) -> None:
        """极简提示：直接写到首页状态卡 / 控制台，避免引入第三方 Toast。

        手机上用户多半在当前页，所以同时 print 一份到 logcat 方便排查。
        """
        print(f"[naiwa] {text}")
        if self.sm.current == "home":
            self.sm.get_screen("home").status_text.text = text


if __name__ == "__main__":
    NaiwaApp().run()
