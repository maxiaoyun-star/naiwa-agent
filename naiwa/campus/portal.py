"""教务数据适配器（课表 / 考试 / 个人信息）。

**这里有一个必须说清楚的现实**：长春理工大学门户的教务接口没有公开文档，
需要拿自己的账号抓一次包才能确定 URL。所以本模块的做法是：

* 接口路径**运行时可配**（设置页 → 高级 → 教务接口），不把猜测的路径写死；
* 解析层做得足够宽容：字段名走别名表，能吃掉正方 / 金智 / 自研门户几种常见格式；
* 没配置时抛出 ``PortalNotConfigured``，界面给一段可操作的中文提示，而不是一句 "error"。

抓包步骤见 ``docs/CAS接入说明.md``；``scripts/probe_portal.py`` 可以一次试完候选路径。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from .. import config
from .cas import CasClient, CasError, CookieJar
from .models import Course, Exam, UserProfile, WEEKDAYS


class PortalError(RuntimeError):
    """教务接口调用失败。"""


class PortalNotConfigured(PortalError):
    """接口路径还没配置。"""


class SessionExpired(PortalError):
    """登录态失效。"""


# 字段别名表：覆盖几种常见教务系统导出的 JSON 命名
COURSE_KEYS = {
    "name": ("kcmc", "courseName", "course_name", "name", "课程名称", "课程"),
    "teacher": ("jsxm", "teacher", "teacherName", "xm", "教师", "任课教师"),
    "room": ("cdmc", "room", "classroom", "classRoom", "dd", "上课地点", "教室"),
    "weekday": ("xqj", "weekday", "dayOfWeek", "day_of_week", "星期", "周几"),
    "sections": ("jcs", "jcor", "sections", "section", "节次", "上课节次"),
    "weeks": ("zcd", "zc", "weeks", "week", "周次", "上课周次"),
}

EXAM_KEYS = {
    "name": ("kcmc", "courseName", "name", "课程名称", "考试科目"),
    "date": ("ksrq", "date", "examDate", "考试日期"),
    "time": ("kssj", "time", "examTime", "考试时间", "时间段"),
    "room": ("kscdmc", "cdmc", "room", "考场", "考试地点"),
    "seat": ("zwh", "seat", "seatNo", "座位号"),
}

PROFILE_KEYS = {
    "name": ("xm", "name", "userName", "姓名"),
    "college": ("yxmc", "college", "学院", "院系"),
    "major": ("zymc", "major", "专业"),
    "grade": ("nj", "grade", "年级"),
}


def _first(payload: dict, keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        if key in payload and payload[key] not in (None, "", "null"):
            value = payload[key]
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, str):
                return value.strip()
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _weekday_of(value: Any) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        num = int(text)
        return num if 1 <= num <= 7 else default_weekday(text)
    return default_weekday(text)


def default_weekday(text: str) -> int:
    week_map = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
        "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
    }
    lowered = text.lower()
    for key, num in week_map.items():
        if key in lowered:
            return num
    return 0


def explode_rows(payload: Any, json_path: str = "") -> list[dict]:
    """把各种形状的返回体统一成 [dict, ...]。

    支持：
    * 直接是列表
    * {"data": [...]} / {"rows": [...]} / {"data": {"rows": [...]}} 等常见包装
    * ``json_path`` 手动指定，如 ``data.list``
    """
    node: Any = payload
    if json_path:
        for part in json_path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
    if isinstance(node, list):
        return [item for item in node if isinstance(item, dict)]
    if isinstance(node, dict):
        for key in ("rows", "list", "data", "items", "result", "records", "kbList"):
            value = node.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = explode_rows(value)
                if nested:
                    return nested
        # 只有一个对象也算一条
        return [node] if node else []
    return []


def parse_courses(payload: Any, json_path: str = "") -> list[Course]:
    courses: list[Course] = []
    for row in explode_rows(payload, json_path):
        name = _first(row, COURSE_KEYS["name"])
        if not name:
            continue
        courses.append(
            Course(
                name=name,
                weekday=_weekday_of(_first(row, COURSE_KEYS["weekday"])),
                sections=_first(row, COURSE_KEYS["sections"]),
                weeks=_first(row, COURSE_KEYS["weeks"]),
                teacher=_first(row, COURSE_KEYS["teacher"]),
                room=_first(row, COURSE_KEYS["room"]),
                raw=row,
            )
        )
    courses.sort(key=lambda item: (item.weekday or 9, item.sections or "99"))
    return courses


def parse_exams(payload: Any, json_path: str = "") -> list[Exam]:
    exams: list[Exam] = []
    for row in explode_rows(payload, json_path):
        name = _first(row, EXAM_KEYS["name"])
        if not name:
            continue
        exams.append(
            Exam(
                name=name,
                date=_first(row, EXAM_KEYS["date"]),
                time=_first(row, EXAM_KEYS["time"]),
                room=_first(row, EXAM_KEYS["room"]),
                seat=_first(row, EXAM_KEYS["seat"]),
                raw=row,
            )
        )
    return exams


def parse_profile(payload: Any, json_path: str = "") -> UserProfile:
    rows = explode_rows(payload, json_path)
    row = rows[0] if rows else {}
    return UserProfile(
        name=_first(row, PROFILE_KEYS["name"]),
        college=_first(row, PROFILE_KEYS["college"]),
        major=_first(row, PROFILE_KEYS["major"]),
        grade=_first(row, PROFILE_KEYS["grade"]),
    )


# ---------------------------------------------------------------------- 客户端
@dataclass
class ApiSpec:
    """一条教务接口的配置。"""

    path: str = ""
    json_path: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.path.strip())


class PortalClient:
    """拿 CAS 的 Cookie 去调门户的 JSON 接口。"""

    def __init__(self, jar: CookieJar, settings, timeout: float = config.HTTP_TIMEOUT) -> None:
        self.jar = jar
        self.settings = settings
        self.timeout = timeout

    # ------------------------------------------------------------------ 配置
    def spec(self, key: str) -> ApiSpec:
        return ApiSpec(
            path=str(self.settings.get(f"portal_api_{key}", "") or ""),
            json_path=str(self.settings.get(f"portal_api_{key}_path", "") or ""),
        )

    def configured(self) -> bool:
        return any(self.spec(k).ready for k in ("schedule", "exams", "profile"))

    # ------------------------------------------------------------------ HTTP
    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, str, str]:
        url = path if path.startswith("http") else urllib.parse.urljoin(config.PORTAL_BASE, path)
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
            if query:
                url = url + ("&" if "?" in url else "?") + query
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", config.USER_AGENT)
        request.add_header("Accept", "application/json, text/plain, */*")
        request.add_header("Referer", config.PORTAL_HOME)
        request.add_header("X-Requested-With", "XMLHttpRequest")
        cookie = self.jar.header_for(urllib.parse.urlsplit(url).hostname or "")
        if cookie:
            request.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
                final = response.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SessionExpired("登录已过期，请重新登录") from exc
            raise PortalError(f"教务接口返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise PortalError(f"连不上门户：{getattr(exc, 'reason', exc)}") from exc

        text = raw.decode("utf-8", "ignore")
        if "mysso.cust.edu.cn" in final or "统一身份认证" in text[:2000]:
            raise SessionExpired("登录已过期，请重新登录")
        return 200, text, content_type

    def ping(self) -> bool:
        """探活：门户首页还能不能拿到。返回 False 表示登录态确实失效。"""
        try:
            self._get(config.PORTAL_HOME)
            return True
        except SessionExpired:
            return False
        except PortalError:
            # 网络抖动 / 首页 404 不算掉线，交给业务接口自己报错
            return True

    def _json(self, spec: ApiSpec, params: dict[str, Any] | None = None) -> Any:
        if not spec.ready:
            raise PortalNotConfigured(
                "还没配置教务接口路径。在「我的 → 教务接口」里填入抓包得到的地址，"
                "或者先看 docs/CAS接入说明.md。"
            )
        _status, text, _ctype = self._get(spec.path, params)
        stripped = text.lstrip()
        if not stripped.startswith(("{", "[")):
            raise PortalError(
                "接口返回的不是 JSON（可能是网页）。把地址换成 XHR 请求里的那一条，"
                "浏览器 F12 → Network → Fetch/XHR。"
            )
        try:
            return json.loads(stripped)
        except ValueError as exc:
            raise PortalError("接口返回的 JSON 解析失败") from exc

    # ------------------------------------------------------------------ 业务
    def courses(self, week: int | None = None) -> list[Course]:
        spec = self.spec("schedule")
        params = {"week": week} if week else None
        return parse_courses(self._json(spec, params), spec.json_path)

    def exams(self) -> list[Exam]:
        spec = self.spec("exams")
        return parse_exams(self._json(spec), spec.json_path)

    def profile(self) -> UserProfile:
        spec = self.spec("profile")
        if not spec.ready:
            return UserProfile()
        try:
            return parse_profile(self._json(spec), spec.json_path)
        except PortalError:
            return UserProfile()


def build_client(cookies: dict[str, dict[str, str]], settings) -> PortalClient | None:
    """从保存的 Cookie 造客户端；没有会话返回 None。"""
    if not cookies:
        return None
    return PortalClient(CookieJar(cookies), settings)


__all__ = [
    "PortalClient", "PortalError", "PortalNotConfigured", "SessionExpired",
    "ApiSpec", "parse_courses", "parse_exams", "parse_profile", "explode_rows",
    "build_client", "COURSE_KEYS", "EXAM_KEYS", "WEEKDAYS",
]
