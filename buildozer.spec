[app]
# 应用名（会显示在桌面上）
title = 奶娃Agent
package.name = naiwaagent
package.domain = com.naiwa

source.dir = .
# 打包进 APK 的资源类型（模型 .gguf 故意不在这里，运行时下载/导入）
source.include_exts = py,png,jpg,kv,ttf,json,md,txt,otf
source.exclude_dirs = tests,docs,.github,probe,__pycache__,build,dist,.venv,.venv-uitest,native
source.exclude_patterns = *.pyc,notice_*.txt,read_*_docx.py,deep_dump_docx.py,*.part

version = 0.2.3

# 纯 Python 依赖，刻意保持最少：只有 Kivy。
# cryptography / requests 都不引入，加密与网络全部用标准库实现，降低 CI 编译失败概率。
# 不写死 kivy 版本：交给 python-for-android 的 recipe 选它自己验证过的版本。
requirements = python3,kivy

orientation = portrait
fullscreen = 0
# 让输入框在软键盘弹出时上移，聊天界面必需
android.softinput_mode = below_target
icon.filename = %(source.dir)s/assets/icon.png

# 目标：Android 13 (API 33) ~ Android 17 (API 37) 全兼容。
# 只保留 INTERNET：从 Android 13 起读写 /sdcard 已无意义，模型只放在 App 私有目录
# 或它自己的 Android/data/<包名>/files 里，这两个位置都不需要权限。
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# 端侧推理只需要 arm64；同时构建 arm64 可覆盖 2019 年后几乎所有国产安卓机
android.archs = arm64-v8a
# compileSdk / targetSdk。先用 34：python-for-android 的 gradle 模板对 34 支持最成熟，
# 34 的 APK 在 Android 13–17 上都能装能跑。想跟到 36/37 时改这里，
# 并同步 naiwa/config.py 的 ANDROID_MAX_API（CI 会跑一次验证）。
android.api = 34
# Android 13 = API 33，作为最低支持版本
android.minapi = 33
# NDK 用 25b：与 python-for-android 的兼容性最稳，且它自带 API 33 平台头文件。
# 16 KB 页对齐靠链接参数（scripts/build_llama_android.sh 里的 max-page-size），
# 不依赖 NDK 版本，所以没必要为了 16 KB 页去换 r27/r28。
android.ndk = 25b
android.ndk_api = 33
android.accept_sdk_license = True

# llama.cpp 的预编译产物（由 scripts/build_llama_android.sh 或 CI 生成）。
# CI 在没有 .so 时会自动删掉这一行，避免 p4a 因为空目录/不存在的目录直接失败。
android.add_libs_arm64_v8a = libs/arm64-v8a/*.so



[buildozer]
log_level = 2
warn_on_root = 1
