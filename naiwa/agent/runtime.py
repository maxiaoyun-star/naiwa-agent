"""智能体主循环：意图 → 工具 → 模型 → 回复。

三条铁律：
1. **数据只来自工具**。模型只被允许"把数据说人话"，不许自己补课表。
2. **任何一层失败都要有兜底**。本地模型挂了走云端，云端也没配就直接把数据原文给用户。
3. **失败提示必须可操作**。"出错了"是废话，"去登录"才有用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..llm.base import ProviderError
from ..llm.prompt import build_messages, offline_reply
from ..llm.router import LLMRouter
from . import intents as I
from .memory import ConversationMemory
from .tools import ACTION_LOGIN, ToolRegistry, ToolResult, time_greeting

QUICK_PROMPTS = ("今天有什么课", "本周课表", "考试安排", "你能做什么")

HELP_TEXT = (
    "我是奶娃，能帮你做这些：\n"
    "· 查课表：「今天有什么课」「周三的课」「第5周课表」\n"
    "· 查考试：「考试安排」「什么时候考」\n"
    "· 查账号：「我的信息」\n"
    "· 聊天答疑：学习、生活、办事流程，想到什么问什么\n"
    "查课表和考试要先在「我的」里用一卡通号登录。"
)

LOGIN_HINT = "登录走学校的统一身份认证。点下面这个按钮，填一卡通号和密码，验证码照图输就行。"


@dataclass
class Reply:
    text: str
    source: str = "template"     # tool | local | remote | template | ui
    action: str = ""
    display: dict | None = None


class AgentRuntime:
    def __init__(
        self,
        settings,
        llm: LLMRouter,
        campus,
        memory: ConversationMemory | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.campus = campus
        self.memory = memory or ConversationMemory()
        self.tools = ToolRegistry(campus)

    # ------------------------------------------------------------------ 主入口
    def answer(
        self,
        text: str,
        on_token: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Reply:
        text = (text or "").strip()
        if not text:
            return Reply("想聊点什么？", source="template")

        intent = I.classify(text)
        self.memory.add("user", text)

        if intent.name == I.INTENT_LOGIN:
            reply = Reply(LOGIN_HINT, source="ui", action=ACTION_LOGIN)
        elif intent.name == I.INTENT_HELP:
            reply = Reply(HELP_TEXT, source="template")
        elif I.needs_campus(intent):
            reply = self._answer_with_tools(intent, text, on_token, should_stop)
        elif intent.name == I.INTENT_GREETING:
            reply = self._answer_chat(text, on_token, should_stop, prefix=f"{time_greeting()}！")
        else:
            reply = self._answer_chat(text, on_token, should_stop)

        self.memory.add("assistant", reply.text)
        return reply

    # ------------------------------------------------------------------ 有数据
    def _answer_with_tools(
        self,
        intent: I.Intent,
        text: str,
        on_token: Callable[[str], None] | None,
        should_stop: Callable[[], bool] | None,
    ) -> Reply:
        result: ToolResult = self.tools.run(intent)
        if not result.ok:
            return Reply(result.error or "没查到", source="tool", action=result.action)

        data = result.text
        # 有数据时让模型润色，失败就直接回数据原文（信息的准确性优先）
        try:
            messages = build_messages(text, campus_data=data, history=self.memory.recent())
            routed = self.llm.generate(messages, on_token=on_token, should_stop=should_stop)
            body = routed.text
            source = routed.kind
        except ProviderError:
            body = data
            source = "tool"

        return Reply(body, source=source, display=result.display)

    # ------------------------------------------------------------------ 纯聊天
    def _answer_chat(
        self,
        text: str,
        on_token: Callable[[str], None] | None,
        should_stop: Callable[[], bool] | None,
        prefix: str = "",
    ) -> Reply:
        try:
            messages = build_messages(text, history=self.memory.recent())
            routed = self.llm.generate(messages, on_token=on_token, should_stop=should_stop)
            return Reply((prefix + routed.text) if prefix else routed.text, source=routed.kind)
        except ProviderError:
            return Reply(offline_reply("", text), source="template")


__all__ = ["AgentRuntime", "Reply", "QUICK_PROMPTS", "HELP_TEXT", "LOGIN_HINT"]
