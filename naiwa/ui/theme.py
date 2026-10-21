"""纯白主题：颜色、字号、字体注册。

界面刻意不引入 KivyMD 之类的组件库 —— 全部用 Kivy 原生 canvas 手绘，
好处是 APK 体积小、启动快、样式完全可控（纯白 + 细线 + 单一近黑强调色）。
"""

from __future__ import annotations

import os
from pathlib import Path

from kivy.core.text import LabelBase
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

from .. import config

# ------------------------------------------------------------------ 颜色
HEX = {
    "bg": "#FFFFFF",          # 页面底色，纯白
    "surface": "#FFFFFF",     # 卡片
    "surface_alt": "#F6F7F8", # 次级块（气泡、chip）
    "line": "#ECEDEF",        # 分割线 / 卡片描边
    "text": "#16181A",        # 主文字
    "muted": "#8A9099",       # 次要文字
    "faint": "#B9BEC5",       # 占位符
    "accent": "#121417",      # 强调（近黑，主按钮 / 自己发的气泡）
    "accent_text": "#FFFFFF",
    "ok": "#128A4E",
    "warn": "#B45309",
    "error": "#C0392B",
}


def c(name: str) -> list[float]:
    return get_color_from_hex(HEX[name])


BG = c("bg")
SURFACE = c("surface")
SURFACE_ALT = c("surface_alt")
LINE = c("line")
TEXT = c("text")
MUTED = c("muted")
FAINT = c("faint")
ACCENT = c("accent")
ACCENT_TEXT = c("accent_text")
OK = c("ok")
WARN = c("warn")
ERROR = c("error")

# ------------------------------------------------------------------ 间距 / 圆角
PAD = dp(16)
PAD_S = dp(8)
PAD_L = dp(24)
RADIUS = dp(16)
RADIUS_S = dp(10)

FONT_REGULAR = "Roboto"
FONT_BOLD = "Roboto"
FONT_NAME = "NaiwaCJK"

_CJK_CANDIDATES = (
    # 随包的字体（推荐，放 assets/fonts/ 下自动生效）
    "assets/fonts/NotoSansSC-Regular.ttf",
    "assets/fonts/NotoSansSC.ttf",
    "assets/fonts/SourceHanSansSC-Regular.otf",
    # Android 系统自带的中文字体（TTC 也能被 SDL_ttf 读取）
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/DroidSansChinese.ttf",
)

_registered: str | None = None


def register_fonts() -> str | None:
    """注册中文字体，返回可用的字体名（失败返回 None，界面跟系统默认字体）。

    必须在创建任何 Label 之前调用。
    """
    global _registered, FONT_REGULAR, FONT_BOLD
    if _registered is not None:
        return _registered or None

    root = Path(config.__file__).resolve().parent.parent
    found: Path | None = None
    for rel in _CJK_CANDIDATES:
        candidate = Path(rel) if os.path.isabs(rel) else root / rel
        if candidate.is_file():
            found = candidate
            break

    if found is None:
        _registered = ""
        return None

    try:
        LabelBase.register(
            name=FONT_NAME,
            fn_regular=str(found),
            fn_bold=str(found),
        )
    except Exception:  # noqa: BLE001 - 字体坏了也不能让 App 起不来
        _registered = ""
        return None

    _registered = FONT_NAME
    FONT_REGULAR = FONT_NAME
    FONT_BOLD = FONT_NAME
    return FONT_NAME


def apply_window() -> None:
    """窗口级设置：白底、软键盘不遮挡输入框、深色状态栏图标。"""
    from kivy.core.window import Window

    Window.clearcolor = BG
    try:
        Window.softinput_mode = "below_target"
    except Exception:  # noqa: BLE001
        pass

    # Android 15+ 强制 edge-to-edge：白底配深色状态栏图标，否则时间/电量看不见
    try:
        from .. import platform_compat

        platform_compat.set_light_system_bars()
    except Exception:  # noqa: BLE001
        pass


def tr_color(name: str, alpha: float = 1.0) -> list[float]:
    color = list(c(name))
    if len(color) == 4:
        color[3] = alpha
    else:
        color.append(alpha)
    return color


__all__ = [
    "HEX", "BG", "SURFACE", "SURFACE_ALT", "LINE", "TEXT", "MUTED", "FAINT",
    "ACCENT", "ACCENT_TEXT", "OK", "WARN", "ERROR",
    "PAD", "PAD_S", "PAD_L", "RADIUS", "RADIUS_S",
    "dp", "sp", "c", "tr_color", "register_fonts", "apply_window",
    "FONT_REGULAR", "FONT_BOLD", "FONT_NAME",
]
