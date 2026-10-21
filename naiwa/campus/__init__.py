"""校园系统接入：CAS 登录 + 教务数据。"""

from .cas import (
    CasClient,
    CasError,
    CookieJar,
    LoginChallenge,
    LoginResult,
    NeedCaptcha,
    parse_login_form,
)
from .models import WEEKDAYS, Course, Exam, UserProfile
from .portal import (
    PortalClient,
    PortalError,
    PortalNotConfigured,
    SessionExpired,
    build_client,
    parse_courses,
    parse_exams,
    parse_profile,
)

__all__ = [
    "CasClient", "CasError", "CookieJar", "LoginChallenge", "LoginResult",
    "NeedCaptcha", "parse_login_form", "Course", "Exam", "UserProfile", "WEEKDAYS",
    "PortalClient", "PortalError", "PortalNotConfigured", "SessionExpired",
    "build_client", "parse_courses", "parse_exams", "parse_profile",
]
