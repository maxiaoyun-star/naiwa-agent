"""长春理工大学统一身份认证（CAS）客户端。

真实登录流程（已对着线上页面核实）：

    GET  https://mysso.cust.edu.cn/cas/login?service=<portal>
         ← 返回 HTML 表单，含隐藏字段 execution，页面里有验证码图片
    GET  https://mysso.cust.edu.cn/cas/captcha?ts=...          ← PNG，与登录同一会话
    POST https://mysso.cust.edu.cn/cas/login?service=<portal>
         username=一卡通号 & password=密码 & captcha=验证码 & execution=...
         &_eventId=submit & geolocation= & submit=LOGIN
         ← 302 Location: https://portal.cust.edu.cn/custp/shiro-cas?ticket=ST-xxx
    GET  <上面那个 Location>                                    ← 门户下发自己的会话 Cookie

要点：
* 全过程共用一套 Cookie（CAS 的 JSESSIONID / PAC4JDELSESSION + 门户会话）；
* 登录成功靠的是 302 + ticket，不是页面文案，所以这里**手动接管重定向**；
* 验证码是必填项，必须在界面上让人工确认，不能自动识别。
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from .. import config


class CasError(RuntimeError):
    """登录过程中的可展示错误。"""


class NeedCaptcha(CasError):
    """需要（重新）获取验证码。"""


# ---------------------------------------------------------------------- Cookie
class CookieJar:
    """极简 Cookie 罐：按域分桶，支持 Domain 属性与父域查找。

    不用 http.cookiejar 的原因：CAS 与门户是两个主机名，且都要跟着 302 走，
    自己管理才能在「手动接管重定向」时把 Cookie 精确带上并把会话存下来。
    """

    def __init__(self, data: dict[str, dict[str, str]] | None = None) -> None:
        self.buckets: dict[str, dict[str, str]] = {}
        if data:
            for domain, cookies in data.items():
                if isinstance(cookies, dict):
                    self.buckets[domain] = {str(k): str(v) for k, v in cookies.items()}

    # -------------------------------------------------------------- 写入
    def update_from_headers(self, host: str, headers: list[str]) -> None:
        for raw in headers:
            name, value, attrs = _parse_set_cookie(raw)
            if not name:
                continue
            domain = (attrs.get("domain") or "").lower().lstrip(".")
            key = domain if domain else host.lower()
            if attrs.get("max-age") == "0":
                self.buckets.get(key, {}).pop(name, None)
                continue
            self.buckets.setdefault(key, {})[name] = value

    # -------------------------------------------------------------- 读取
    def header_for(self, host: str) -> str:
        host = host.lower()
        merged: dict[str, str] = {}
        for key, cookies in self.buckets.items():
            if key == host or host.endswith("." + key.lstrip(".")) or key.lstrip(".") == host:
                merged.update(cookies)
        return "; ".join(f"{k}={v}" for k, v in merged.items())

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in self.buckets.items() if v}

    def is_empty(self) -> bool:
        return not any(self.buckets.values())


_SET_COOKIE_RE = re.compile(r"^\s*([^=;,\s]+)\s*=\s*([^;]*)\s*(?:;\s*(.*))?$", re.S)


def _parse_set_cookie(raw: str) -> tuple[str, str, dict[str, str]]:
    match = _SET_COOKIE_RE.match(raw)
    if not match:
        return "", "", {}
    name, value, tail = match.group(1), match.group(2), match.group(3) or ""
    attrs: dict[str, str] = {}
    for part in tail.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, val = part.partition("=")
            attrs[key.strip().lower()] = val.strip()
        else:
            attrs[part.lower()] = ""
    return name, value.strip().strip('"'), attrs


# ---------------------------------------------------------------------- HTML
class _LoginFormParser(HTMLParser):
    """从 CAS 登录页里抽 execution / 表单 action / 有没有验证码。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.execution = ""
        self.action = ""
        self.has_captcha = False
        self.has_password = False
        self._in_form = False
        self.text_chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self._in_form = True
            if attr.get("id") == "fm1" or not self.action:
                self.action = attr.get("action", self.action)
        elif tag == "input":
            name = attr.get("name", "")
            if name == "execution" and not self.execution:
                self.execution = attr.get("value", "")
            elif name == "captcha":
                self.has_captcha = True
            elif attr.get("type") == "password" or name == "password":
                self.has_password = True
        elif tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._in_form = False
        elif tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.text_chunks.append(data.strip())


