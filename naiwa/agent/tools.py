"""工具层：把「意图」变成「真实数据」。

工具只做一件事 —— 取数据、格式化成两段文本：
* ``text``：给模型看的紧凑数据块（小模型读不懂 JSON，越像人话越好）；
* ``display``：给界面渲染的结构化内容（课表按天分组、考试列表）。

失败时给出**可操作的**提示和 ``action``，界面据此决定是跳登录页还是弹配置说明。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..campus.models import WEEKDAYS, Course, Exam
from ..campus.portal import PortalError, PortalNotConfigured, SessionExpired
from . import intents as I

ACTION_LOGIN = "open_login"
ACTION_ENDPOINTS = "open_endpoints"
ACTION_SETTINGS = "open_settings"

MAX_LINES = 40


@dataclass
class ToolResult:
    ok: bool = True
    text: str = ""
    display: dict | None = None
    error: str = ""
    action: str = ""


@dataclass
class GroupedDay:
    day: str
    items: list[dict] = field(default_factory=list)


def _course_item(course: Course) -> dict:
    return {
        "name": course.name,
        "time": f"第{course.sections}节" if course.sections else "",
        "room": course.room,
        "teacher": course.teacher,
        "weeks": course.weeks,
    }


def group_by_day(courses: list[Course]) -> list[dict]:
    buckets: dict[int, list[Course]] = {}
    for course in courses:
        buckets.setdefault(course.weekday or 0, []).append(course)
    groups = []
    for weekday in sorted(buckets):
        label = WEEKDAYS[weekday - 1] if 1 <= weekday <= 7 else "未排课"
        groups.append({
            "day": label,
            "items": [_course_item(course) for course in buckets[weekday]],
        })
    return groups


def courses_to_text(courses: list[Course], title: str) -> str:
    if not courses:
        return f"{title}没有课。"
    lines = [f"{title}共 {len(courses)} 节："]
    for course in courses[:MAX_LINES]:
        lines.append("- " + course.to_line())
    if len(courses) > MAX_LINES:
        lines.append(f"（还有 {len(courses) - MAX_LINES} 节，只列前 {MAX_LINES} 节）")
    return "\n".join(lines)


def exams_to_text(exams: list[Exam], title: str) -> str:
    if not exams:
        return f"{title}没有查到考试安排。"
    lines = [f"{title}共 {len(exams)} 场："]
    for exam in exams[:MAX_LINES]:
        lines.append("- " + exam.to_line())
    return "\n".join(lines)


class ToolRegistry:
    """所有工具的入口。"""

    def __init__(self, campus) -> None:
        self.campus = campus

    # ------------------------------------------------------------------ 分发
    def run(self, intent: I.Intent) -> ToolResult:
        if intent.name == I.INTENT_SCHEDULE:
            return self.schedule(intent)
        if intent.name == I.INTENT_EXAMS:
            return self.exams()
        if intent.name == I.INTENT_PROFILE:
            return self.profile()
        if intent.name == I.INTENT_GRADES:
            return ToolResult(
                ok=False,
                error="成绩查询还没接上：教务系统里成绩接口是另一个地址，抓到后填进「我的 → 教务接口」就能用。",
                action=ACTION_ENDPOINTS,
            )
        return ToolResult(ok=False, error="这个我查不了", action="")

    # ------------------------------------------------------------------ 课表
    def schedule(self, intent: I.Intent) -> ToolResult:
        if self.campus is None:
            return ToolResult(False, error="还没登录学校账号，先去「我的」里登录。", action=ACTION_LOGIN)

        weekday = intent.weekday
        scope = intent.scope
        if scope == I.SCOPE_TODAY:
            weekday = date.today().isoweekday()
        elif scope == I.SCOPE_TOMORROW:
            weekday = (date.today() + timedelta(days=1)).isoweekday()

        try:
            courses = self.campus.courses(week=intent.week)
        except PortalNotConfigured as exc:
            return ToolResult(False, error=str(exc), action=ACTION_ENDPOINTS)
        except SessionExpired as exc:
            return ToolResult(False, error=str(exc), action=ACTION_LOGIN)
        except PortalError as exc:
            return ToolResult(False, error=f"查课表失败：{exc}", action=ACTION_ENDPOINTS)

        if weekday:
            courses = [course for course in courses if course.weekday == weekday]
            label = WEEKDAYS[weekday - 1]
            title = f"{label}的课"
            if scope == I.SCOPE_TODAY:
                title = "今天"
            elif scope == I.SCOPE_TOMORROW:
                title = "明天"
        else:
            title = f"第{intent.week}周课表" if intent.week else "本周课表"

        return ToolResult(
            ok=True,
            text=courses_to_text(courses, title),
            display={
                "kind": "schedule",
                "title": title,
                "count": len(courses),
                "groups": group_by_day(courses),
            },
        )

    # ------------------------------------------------------------------ 考试
    def exams(self) -> ToolResult:
        if self.campus is None:
            return ToolResult(False, error="还没登录学校账号，先去「我的」里登录。", action=ACTION_LOGIN)
        try:
            exams = self.campus.exams()
        except PortalNotConfigured as exc:
            return ToolResult(False, error=str(exc), action=ACTION_ENDPOINTS)
        except SessionExpired as exc:
            return ToolResult(False, error=str(exc), action=ACTION_LOGIN)
        except PortalError as exc:
            return ToolResult(False, error=f"查考试安排失败：{exc}", action=ACTION_ENDPOINTS)

        return ToolResult(
            ok=True,
            text=exams_to_text(exams, "考试安排"),
            display={
                "kind": "exams",
                "title": "考试安排",
                "count": len(exams),
                "items": [
                    {
                        "name": exam.name,
                        "when": " ".join(part for part in (exam.date, exam.time) if part),
                        "room": exam.room,
                        "seat": exam.seat,
                    }
                    for exam in exams
                ],
            },
        )

    # ------------------------------------------------------------------ 个人信息
    def profile(self) -> ToolResult:
        if self.campus is None:
            return ToolResult(False, error="还没登录学校账号。", action=ACTION_LOGIN)
        profile = self.campus.profile()
        state = self.campus.state
        name = profile.name or state.name or "同学"
        parts = [f"你当前登录的账号是 {state.username or '未知'}（{name}）"]
        if profile.college:
            parts.append(f"学院：{profile.college}")
        if profile.major:
            parts.append(f"专业：{profile.major}")
        return ToolResult(
            ok=True,
            text="，".join(parts) + "。",
            display={"kind": "profile", "username": state.username, "name": name},
        )

    # ------------------------------------------------------------------ 时间
    @staticmethod
    def now_text() -> str:
        now = datetime.now()
        return f"现在是 {now.month}月{now.day}日 {WEEKDAYS[now.isoweekday() - 1]} {now:%H:%M}"


def time_greeting() -> str:
    hour = time.localtime().tm_hour
    if hour < 6:
        return "这么晚还没睡"
    if hour < 11:
        return "早上好"
    if hour < 14:
        return "中午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


__all__ = [
    "ToolResult", "ToolRegistry", "courses_to_text", "exams_to_text",
    "group_by_day", "time_greeting", "ACTION_LOGIN", "ACTION_ENDPOINTS",
    "ACTION_SETTINGS",
]
