"""应用级常量与路径解析。

所有路径都在运行时计算，桌面调试和 Android 打包共用同一份代码：
python-for-android 启动时会设置 ``ANDROID_PRIVATE``（形如
``/data/user/0/com.naiwa.naiwaagent/files``），用它作为私有根目录即可，
不需要额外依赖（不用 plyer、不用 jnius）。
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "奶娃Agent"
APP_NAME_EN = "Naiwa Agent"
APP_ID = "com.naiwa.naiwaagent"
VERSION = "0.2.3"
BUILD_STAGE = "创意赛参赛版"
# 兼容区间，同时用于「关于」页展示
ANDROID_MIN_API = 33   # Android 13
ANDROID_MAX_API = 37   # Android 17

# ------------------------------------------------------------------ 校园系统
CAS_BASE = "https://mysso.cust.edu.cn/cas"
CAS_LOGIN = CAS_BASE + "/login"
CAS_CAPTCHA = CAS_BASE + "/captcha"
# CAS 登录成功后回调的门户地址（即 service 参数）
PORTAL_SERVICE = "https://portal.cust.edu.cn/custp/shiro-cas"
PORTAL_BASE = "https://portal.cust.edu.cn"
PORTAL_HOME = PORTAL_BASE + "/custp/"

# 登录失败时页面里可能出现的提示，用于判断结果
CAS_ERROR_HINTS = (
    "用户名或密码错误",
    "密码错误",
    "验证码错误",
    "验证码不正确",
    "账号或密码",
    "登录失败",
    "用户不存在",
    "账号被锁定",
    "Invalid credentials",
    "Authentication failed",
)

# 网络
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; NAIWA) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
HTTP_TIMEOUT = 20
HTTP_TIMEOUT_LONG = 60


# ------------------------------------------------------------------ 路径
def is_android() -> bool:
    """是否运行在 python-for-android 打包环境里。"""
    return bool(os.environ.get("ANDROID_PRIVATE")) or "ANDROID_ARGUMENT" in os.environ


def data_dir() -> Path:
    """应用私有目录，卸载 App 时随之删除。"""
    root = os.environ.get("ANDROID_PRIVATE")
    if root:
        path = Path(root)
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".local" / "share"
        path = base / "naiwa-agent"
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "settings.json"


def session_path() -> Path:
    return data_dir() / "session.enc"


def device_key_path() -> Path:
    return data_dir() / ".device_key"


def history_path() -> Path:
    return data_dir() / "history.json"


def asset_dir() -> Path:
    """随 APK 一起打包的只读资源目录。"""
    return Path(__file__).resolve().parent.parent / "assets"


def model_search_paths(filename: str) -> list[Path]:
    """模型文件的查找顺序。

    1. 应用私有目录（App 内下载 / 首次导入的位置）
    2. 应用自己的外部私有目录（数据线 adb push 进来最方便的位置，**不需要任何权限**）

    Android 13 起 `/sdcard` 与 `/sdcard/Download` 已经无法直接读取（分区存储），
    所以刻意不再往那里找 —— 找不到还多耗一次 IO，还会误导用户。
    """
    candidates = [models_dir() / filename]
    if is_android():
        candidates += [
            Path("/storage/emulated/0/Android/data") / APP_ID / "files" / "models" / filename,
            Path("/sdcard/Android/data") / APP_ID / "files" / "models" / filename,
        ]
    else:
        candidates += [
            Path.home() / "Downloads" / filename,
            Path.home() / ".cache" / "naiwa" / filename,
        ]
    return candidates


def find_model(filename: str) -> Path | None:
    for candidate in model_search_paths(filename):
        try:
            if candidate.is_file() and candidate.stat().st_size > 32 * 1024 * 1024:
                return candidate
        except OSError:
            continue
    return None


def human_size(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"