def parse_login_form(html: str) -> _LoginFormParser:
    parser = _LoginFormParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - 脏 HTML 不能让登录流程崩掉
        pass
    return parser


# ---------------------------------------------------------------------- 结果
@dataclass
class LoginChallenge:
    """一次登录所需的上下文。"""

    execution: str = ""
    service: str = config.PORTAL_SERVICE
    captcha_required: bool = False
    captcha_png: bytes = b""
    form_action: str = ""

    def __bool__(self) -> bool:
        return bool(self.execution)


@dataclass
class LoginResult:
    ok: bool
    message: str = ""
    username: str = ""
    final_url: str = ""
    cookies: dict[str, dict[str, str]] = field(default_factory=dict)
    need_captcha: bool = False


# ---------------------------------------------------------------------- 客户端
class CasClient:
    def __init__(
        self,
        service: str = config.PORTAL_SERVICE,
        jar: CookieJar | None = None,
        timeout: float = config.HTTP_TIMEOUT,
    ) -> None:
        self.service = service
        self.jar = jar or CookieJar()
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP
    def _request(
        self,
        url: str,
        data: dict[str, str] | None = None,
        *,
        follow: bool = True,
        max_redirects: int = 8,
    ) -> tuple[int, bytes, str, dict[str, str]]:
        """返回 (状态码, 响应体, 最终 URL, 响应头)。

        ``follow=False`` 时把 3xx 当正常结果返回，便于手工处理 CAS 票据跳转。
        """
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        current = url
        for _hop in range(max_redirects + 1):
            request = urllib.request.Request(current, data=body, method="POST" if body else "GET")
            request.add_header("User-Agent", config.USER_AGENT)
            request.add_header("Accept-Language", "zh-CN,zh;q=0.9")
            request.add_header("Accept", "text/html,application/json,*/*")
            if body is not None:
                request.add_header("Content-Type", "application/x-www-form-urlencoded")
            cookie_header = self.jar.header_for(urllib.parse.urlsplit(current).hostname or "")
            if cookie_header:
                request.add_header("Cookie", cookie_header)

            try:
                response = urllib.request.urlopen(request, timeout=self.timeout)
                status = response.getcode()
                raw = response.read()
                headers = dict(response.headers.items())
                final = response.geturl()
                response.close()
            except urllib.error.HTTPError as exc:
                status = exc.code
                raw = exc.read() or b""
                headers = dict(exc.headers.items()) if exc.headers else {}
                final = exc.geturl()
                exc.close()
            except urllib.error.URLError as exc:
                raise CasError(f"连不上学校服务器：{getattr(exc, 'reason', exc)}") from exc
            except TimeoutError as exc:
                raise CasError("连接学校服务器超时，检查一下网络") from exc

            self._absorb_cookies(current, headers)
            if raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass

            location = _header(headers, "location")
            if status in (301, 302, 303, 307, 308) and location:
                if not follow:
                    return status, raw, location, headers
                current = urllib.parse.urljoin(current, location)
                body = None  # 302 之后按 GET 走
                continue
            return status, raw, final, headers
        raise CasError("重定向次数过多")

    def _absorb_cookies(self, url: str, headers: dict[str, str]) -> None:
        host = urllib.parse.urlsplit(url).hostname or ""
        raw_cookies: list[str] = []
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                if value and value not in raw_cookies:
                    raw_cookies.append(value)
        if raw_cookies:
            self.jar.update_from_headers(host, raw_cookies)

    # ------------------------------------------------------------------ 登录页
    def fetch_challenge(self, fetch_captcha: bool = True) -> LoginChallenge:
        url = config.CAS_LOGIN + "?service=" + urllib.parse.quote(self.service, safe="")
        status, raw, _final, _headers = self._request(url)
        html = raw.decode("utf-8", "ignore")
        if status >= 400:
            raise CasError(f"打开登录页失败（HTTP {status}）")
        form = parse_login_form(html)
        if not form.execution and not form.has_password:
            raise CasError("登录页结构变了：没有找到 execution 字段，可能学校升级了认证系统")
        challenge = LoginChallenge(
            execution=form.execution,
            service=self.service,
            captcha_required=form.has_captcha,
            form_action=urllib.parse.urljoin(url, form.action or "login"),
        )
        if fetch_captcha and form.has_captcha:
            challenge.captcha_png = self.fetch_captcha()
        return challenge

    def fetch_captcha(self) -> bytes:
        url = f"{config.CAS_CAPTCHA}?ts={int(time.time() * 1000)}"
        status, raw, _final, headers = self._request(url)
        if status != 200 or not raw:
            raise CasError("验证码加载失败，点一下重试")
        content_type = _header(headers, "content-type") or ""
        if "image" not in content_type and not raw.startswith(b"\x89PNG"):
            raise CasError("验证码返回的不是图片，可能登录页改版了")
        return raw

    # ------------------------------------------------------------------ 登录
    def login(
        self,
        username: str,
        password: str,
        captcha: str,
        challenge: LoginChallenge,
    ) -> LoginResult:
        username = (username or "").strip()
        if not username or not password:
            return LoginResult(False, "学号和一卡通密码都要填")
        if challenge.captcha_required and not (captcha or "").strip():
            return LoginResult(False, "请填写验证码", need_captcha=True)

        payload = {
            "username": username,
            "password": password,
            "captcha": (captcha or "").strip(),
            "execution": challenge.execution,
            "_eventId": "submit",
            "geolocation": "",
            "submit": "LOGIN",
            # 查询串和表单里都带 service，兼容不同版本的 CAS 实现
            "service": challenge.service,
        }
        post_url = config.CAS_LOGIN + "?service=" + urllib.parse.quote(challenge.service, safe="")

        status, raw, location, _headers = self._request(post_url, payload, follow=False)
        text = raw.decode("utf-8", "ignore")

        # 失败：又回到登录页，或者带错误提示
        if status in (200,):
            reason = _extract_error(text) or "登录失败，请检查学号、密码、验证码"
            form = parse_login_form(text)
            return LoginResult(
                False,
                reason,
                need_captcha=form.has_captcha or "验证码" in reason,
            )

        if status not in (301, 302, 303, 307, 308):
            return LoginResult(False, f"学校服务器返回了异常状态（HTTP {status}）")

        if "ticket" not in location.lower():
            reason = _extract_error(text) or "没有拿到登录票据，请重试"
            return LoginResult(False, reason, need_captcha=True)

        # 拿票据换门户会话
        final_url = location
        try:
            pstatus, praw, final_url, _ = self._request(location, follow=True, max_redirects=8)
        except CasError as exc:
            return LoginResult(False, str(exc))

        if "mysso.cust.edu.cn" in final_url and "/cas/login" in final_url:
            return LoginResult(False, "门户拒绝了本次登录，请重新登录")

        ptext = praw.decode("utf-8", "ignore")
        if "统一身份认证" in ptext and "name=\"execution\"" in ptext:
            return LoginResult(False, "登录未完成，请重试")

        return LoginResult(
            ok=True,
            message="登录成功",
            username=username,
            final_url=final_url,
            cookies=self.jar.as_dict(),
        )

    # ------------------------------------------------------------------ 会话复用
    def check_alive(self) -> bool:
        """已保存的会话是否还有效。"""
        try:
            status, raw, final, _ = self._request(config.PORTAL_HOME, follow=True)
        except CasError:
            return False
        if status != 200:
            return False
        # 被踢回认证页就说明过期了
        return "mysso.cust.edu.cn" not in final


def _header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


_ALERT_RE = re.compile(
    r'<(?:div|span|p)[^>]*class="[^"]*(?:alert|errors|error|msg)[^"]*"[^>]*>(.*?)</(?:div|span|p)>',
    re.S | re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_error(html: str) -> str:
    for hinted in config.CAS_ERROR_HINTS:
        if hinted in html:
            return hinted
    for chunk in _ALERT_RE.findall(html)[:3]:
        text = _TAG_RE.sub(" ", chunk)
        text = " ".join(text.split())
        if text and len(text) < 120:
            return text
    return ""


def dump_session(cookies: dict[str, dict[str, str]]) -> str:
    return json.dumps(cookies, ensure_ascii=False)
