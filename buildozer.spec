[app]
# 应用名（会显示在桌面上）
title = 奶娃Agent
package.name = naiwaagent
package.domain = com.naiwa

source.dir = .
# 打包进 APK 的资源类型（模型 .gguf 故意不在这里，运行时下载/导入）
source.include_exts = py,png,jpg,kv,ttf,json,md,txt,otf
source.exclude_dirs = tests,docs,.github,probe,__pycache__,build,dist,.venv
source.exclude_patterns = *.pyc,notice_*.txt,read_*_docx.py,deep_dump_docx.py

version = 0.1.0

# 纯 Python 依赖，刻意保持最少：只有 Kivy。
# cryptography / requests 都不引入，加密与网络全部用标准库实现，降低 CI 编译失败概率。
requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0
# 让输入框在软键盘弹出时上移，聊天界面必需
android.softinput_mode = below_target
icon.filename = %(source.dir)s/assets/icon.png

# 读写模型文件、联网
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# 端侧推理只需要 arm64；同时构建 arm64 可覆盖 2019 年后几乎所有国产安卓机
android.archs = arm64-v8a
android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24

# llama.cpp 的预编译产物（由 scripts/build_llama_android.sh 或 CI 生成）
# 若目录为空，buildozer 会警告但不会中断构建，App 自动降级为 API 模式。
android.add_libs_arm64_v8a = libs/arm64-v8a/*.so

android.entrypoint = org.kivy.android.PythonActivity
android.logcat_filters = *:S python:D
android.release_artifact = apk

p4a.branch = master
p4a.local_recipes = p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
