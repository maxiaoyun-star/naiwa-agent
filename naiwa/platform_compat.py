"""Android 13–17 的兼容层。

需要处理的平台变化（按 Android 版本）：

* **13 (API 33)**：`READ_EXTERNAL_STORAGE` 失效，`/sdcard` 不可随便读 → 只用 App 私有目录
  与自己的外部私有目录（`Android/data/<pkg>/files`，无需任何权限）。
* **14 (API 34)**：前台服务需要声明类型（本项目不用服务，无影响）；隐式 Intent 受限（不用）。
* **15 (API 35)**：**强制 edge-to-edge** —— 只要 targetSdk ≥ 35，界面就会画到状态栏和
  导航栏底下，必须自己让出安全区，否则标题被状态栏压住。
* **16 (API 36)**：16 KB 内存页设备普及，原生库必须按 16 KB 对齐链接
  （见 `scripts/build_llama_android.sh` 里的 `max-page-size=16384`），否则装上就崩。
* **17 (API 37)**：延续 edge-to-edge + 16 KB 页，行为同 16。

因此这里用 jnius 读真实的系统栏高度（不猜），失败就返回 0，退化成 Kivy 默认布局 ——
宁可界面紧一点，也不要因为拿不到 insets 而崩溃。
"""

from __future__ import annotations

import os

_cached: tuple[float, float] | None = None


def is_android() -> bool:
    return bool(os.environ.get("ANDROID_PRIVATE")) or "ANDROID_ARGUMENT" in os.environ


def _dp(px: float, density: float) -> float:
    if not density or density <= 0:
        return float(px)
    return round(float(px) / float(density), 1)


def insets_dp() -> tuple[float, float]:
    """返回 (状态栏高度 dp, 导航栏高度 dp)。非 Android 或读取失败返回 (0, 0)。"""
    global _cached
    if _cached is not None:
        return _cached
    if not is_android():
        _cached = (0.0, 0.0)
        return _cached

    try:
        from jnius import autoclass  # type: ignore

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        resources = activity.getResources()
        metrics = resources.getDisplayMetrics()
        density = float(metrics.density)

        decor = activity.getWindow().getDecorView()
        insets = decor.getRootWindowInsets()
        if insets is None:
            _cached = (0.0, 0.0)
            return _cached

        types = autoclass("android.view.WindowInsets$Type")
        system_bars = insets.getInsets(types.systemBars())
        top = float(system_bars.top)
        bottom = float(system_bars.bottom)
        _cached = (_dp(top, density), _dp(bottom, density))
        return _cached
    except Exception:  # noqa: BLE001 - 任何 Java 侧差异都不能让 App 起不来
        _cached = (0.0, 0.0)
        return _cached


def set_light_system_bars() -> None:
    """白底界面配深色状态栏图标（Android 6+ 的 SYSTEM_UI_FLAG_LIGHT_STATUS_BAR）。"""
    if not is_android():
        return
    try:
        from jnius import autoclass  # type: ignore

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        decor = activity.getWindow().getDecorView()
        view = autoclass("android.view.View")
        flag = int(view.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR)
        if hasattr(view, "SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR"):
            flag |= int(view.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR)
        decor.setSystemUiVisibility(int(decor.getSystemUiVisibility()) | flag)
    except Exception:  # noqa: BLE001
        pass


def reset_cache() -> None:
    """测试用：清掉缓存。"""
    global _cached
    _cached = None
