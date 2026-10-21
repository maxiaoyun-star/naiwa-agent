#!/usr/bin/env bash
# 用 Android NDK 交叉编译 llama.cpp + 奶娃的 C 薄封装，产出 libs/arm64-v8a/*.so。
#
# 用法：
#   export ANDROID_NDK_HOME=/path/to/ndk/25.2.9519653
#   scripts/build_llama_android.sh
#
# 环境变量：
#   LLAMA_CPP_TAG   要构建的 llama.cpp 版本，默认 master。**建议固定成某个 release tag**，
#                   否则上游改了 C API，native/naiwa_llama.c 可能要跟着改。
#   ABI             目标架构，默认 arm64-v8a
#   ANDROID_API     最低 API level，默认 24
#
# 产物：libs/arm64-v8a/libnaiwa_llama.so 以及它依赖的 libllama.so / libggml*.so。
# buildozer 的 android.add_libs_arm64_v8a 会把整个目录打进 APK。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LLAMA_CPP_REPO="${LLAMA_CPP_REPO:-https://github.com/ggml-org/llama.cpp.git}"
LLAMA_CPP_TAG="${LLAMA_CPP_TAG:-master}"
ABI="${ABI:-arm64-v8a}"
# 与 buildozer.spec 的 android.ndk_api 保持一致：Android 13 (API 33) 起
ANDROID_API="${ANDROID_API:-33}"
WORK_DIR="${WORK_DIR:-build/llama-android}"
OUT_DIR="$REPO_ROOT/libs/$ABI"

NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}"
if [ -z "$NDK" ] || [ ! -d "$NDK" ]; then
  echo "✗ 找不到 NDK。请设置 ANDROID_NDK_HOME 指向 NDK 目录（例如 .../ndk/25.2.9519653）。" >&2
  exit 1
fi
echo "NDK      : $NDK"
echo "llama.cpp: $LLAMA_CPP_TAG"
echo "ABI      : $ABI (android-$ANDROID_API)"

# ---------------------------------------------------------------- 1. 源码
SRC_DIR="$WORK_DIR/llama.cpp"
if [ ! -d "$SRC_DIR/.git" ]; then
  mkdir -p "$WORK_DIR"
  git clone --depth 1 --branch "$LLAMA_CPP_TAG" "$LLAMA_CPP_REPO" "$SRC_DIR"
else
  echo "复用已有源码：$SRC_DIR"
fi

# ---------------------------------------------------------------- 2. 编译 llama.cpp
BUILD_DIR="$WORK_DIR/build"
# 16 KB 页对齐：Android 15+ 的部分设备使用 16 KB 内存页，原生库未按 16 KB 对齐会直接崩溃。
# NDK r28 起可用 -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON；
# NDK r27 用下面这组链接参数也能达到同样效果。
PAGE_FLAGS="-Wl,-z,max-page-size=16384"
cmake -S "$SRC_DIR" -B "$BUILD_DIR" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI="$ABI" \
  -DANDROID_PLATFORM="android-$ANDROID_API" \
  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \
  -DCMAKE_SHARED_LINKER_FLAGS="$PAGE_FLAGS" \
  -DCMAKE_MODULE_LINKER_FLAGS="$PAGE_FLAGS" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DLLAMA_CURL=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=OFF \
  -DGGML_OPENMP=OFF \
  -DGGML_LLAMAFILE=OFF

cmake --build "$BUILD_DIR" --config Release -j"$(nproc 2>/dev/null || echo 4)"

# ---------------------------------------------------------------- 3. 编译 C 薄封装
HOST_TAG=""
for candidate in linux-x86_64 darwin-x86_64 windows-x86_64; do
  if [ -d "$NDK/toolchains/llvm/prebuilt/$candidate" ]; then
    HOST_TAG="$candidate"
    break
  fi
done
if [ -z "$HOST_TAG" ]; then
  echo "✗ 找不到 NDK 的 llvm toolchain" >&2
  exit 1
fi

case "$ABI" in
  arm64-v8a)   TRIPLE="aarch64-linux-android" ;;
  armeabi-v7a) TRIPLE="armv7a-linux-androideabi" ;;
  x86_64)      TRIPLE="x86_64-linux-android" ;;
  *) echo "✗ 不支持的 ABI: $ABI" >&2; exit 1 ;;
esac

CC="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/bin/${TRIPLE}${ANDROID_API}-clang"
if [ ! -x "$CC" ]; then
  echo "✗ 找不到编译器 $CC" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
# 先放依赖库，链接器才能在 -L 里找到它们
cp -f "$BUILD_DIR"/bin/lib*.so "$OUT_DIR"/ 2>/dev/null || true

echo "→ 编译 native/naiwa_llama.c"
"$CC" -shared -fPIC -O2 -std=c11 \
  -I"$SRC_DIR/include" \
  -I"$SRC_DIR/ggml/include" \
  "$REPO_ROOT/native/naiwa_llama.c" \
  -L"$BUILD_DIR/bin" -lllama -lggml -lggml-base -lggml-cpu \
  -Wl,-z,max-page-size=16384 \
  -Wl,-rpath,'$ORIGIN' \
  -lm -o "$OUT_DIR/libnaiwa_llama.so" \
  || "$CC" -shared -fPIC -O2 -std=c11 \
       -I"$SRC_DIR/include" -I"$SRC_DIR/ggml/include" \
       "$REPO_ROOT/native/naiwa_llama.c" \
       -L"$BUILD_DIR/bin" -lllama \
       -Wl,-z,max-page-size=16384 \
       -Wl,-rpath,'$ORIGIN' -lm -o "$OUT_DIR/libnaiwa_llama.so"

# 去掉调试符号，能省几 MB
STRIP="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/bin/llvm-strip"
if [ -x "$STRIP" ]; then
  "$STRIP" --strip-unneeded "$OUT_DIR"/*.so || true
fi

echo "✓ 完成，产物在 $OUT_DIR:"
ls -lh "$OUT_DIR"
