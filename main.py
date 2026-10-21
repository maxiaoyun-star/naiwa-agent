"""奶娃 Agent 启动入口。

buildozer 会把 ``main.py`` 作为 APK 的入口脚本，所以这里保持极简：
只做 sys.path 兜底和 App 启动。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from naiwa.app import NaiwaApp  # noqa: E402

if __name__ == "__main__":
    NaiwaApp().run()
