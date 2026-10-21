"""校园查询页：课表 / 考试。

两个 Tab 共用一个滚动容器，切换时重绘。数据全部来自 ``CampusService``，
失败时给的是「下一步该做什么」，不是堆栈。
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from ..campus.portal import PortalError, PortalNotConfigured, SessionExpired
from . import theme as T
from .widgets import Body, Card, Chip, GhostButton, H2, Muted, PrimaryButton, Screen, TopBar

TAB_SCHEDULE = 0
TAB_EXAMS = 1


class ScheduleScreen(Screen):
    tab_index = TAB_SCHEDULE

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._loaded = False
        self._courses = None
        self._exams = None

        bar = TopBar("校园查询", on_back=app.back)
        self.add_widget(bar)

        tabs = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        self.tab_schedule = Chip("课表")
        self.tab_schedule.bind(on_release=lambda *_: self.switch_tab(TAB_SCHEDULE))
        self.tab_exams = Chip("考试")
        self.tab_exams.bind(on_release=lambda *_: self.switch_tab(TAB_EXAMS))
        tabs.add_widget(self.tab_schedule)
        tabs.add_widget(self.tab_exams)
        tabs.add_widget(Widget())
        self.add_widget(tabs)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=0)
        self.content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(8),
            padding=[dp(1), dp(4), dp(1), dp(20)],
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.add_widget(self.scroll)

        self.refresh_button = GhostButton("刷新", height=dp(44))
        self.refresh_button.bind(on_release=lambda *_: self.load(force=True))
        self.add_widget(self.refresh_button)

    # ------------------------------------------------------------------ 生命周期
    def on_pre_enter(self, *_args) -> None:
        self._apply_tab_style()
        if not self._loaded:
            self.load()

    def switch_tab(self, index: int) -> None:
        self.tab_index = index
        self._apply_tab_style()
        self._render()

    def _apply_tab_style(self) -> None:
        for index, chip in ((TAB_SCHEDULE, self.tab_schedule), (TAB_EXAMS, self.tab_exams)):
            chip.set_active(index == self.tab_index)

    # ------------------------------------------------------------------ 加载
    def load(self, force: bool = False) -> None:
        if not self.app.campus.state.logged_in:
            self._render_message("还没登录学校账号。", "去登录", lambda: self.app.go("login"))
            return
        self._render_message("正在查…", None, None)

        def work():
            courses, exams, error = None, None, ""
            try:
                courses = self.app.campus.courses()
            except SessionExpired as exc:
                error = f"{exc}|login"
            except PortalNotConfigured as exc:
                error = f"{exc}|endpoints"
            except PortalError as exc:
                error = f"课表：{exc}|endpoints"
            try:
                exams = self.app.campus.exams()
            except (PortalError, SessionExpired):
                exams = []
            return courses, exams, error

        def done(result) -> None:
            courses, exams, error = result
            self._loaded = True
            self._courses = courses
            self._exams = exams
            self._error = error
            self._render()

        def failed(exc: Exception) -> None:
            self._render_message(f"查询失败：{exc}", "重试", lambda: self.load(force=True))

        self.app.run_bg(work, done, failed)

    # ------------------------------------------------------------------ 渲染
    def _render(self) -> None:
        error = getattr(self, "_error", "")
        if error:
            message, action = error.split("|", 1)
            if action == "login":
                self._render_message(message, "去登录", lambda: self.app.go("login"))
            elif action == "endpoints":
                self._render_message(message, "去配置接口", lambda: self.app.go("settings"))
            else:
                self._render_message(message, "重试", lambda: self.load(force=True))
            return
        if self.tab_index == TAB_SCHEDULE:
            self._render_courses()
        else:
            self._render_exams()

    def _clear(self) -> None:
        self.content.clear_widgets()
        Clock.schedule_once(lambda _dt: setattr(self.scroll, "scroll_y", 1), 0.02)

    def _render_message(self, text: str, action: str | None = None, callback=None) -> None:
        self._clear()
        card = Card(size_hint_y=None, height=dp(140), padding=[dp(16), dp(18)])
        body = Body(text, font_size=sp(14))
        body.size_hint_y = None
        body.height = dp(64)
        card.add_widget(body)
        if action and callback:
            button = PrimaryButton(action, height=dp(40))
            button.font_size = sp(14)
            button.bind(on_release=lambda *_: callback())
            card.add_widget(button)
        self.content.add_widget(card)

    def _render_courses(self) -> None:
        self._clear()
        groups = self._courses or []
        if not groups:
            self._render_message("这一周没有排课，或者教务接口还没配置。", "去配置接口", lambda: self.app.go("settings"))
            return
        for group in _course_groups(self._courses):
            header = Muted(group["day"], size_hint_y=None, height=dp(28))
            header.valign = "middle"
            self.content.add_widget(header)
            for item in group["items"]:
                self.content.add_widget(_course_card(item))

    def _render_exams(self) -> None:
        self._clear()
        exams = self._exams or []
        if not exams:
            self._render_message("没有查到考试安排。可能还没排考，或接口没配好。", "去配置接口", lambda: self.app.go("settings"))
            return
        for exam in exams:
            card = Card(size_hint_y=None, height=dp(92), padding=[dp(14), dp(12)])
            card.add_widget(H2(exam["name"]))
            line = " · ".join(
                part for part in (exam.get("when", ""), exam.get("room", ""), exam.get("seat", "")) if part
            )
            card.add_widget(Muted(line or "时间地点待定"))
            self.content.add_widget(card)


def _course_groups(courses: list[dict]) -> list[dict]:
    """CampusService 返回的是 Course 列表，这里按天分组。

    为了不让 UI 依赖 dataclass，统一转成 dict。
    """
    buckets: dict[int, list] = {}
    for course in courses:
        buckets.setdefault(getattr(course, "weekday", 0) or 0, []).append(course)
    from ..campus.models import WEEKDAYS

    groups = []
    for weekday in sorted(buckets):
        label = WEEKDAYS[weekday - 1] if 1 <= weekday <= 7 else "未排课"
        items = []
        for course in buckets[weekday]:
            items.append({
                "name": course.name,
                "time": f"第{course.sections}节" if course.sections else "",
                "room": course.room,
                "teacher": course.teacher,
                "weeks": course.weeks,
            })
        groups.append({"day": label, "items": items})
    return groups


def _course_card(item: dict) -> Card:
    card = Card(size_hint_y=None, height=dp(84), padding=[dp(14), dp(11)])
    card.add_widget(H2(item["name"]))
    line = " · ".join(
        part for part in (item.get("time", ""), item.get("room", ""), item.get("teacher", "")) if part
    )
    card.add_widget(Muted(line or "时间地点待定"))
    return card


__all__ = ["ScheduleScreen", "TAB_SCHEDULE", "TAB_EXAMS"]
