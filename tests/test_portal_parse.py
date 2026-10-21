"""教务数据解析的单元测试。

真实接口拿不到，但「返回体形状」是有限的几种，这里把常见形状都锁住：
* 直接数组 / data.rows / rows / kbList（正方课表）
* 中文字段名 + 拼音字段名
"""

from __future__ import annotations

import unittest

from naiwa.campus.portal import (
    explode_rows,
    parse_courses,
    parse_exams,
    parse_profile,
)


class ExplodeRowsTest(unittest.TestCase):
    def test_plain_list(self) -> None:
        self.assertEqual(len(explode_rows([{"a": 1}, {"b": 2}])), 2)

    def test_data_rows(self) -> None:
        payload = {"code": 0, "data": {"rows": [{"a": 1}]}}
        self.assertEqual(len(explode_rows(payload)), 1)

    def test_rows(self) -> None:
        self.assertEqual(len(explode_rows({"rows": [{"a": 1}, {"a": 2}]})), 2)

    def test_json_path(self) -> None:
        payload = {"data": {"list": [{"a": 1}, {"a": 2}, {"a": 3}]}}
        self.assertEqual(len(explode_rows(payload, "data.list")), 3)

    def test_garbage(self) -> None:
        self.assertEqual(explode_rows(None), [])
        self.assertEqual(explode_rows("text"), [])


class ParseCoursesTest(unittest.TestCase):
    def test_pinyin_fields(self) -> None:
        payload = {
            "kbList": [
                {"kcmc": "高等数学", "xqj": "1", "jcs": "1-2", "cdmc": "东1-201",
                 "jsxm": "张三", "zcd": "1-16"},
            ]
        }
        courses = parse_courses(payload)
        self.assertEqual(len(courses), 1)
        course = courses[0]
        self.assertEqual(course.name, "高等数学")
        self.assertEqual(course.weekday, 1)
        self.assertEqual(course.room, "东1-201")
        self.assertEqual(course.to_line(), "周一 第1-2节 高等数学 东1-201 张三 1-16周")

    def test_chinese_fields(self) -> None:
        payload = [{"课程名称": "大学物理", "星期": "周三", "节次": "3-4", "上课地点": "B203", "教师": "李四"}]
        courses = parse_courses(payload)
        self.assertEqual(courses[0].weekday, 3)
        self.assertEqual(courses[0].name, "大学物理")

    def test_english_fields(self) -> None:
        payload = {"data": [{"courseName": "线性代数", "weekday": 2, "sections": "5-6", "room": "C101"}]}
        courses = parse_courses(payload, "data")
        self.assertEqual(courses[0].name, "线性代数")
        self.assertEqual(courses[0].weekday, 2)

    def test_sorted_by_day(self) -> None:
        payload = [
            {"name": "周五课", "weekday": 5},
            {"name": "周一课", "weekday": 1},
        ]
        courses = parse_courses(payload)
        self.assertEqual([c.name for c in courses], ["周一课", "周五课"])

    def test_rows_without_name_skipped(self) -> None:
        self.assertEqual(parse_courses([{"room": "A101"}]), [])


class ParseExamsTest(unittest.TestCase):
    def test_pinyin(self) -> None:
        payload = [
            {"kcmc": "数据结构", "ksrq": "2026-01-08", "kssj": "09:00-11:00",
             "kscdmc": "东2-305", "zwh": "12"},
        ]
        exams = parse_exams(payload)
        self.assertEqual(len(exams), 1)
        self.assertIn("数据结构", exams[0].to_line())
        self.assertIn("东2-305", exams[0].to_line())

    def test_empty(self) -> None:
        self.assertEqual(parse_exams({"rows": []}), [])


class ParseProfileTest(unittest.TestCase):
    def test_profile(self) -> None:
        profile = parse_profile({"data": {"xm": "王五", "yxmc": "计算机学院", "zymc": "软件工程"}})
        self.assertEqual(profile.name, "王五")
        self.assertEqual(profile.college, "计算机学院")
        self.assertEqual(profile.display(), "王五")


if __name__ == "__main__":
    unittest.main()
