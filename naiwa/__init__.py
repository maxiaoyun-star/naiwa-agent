"""奶娃 Agent 核心包。

注意：这里**不能** import kivy 或任何 UI 模块，保证核心逻辑可以在无 GUI 环境下
（单元测试、CI 的 test job）直接导入。
"""

from __future__ import annotations

from .config import APP_ID, APP_NAME, VERSION

__all__ = ["APP_NAME", "APP_ID", "VERSION"]
__version__ = VERSION
