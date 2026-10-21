"""规则意图识别。

为什么不用小模型做 function calling：1–2B 的模型在中文工具选择上准确率很难看，
一句话就可能既想查课表又想查考试，还会编参数。所以这里用「关键词 + 槽位抽取」
把确定性做到 100%，模型只负责把查到的数据说人话 —— 这也正是技术方案里可以写的一条设计。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

INTENT_SCHEDULE = "schedule"
INTENT_EXAMS = "exams"
INTENT_GRADES = "grades"
INTENT_PROFILE = "profile"
INTENT_LOGIN = "login"
INTENT_HELP = "help"
INTENT_GREETING = "greeting"
INTENT_CHAT = "chat"

SCOPE_TODAY = "today"
SCOPE_TOMORROW = "tomorrow"
SCOPE_WEEK = "week"
SCOPE_DAY = "day"

_WEEKDAY_CN = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
}

_SCHEDULE_WORDS = (
    "课表", "课程表", "有课", "什么课", "几节课", "上课", "课多", "调课", "的课", "课程",
)
_EXAM_WORDS = ("考试", "考表", "考试安排", "考场", "监考", "补考", "期末", "几号考")
_GRADE_WORDS = ("成绩", "绩点", "分数", "挂科", "rank")
_PROFILE_WORDS = ("我的信息", "个人信息", "我的学号", "我是谁", "我的专业")
_LOGIN_WORDS = ("登录", "登录学号", "绑定", "认证", "统一身份", "账号密码")
_HELP_WORDS = ("怎么用", "帮助", "能做什么", "有什么功能", "你会什么", "使用说明")
_GREETING_WORDS = ("你好", "您好", "在吗", "hi", "hello", "哈喽", "早上好", "晚上好")


@dataclass
class Intent:
    name: str = INTENT_CHAT
    scope: str = SCOPE_WEEK
    weekday: int | None = None
    week: int | None = None
    confidence: float = 0.5
    raw: str = ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _extract_weekday(text: str) -> int | None:
    match = re.search(r"(?:周|星期|礼拜)([一二三四五六日天1-7])", text)
    if match:
        return _WEEKDAY_CN.get(match.group(1))
    return None


def _extract_week(text: str) -> int | None:
    match = re.search(r"第([0-9]{1,2})周", text)
    if match:
        try:
            value = int(match.group(1))
            if 1 <= value <= 30:
                return value
        except ValueError:
            return None
    return None


def _schedule_context(text: str) -> bool:
    """「周三的课」「明天要上什么」这类没有课程表字样但明显在问课的说法。"""
    if "课" not in text:
        return False
    if _extract_weekday(text):
        return True
    return any(word in text for word in ("今天", "明天", "后天", "上午", "下午"))


def classify(text: str) -> Intent:
    raw = (text or "").strip()
    norm = _normalize(raw)
    intent = Intent(raw=raw)

    if not norm:
        return Intent(name=INTENT_CHAT, confidence=0.0, raw=raw)

    # 优先级：教务查询 > 账号 > 帮助 > 寒暄 > 闲聊
    if any(word in norm for word in _EXAM_WORDS):
        intent.name = INTENT_EXAMS
        intent.confidence = 0.9
        return intent

    if any(word in norm for word in _SCHEDULE_WORDS) or _schedule_context(norm):
        intent.name = INTENT_SCHEDULE
        intent.confidence = 0.9
        intent.weekday = _extract_weekday(norm)
        intent.week = _extract_week(norm)
        if "今天" in norm or "今日" in norm:
            intent.scope = SCOPE_TODAY
        elif "明天" in norm:
            intent.scope = SCOPE_TOMORROW
        elif intent.weekday:
            intent.scope = SCOPE_DAY
        else:
            intent.scope = SCOPE_WEEK
        return intent

    if any(word in norm for word in _GRADE_WORDS):
        intent.name = INTENT_GRADES
        intent.confidence = 0.8
        return intent

    if any(word in norm for word in _PROFILE_WORDS):
        intent.name = INTENT_PROFILE
        intent.confidence = 0.8
        return intent

    if any(word in norm for word in _LOGIN_WORDS):
        intent.name = INTENT_LOGIN
        intent.confidence = 0.85
        return intent

    if any(word in norm for word in _HELP_WORDS):
        intent.name = INTENT_HELP
        intent.confidence = 0.8
        return intent

    if len(norm) <= 8 and any(norm.startswith(word) for word in _GREETING_WORDS):
        intent.name = INTENT_GREETING
        intent.confidence = 0.7
        return intent

    intent.name = INTENT_CHAT
    intent.confidence = 0.4
    return intent


def needs_campus(intent: Intent) -> bool:
    return intent.name in (INTENT_SCHEDULE, INTENT_EXAMS, INTENT_GRADES, INTENT_PROFILE)
