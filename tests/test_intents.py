"""意图识别的单元测试。

这层是确定性的，改了关键词就会影响产品行为，所以值得锁住。
"""

from __future__ import annotations

import unittest

from naiwa.agent import intents as I


class ClassifyTest(unittest.TestCase):
    def test_schedule_today(self) -> None:
        intent = I.classify("今天有什么课")
        self.assertEqual(intent.name, I.INTENT_SCHEDULE)
        self.assertEqual(intent.scope, I.SCOPE_TODAY)

    def test_schedule_tomorrow(self) -> None:
        intent = I.classify("明天有课吗")
        self.assertEqual(intent.name, I.INTENT_SCHEDULE)
        self.assertEqual(intent.scope, I.SCOPE_TOMORROW)

    def test_schedule_weekday(self) -> None:
        intent = I.classify("周三的课")
        self.assertEqual(intent.name, I.INTENT_SCHEDULE)
        self.assertEqual(intent.weekday, 3)
        self.assertEqual(intent.scope, I.SCOPE_DAY)

    def test_schedule_week_number(self) -> None:
        intent = I.classify("第5周课表")
        self.assertEqual(intent.name, I.INTENT_SCHEDULE)
        self.assertEqual(intent.week, 5)

    def test_sunday_alias(self) -> None:
        intent = I.classify("周天上课吗")
        self.assertEqual(intent.name, I.INTENT_SCHEDULE)
        self.assertEqual(intent.weekday, 7)

    def test_exams(self) -> None:
        for text in ("考试安排", "这学期几号考", "考场在哪"):
            with self.subTest(text=text):
                self.assertEqual(I.classify(text).name, I.INTENT_EXAMS)

    def test_help_and_greeting(self) -> None:
        self.assertEqual(I.classify("你能做什么").name, I.INTENT_HELP)
        self.assertEqual(I.classify("你好").name, I.INTENT_GREETING)

    def test_login(self) -> None:
        self.assertEqual(I.classify("怎么登录学号").name, I.INTENT_LOGIN)

    def test_plain_chat(self) -> None:
        self.assertEqual(I.classify("帮我写个学习计划").name, I.INTENT_CHAT)

    def test_empty(self) -> None:
        intent = I.classify("   ")
        self.assertEqual(intent.name, I.INTENT_CHAT)
        self.assertEqual(intent.confidence, 0.0)

    def test_needs_campus(self) -> None:
        self.assertTrue(I.needs_campus(I.classify("考试安排")))
        self.assertFalse(I.needs_campus(I.classify("你好")))


if __name__ == "__main__":
    unittest.main()
