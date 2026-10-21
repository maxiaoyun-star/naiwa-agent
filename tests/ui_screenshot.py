"""把界面渲染成图片，用于人工检查纯白风格与布局。

需要已安装 Kivy，并且需要一个能创建窗口的环境（桌面直接跑即可）。
截图默认输出到 ``screenshots/``。

跑法::

    python tests/ui_screenshot.py
    NAIWA_FONT=C:\\Windows\\Fonts\\msyh.ttc python tests/ui_screenshot.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHOTS = [
    ("home", "home.png"),
    ("chat", "chat.png"),
    ("schedule", "schedule.png"),
    ("login", "login.png"),
    ("settings", "settings.png"),
]


def main() -> int:
    os.environ["ANDROID_PRIVATE"] = tempfile.mkdtemp(prefix="naiwa-shot-")
    os.environ.setdefault("NAIWA_FONT", r"C:\Windows\Fonts\msyh.ttc")

    from kivy.clock import Clock
    from kivy.core.window import Window

    from naiwa.app import NaiwaApp

    out = ROOT / "screenshots"
    out.mkdir(exist_ok=True)

    class ShotApp(NaiwaApp):
        def on_start(self) -> None:  # noqa: D401
            Window.size = (400, 860)
            delay = 1.8
            for name, filename in SHOTS:
                Clock.schedule_once(lambda _dt, n=name: self._goto(n), delay)
                Clock.schedule_once(lambda _dt, f=filename: self._shot(f), delay + 0.6)
                delay += 0.9
            Clock.schedule_once(lambda _dt: self.stop(), delay + 0.6)

        def _goto(self, name: str) -> None:
            try:
                self.sm.current = name
            except Exception as exc:  # noqa: BLE001
                print(f"切页失败 {name}: {exc}")

        def _shot(self, filename: str) -> None:
            path = out / filename
            try:
                Window.screenshot(name=str(path))
                print(f"✓ {path}")
            except Exception as exc:  # noqa: BLE001
                print(f"✗ {path}: {exc}")

    ShotApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
