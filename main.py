"""奶娃 Agent 启动入口。

buildozer 会把 ``main.py`` 作为 APK 的入口脚本，所以这里保持极简：
只做 sys.path 兜底、faulthandler 兜底和 App 启动。
"""

from __future__ import annotations

import faulthandler
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 原生崩溃（SIGSEGV/SIGABRT）不会走 Python 的 excepthook，
# 但只要开了 faulthandler，就能把当时的 Python 栈写进 crash.log。
# 安卓上没有控制台，这是排查「点一下就闪退」的唯一线索来源。
try:
    from naiwa import config

    _crash = open(config.logs_dir() / "native.log", "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(file=_crash, all_threads=True)
except Exception:  # noqa: BLE001
    pass

from naiwa.app import NaiwaApp  # noqa: E402

if __name__ == "__main__":
    NaiwaApp().run()
