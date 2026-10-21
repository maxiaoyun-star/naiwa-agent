"""工具层的单元测试：用假校园服务验证「数据 → 文本 / 视图」的转换与失败分支。"""

from __future__ import annotations

import unittest
from datetime import date

from naiwa.agent import intents as I
from naiwa.agent.tools import ToolRegistry, courses_to_text, exams_to_text, group_by_day
from naiwa.campus.models import Course, Exam, UserProfile
from naiwa.campus.portal import PortalNotConfigured, SessionExpired


class FakeState:
    logged_in = True
    username = "2021001"
    name = "张三"


class FakeCampus:
    def __init__(self, courses=None, exams=None, error=None):
        self.state = FakeState()
        self._courses = courses if courses is not None else []
        self._exams = exams if exams is not None else []
        self._error = error

    def courses(self, week=None):
        if self._error:
            raise self._error
        return self._courses

    def exams(self):
        if self._error:
            raise self._error
        return self._exams

    def profile(self):
        return UserProfile(name="张三", college="计算机学院")


COURSES = [
    Course(name="高等数学", weekday=1, sections="1-2", room="东1-201", teacher="张三", weeks="1-16"),
    Course(name="大学物理", weekday=3, sections="3-4", room="B203", teacher="李四"),
]
EXAMS = [Exam(name="数据结构", date="2026-01-08", time="09:00-11:00", room="东2-305", seat="12")]


class FormatTest(unittest.TestCase):
    def test_group_by_day(self) -> None:
        groups = group_by_day(COURSES)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["day"], "周一")
        self.assertEqual(groups[0]["items"][0]["name"], "高等数学")

    def test_courses_to_text(self) -> None:
        text = courses_to_text(COURSES, "本周课表")
        self.assertIn("共 2 节", text)
        self.assertIn("高等数学", text)

    def test_empty_text(self) -> None:
        self.assertIn("没有课", courses_to_text([], "今天"))

    def test_exams_to_text(self) -> None:
        text = exams_to_text(EXAMS, "考试安排")
        self.assertIn("数据结构", text)
        self.assertIn("东2-305", text)


class ToolRegistryTest(unittest.TestCase):
    def test_schedule_week(self) -> None:
        tools = ToolRegistry(FakeCampus(COURSES, EXAMS))
        result = tools.run(I.classify("本周课表"))
        self.assertTrue(result.ok)
        self.assertIn("高等数学", result.text)
        self.assertEqual(result.display["kind"], "schedule")
        self.assertEqual(result.display["count"], 2)

    def test_schedule_today_filters(self) -> None:
        today = date.today().isoweekday()
        tools = ToolRegistry(FakeCampus([Course(name="今日课", weekday=today, sections="1-2")]))
        result = tools.run(I.classify("今天有什么课"))
        self.assertTrue(result.ok)
        self.assertIn("今日课", result.text)

    def test_schedule_not_logged_in(self) -> None:
        tools = ToolRegistry(None)
        result = tools.run(I.classify("今天有什么课"))
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "open_login")

    def test_schedule_not_configured(self) -> None:
        tools = ToolRegistry(FakeCampus(error=PortalNotConfigured("没配置")))
        result = tools.run(I.classify("本周课表"))
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "open_endpoints")

    def test_session_expired(self) -> None:
        tools = ToolRegistry(FakeCampus(error=SessionExpired("过期了")))
        result = tools.run(I.classify("考试安排"))
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "open_login")

    def test_exams(self) -> None:
        tools = ToolRegistry(FakeCampus(COURSES, EXAMS))
        result = tools.run(I.classify("考试安排"))
        self.assertTrue(result.ok)
        self.assertEqual(result.display["items"][0]["name"], "数据结构")

    def test_profile(self) -> None:
        tools = ToolRegistry(FakeCampus(COURSES, EXAMS))
        result = tools.run(I.classify("我的信息"))
        self.assertTrue(result.ok)
        self.assertIn("2021001", result.text)

    def test_grades_not_implemented(self) -> None:
        tools = ToolRegistry(FakeCampus(COURSES, EXAMS))
        result = tools.run(I.classify("我的成绩"))
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "open_endpoints")


if __name__ == "__main__":
    unittest.main()
