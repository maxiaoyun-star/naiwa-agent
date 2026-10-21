"""智能体主循环的单元测试：用假模型验证降级链路。

这是整个产品最关键的一条路径 —— 本地模型挂了、云端没配，也必须给出可用答案。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from naiwa.agent.memory import ConversationMemory
from naiwa.agent.runtime import AgentRuntime
from naiwa.campus.models import Course, Exam, UserProfile
from naiwa.llm.base import ProviderError
from naiwa.store import HistoryStore


class FakeState:
    logged_in = True
    username = "2021001"
    name = "张三"


class FakeCampus:
    def __init__(self) -> None:
        self.state = FakeState()

    def courses(self, week=None):
        return [Course(name="高等数学", weekday=1, sections="1-2", room="东1-201")]

    def exams(self):
        return [Exam(name="数据结构", date="2026-01-08", time="09:00-11:00", room="东2-305")]

    def profile(self):
        return UserProfile(name="张三")


class OkRouter:
    """模拟可用的模型：返回固定文本，并触发一次流式回调。"""

    def __init__(self, text: str = "模型润色后的回答") -> None:
        self.text = text
        self.calls = 0
        self._local_ready = True

    def generate(self, messages, on_token=None, should_stop=None):
        self.calls += 1
        if on_token is not None:
            on_token(self.text)
        return SimpleNamespace(text=self.text, kind="local")

    def local_ready(self):
        return self._local_ready

    def status(self):
        return "本地", "ok"


class DeadRouter(OkRouter):
    def generate(self, messages, on_token=None, should_stop=None):
        raise ProviderError("模型挂了")


class RuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = ConversationMemory(HistoryStore(Path(self.tmp.name) / "history.json"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runtime(self, router, campus=None) -> AgentRuntime:
        return AgentRuntime(SimpleNamespace(get=lambda *_: None), router, campus or FakeCampus(), self.memory)

    def test_schedule_uses_data_and_model(self) -> None:
        router = OkRouter("周一 1-2 节有高等数学，别迟到。")
        runtime = self._runtime(router)
        reply = runtime.answer("本周课表")
        self.assertEqual(reply.text, "周一 1-2 节有高等数学，别迟到。")
        self.assertEqual(reply.source, "local")
        self.assertEqual(reply.display["kind"], "schedule")
        self.assertEqual(router.calls, 1)

    def test_schedule_falls_back_to_raw_data(self) -> None:
        runtime = self._runtime(DeadRouter())
        reply = runtime.answer("本周课表")
        # 模型不可用时必须回退到工具数据本身，而不是报错
        self.assertIn("高等数学", reply.text)
        self.assertEqual(reply.source, "tool")

    def test_chat_without_model_uses_offline_text(self) -> None:
        runtime = self._runtime(DeadRouter())
        reply = runtime.answer("帮我写个学习计划")
        self.assertEqual(reply.source, "template")
        self.assertIn("本地模型", reply.text)

    def test_greeting_prefix(self) -> None:
        runtime = self._runtime(OkRouter("今天想做点什么？"))
        reply = runtime.answer("你好")
        self.assertTrue(reply.text.startswith("早上好") or "？" in reply.text)

    def test_login_intent_returns_action(self) -> None:
        runtime = self._runtime(OkRouter())
        reply = runtime.answer("怎么登录学号")
        self.assertEqual(reply.action, "open_login")
        self.assertEqual(reply.source, "ui")

    def test_streaming_callback_fires(self) -> None:
        pieces = []
        runtime = self._runtime(OkRouter("分块输出"))
        runtime.answer("你好", on_token=pieces.append)
        self.assertEqual(pieces, ["分块输出"])

    def test_memory_records_both_sides(self) -> None:
        runtime = self._runtime(OkRouter("收到"))
        runtime.answer("本周课表")
        roles = [item["role"] for item in self.memory.recent()]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    def test_empty_input(self) -> None:
        runtime = self._runtime(OkRouter())
        reply = runtime.answer("   ")
        self.assertTrue(reply.text)


if __name__ == "__main__":
    unittest.main()
