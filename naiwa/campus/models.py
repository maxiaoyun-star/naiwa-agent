"""校园数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


@dataclass
class Course:
    name: str
    weekday: int = 0            # 1=周一
    sections: str = ""          # 第几节，如 "3-4"
    weeks: str = ""             # 周次，如 "1-16"
    teacher: str = ""
    room: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def to_line(self) -> str:
        bits = [WEEKDAYS[self.weekday - 1] if 1 <= self.weekday <= 7 else "周?"]
        if self.sections:
            bits.append(f"第{self.sections}节")
        bits.append(self.name)
        if self.room:
            bits.append(self.room)
        if self.teacher:
            bits.append(self.teacher)
        if self.weeks:
            bits.append(f"{self.weeks}周")
        return " ".join(bits)


@dataclass
class Exam:
    name: str
    date: str = ""
    time: str = ""
    room: str = ""
    seat: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def to_line(self) -> str:
        bits = [self.name]
        when = " ".join(part for part in (self.date, self.time) if part)
        if when:
            bits.append(when)
        if self.room:
            bits.append(self.room)
        if self.seat:
            bits.append(f"座位{self.seat}")
        return " · ".join(bits)


@dataclass
class UserProfile:
    username: str = ""
    name: str = ""
    college: str = ""
    major: str = ""
    grade: str = ""

    def display(self) -> str:
        return self.name or self.username or "未登录"
