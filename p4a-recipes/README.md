# p4a 本地配方目录

这里放 python-for-android 的本地 recipe。当前为空占位：Kivy 与标准库都走官方 recipe，
llama.cpp 不通过 p4a recipe 构建，而是由 `scripts/build_llama_android.sh` 直接用 NDK
交叉编译成 `libs/arm64-v8a/libllama.so`，再由 `buildozer.spec` 的
`android.add_libs_arm64_v8a` 打进 APK。

好处：原生库和 Python 打包解耦，编译失败不会拖垮整个 APK 构建。

如果以后要给 llama.cpp 加 p4a recipe，放在这个目录下即可（buildozer.spec 已配置
`p4a.local_recipes = p4a-recipes`）。本目录只放说明文件时 p4a 不会报错。
