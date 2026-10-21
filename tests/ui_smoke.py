"""UI 冒烟测试：把 5 个页面都构造出来，不进入事件循环。

用途：在没有安卓真机的情况下，尽早暴露 Kivy 控件参数写错、布局绑定炸掉这类问题。
不放进 ``discover`` 的自动发现范围（文件名不以 test_ 开头），因为它需要 Kivy 和一个
可用的窗口 provider。

跑法::

    # Windows / Linux 桌面
    python tests/ui_smoke.py

    # 无显示器（CI）时可以试 dummy 视频驱动
    SDL_VIDEODRIVER=dummy python tests/ui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "0")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    # 让所有数据写到临时目录，别污染开发机的 AppData
    sandbox = tempfile.mkdtemp(prefix="naiwa-smoke-")
    os.environ["ANDROID_PRIVATE"] = sandbox

    try:
        import kivy  # noqa: F401
    except ImportError:
        print("SKIP: 没有安装 Kivy（pip install kivy 后再跑）")
        return 0

    print(f"Kivy {kivy.__version__} · data={sandbox}")
    try:
        from naiwa.app import NaiwaApp
        from naiwa.ui import theme as T
    except Exception:
        traceback.print_exc()
        print("FAIL: 导入阶段就挂了")
        return 1

    # 字体：没有中文字体也能跑，只是显示方块
    print("→ 注册字体:", T.register_fonts())
    try:
        T.apply_window()
    except Exception as exc:  # noqa: BLE001
        print(f"! apply_window 失败（无窗口环境可忽略）：{exc}")

    app = NaiwaApp()
    try:
        root = app.build()
    except Exception:
        traceback.print_exc()
        print("FAIL: build() 抛异常")
        return 1

    screens = list(root.screen_names)
    print("→ 页面:", screens)
    expected = {"home", "chat", "schedule", "login", "settings"}
    missing = expected - set(screens)
    if missing:
        print("FAIL: 缺页面", missing)
        return 1

    # 逐个进入，触发 on_pre_enter / on_enter
    for name in screens:
        try:
            root.current = name
        except Exception:
            traceback.print_exc()
            print(f"FAIL: 切到 {name} 失败")
            return 1
        print(f"   ok  {name}")

    # 聊天气泡 + 状态胶囊
    try:
        chat = root.get_screen("chat")
        bubble = chat.add_bubble("测试消息", mine=True)
        bubble.set_text("测试消息（变长一点，看看换行和高度是否跟着走）")
        chat.send("你好")  # 会走后台线程 + 降级回复
        home = root.get_screen("home")
        home._refresh()
        settings = root.get_screen("settings")
        settings._refresh()
    except Exception:
        traceback.print_exc()
        print("FAIL: 交互冒烟失败")
        return 1

    print("PASS: 全部页面构造并渲染完成")
    app.stop()  # build() 里挂了 Clock 事件，停掉避免退出时报警告
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
