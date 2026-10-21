"""把「CAS 登录 + 教务查询」封装成一个对象，给 UI 和工具层共用。

这里解决一个容易写错的地方：**取验证码和提交登录必须用同一个会话**。
所以 ``begin_login()`` 返回的 challenge 会连带一个未完成的 CasClient 挂在实例上，
``submit_login()`` 复用它 —— 重新 new 一个客户端就会因为 Cookie 不匹配而一直报验证码错误。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .. import config
from .cas import CasClient, CasError, CookieJar, LoginChallenge, LoginResult
from .models import Course, Exam, UserProfile
from .portal import (
    PortalClient,
    PortalError,
    PortalNotConfigured,
    SessionExpired,
    build_client,
)


@dataclass
class CampusState:
    logged_in: bool = False
    username: str = ""
    name: str = ""
    checked_at: float = 0.0
    message: str = ""
    cookies: dict[str, dict[str, str]] = field(default_factory=dict)

    def display(self) -> str:
        if not self.logged_in:
            return "未登录"
        return self.name or self.username or "已登录"


class CampusService:
    def __init__(self, settings, session_store) -> None:
        self.settings = settings
        self.sessions = session_store
        self.state = CampusState()
        self._lock = threading.RLock()
        self._client: CasClient | None = None
        self._challenge: LoginChallenge | None = None
        self._portal: PortalClient | None = None
        self._jar = CookieJar()
        self._restore()

    # ------------------------------------------------------------------ 会话
    def _restore(self) -> None:
        data = self.sessions.load()
        if not data:
            return
        cookies = data.get("cookies") or {}
        if not isinstance(cookies, dict):
            return
        self.state.cookies = cookies
        self.state.username = str(data.get("username", ""))
        self._jar = CookieJar(cookies)
        self._portal = build_client(cookies, self.settings)
        self.state.logged_in = bool(cookies)
        self.state.message = "已恢复上次登录"

    def client(self) -> PortalClient | None:
        with self._lock:
            if self._portal is None and self.state.cookies:
                self._portal = build_client(self.state.cookies, self.settings)
            return self._portal

    def logout(self) -> None:
        with self._lock:
            self._client = None
            self._challenge = None
            self._portal = None
            self._jar = CookieJar()
            self.state = CampusState()
            self.sessions.clear()

    # ------------------------------------------------------------------ 登录
    def begin_login(self) -> LoginChallenge:
        """打开登录页 + 取验证码。抛 CasError。"""
        with self._lock:
            self._client = CasClient(jar=CookieJar())
            self._challenge = self._client.fetch_challenge()
            return self._challenge

    def refresh_captcha(self) -> bytes:
        with self._lock:
            if self._client is None:
                self.begin_login()
            assert self._client is not None
            return self._client.fetch_captcha()

    def submit_login(self, username: str, password: str, captcha: str) -> LoginResult:
        with self._lock:
            if self._client is None or self._challenge is None:
                # 会话丢了（比如界面重建），重新走一遍
                self._client = CasClient(jar=CookieJar())
                self._challenge = self._client.fetch_challenge()
            result = self._client.login(username, password, captcha, self._challenge)
            if result.ok:
                self.state = CampusState(
                    logged_in=True,
                    username=username,
                    checked_at=time.time(),
                    message=result.message,
                    cookies=result.cookies,
                )
                self._portal = build_client(result.cookies, self.settings)
                self.settings.set("cas_username", username)
                remember = bool(self.settings.get("cas_remember", True))
                save_password = bool(self.settings.get("cas_save_password", False))
                if remember:
                    self.sessions.save(
                        username,
                        result.cookies,
                        password if save_password else "",
                    )
                try:
                    profile = self._portal.profile() if self._portal else UserProfile()
                    self.state.name = profile.name
                except PortalError:
                    pass
            else:
                # 失败后旧 execution 失效，必须换一张新验证码
                try:
                    self._challenge = self._client.fetch_challenge()
                except CasError:
                    self._challenge = None
            return result

    # ------------------------------------------------------------------ 查询
    def _ensure(self) -> PortalClient:
        client = self.client()
        if client is None:
            raise SessionExpired("还没登录，先绑定学号")
        if not client.configured():
            raise PortalNotConfigured(
                "教务接口还没配。用电脑抓一次包，把课表/考试的接口地址填进「我的 → 教务接口」。"
            )
        return client

    def ensure_alive(self) -> bool:
        """用保存的 Cookie 探一下门户，失效就清掉状态。"""
        with self._lock:
            if not self.state.logged_in:
                return False
            client = self._portal or build_client(self.state.cookies, self.settings)
            if client is None:
                return False
            try:
                alive = client.ping()
                if alive:
                    self.state.checked_at = time.time()
                else:
                    self.state.logged_in = False
                    self.state.message = "登录已过期"
                return alive
            except PortalError:
                return True  # 网络问题不当作掉线

    def courses(self, week: int | None = None) -> list[Course]:
        return self._ensure().courses(week)

    def exams(self) -> list[Exam]:
        return self._ensure().exams()

    def profile(self) -> UserProfile:
        client = self.client()
        if client is None:
            return UserProfile()
        return client.profile()


__all__ = ["CampusService", "CampusState"]
