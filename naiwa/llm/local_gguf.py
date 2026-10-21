"""本地 GGUF 推理。

两条后端，按优先级自动选择：

1. **libnaiwa_llama.so**（推荐，Android 用这个）
   见 ``native/naiwa_llama.c``。ctypes 只接触 4 个我自己定义的稳定函数，
   llama.cpp 的结构体布局变化全被 C 层吸收掉了。

2. **llama-cpp-python**（桌面调试方便）
   ``pip install llama-cpp-python`` 后可直接用，不装也不影响 App 启动。

两者都不可用时，``available()`` 返回 False，上层自动降级到云端或模板回复 ——
这一点很关键：本地模型挂了不能让整个 App 不能用。
"""

from __future__ import annotations

import codecs
import ctypes
import os
import platform
import sys
import threading
from pathlib import Path
from typing import Callable, Iterable

from .base import (
    ChatProvider,
    GenerationConfig,
    Message,
    ProviderError,
    TokenCallback,
    chatml,
)

_TOKEN_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)


def _lib_names() -> list[str]:
    system = platform.system().lower()
    if system == "windows":
        return ["naiwa_llama.dll", "libnaiwa_llama.dll"]
    if system == "darwin":
        return ["libnaiwa_llama.dylib"]
    return ["libnaiwa_llama.so"]


def _candidate_lib_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent.parent
    dirs = [
        here / "native" / "build",
        here / "libs" / "arm64-v8a",
        here / "assets" / "lib",
    ]
    private = os.environ.get("ANDROID_PRIVATE")
    if private:
        # /data/user/0/<pkg>/files -> /data/user/0/<pkg>
        pkg_root = Path(private).parent.parent
        dirs += [pkg_root / "lib", pkg_root / "lib" / "arm64"]
    return dirs


class _ShimBackend:
    """libnaiwa_llama.so 的 ctypes 绑定。"""

    name = "libnaiwa_llama"

    def __init__(self, model_path: Path, n_ctx: int, n_threads: int) -> None:
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._lib = None
        self._handle = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 加载
    def _load_library(self) -> ctypes.CDLL:
        errors: list[str] = []
        for name in _lib_names():
            try:
                return ctypes.CDLL(name)
            except OSError as exc:  # noqa: PERF203
                errors.append(f"{name}: {exc}")
        for folder in _candidate_lib_dirs():
            for name in _lib_names():
                candidate = folder / name
                if candidate.is_file():
                    try:
                        return ctypes.CDLL(str(candidate))
                    except OSError as exc:  # noqa: PERF203
                        errors.append(f"{candidate}: {exc}")
        raise ProviderError("找不到本地推理库（libnaiwa_llama）\n" + "\n".join(errors[:3]))

    def open(self) -> None:
        lib = self._load_library()
        lib.naiwa_backend_init.argtypes = []
        lib.naiwa_backend_init.restype = None
        lib.naiwa_load.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.naiwa_load.restype = ctypes.c_void_p
        lib.naiwa_free.argtypes = [ctypes.c_void_p]
        lib.naiwa_free.restype = None
        lib.naiwa_generate.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_float,
            ctypes.c_float, ctypes.c_int, ctypes.c_int, _TOKEN_CB,
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
        ]
        lib.naiwa_generate.restype = ctypes.c_int
        lib.naiwa_backend_init()

        handle = lib.naiwa_load(str(self.model_path).encode("utf-8"), int(self.n_threads))
        if not handle:
            raise ProviderError("模型加载失败：文件损坏或内存不足")
        self._lib = lib
        self._handle = handle

    # ------------------------------------------------------------------ 推理
    def complete(
        self,
        prompt: str,
        config: GenerationConfig,
        on_token: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        if self._lib is None or self._handle is None:
            raise ProviderError("本地模型未加载")

        pieces: list[str] = []
        decoder = codecs.getincrementaldecoder("utf-8")("ignore")
        stop_flag = {"stop": False}

        def _callback(piece_ptr, _user) -> int:
            if should_stop is not None and should_stop():
                stop_flag["stop"] = True
                return 1
            raw = ctypes.cast(piece_ptr, ctypes.c_char_p).value or b""
            text = decoder.decode(raw)
            if text:
                pieces.append(text)
                if on_token is not None:
                    on_token(text)
            return 0

        c_cb = _TOKEN_CB(_callback)
        err = ctypes.create_string_buffer(512)

        with self._lock:
            rc = self._lib.naiwa_generate(
                self._handle,
                prompt.encode("utf-8"),
                int(config.max_tokens),
                float(config.temperature),
                float(config.top_p),
                int(self.n_ctx),
                int(self.n_threads),
                c_cb,
                None,
                err,
                len(err),
            )
        tail = decoder.decode(b"", final=True)
        if tail:
            pieces.append(tail)

        if rc != 0:
            message = err.value.decode("utf-8", "ignore") or "本地推理失败"
            raise ProviderError(message)
        return "".join(pieces).strip()

    def close(self) -> None:
        with self._lock:
            if self._lib is not None and self._handle:
                try:
                    self._lib.naiwa_free(self._handle)
                except OSError:
                    pass
            self._handle = None


class _LlamaCppBackend:
    """llama-cpp-python 后端（桌面调试用）。"""

    name = "llama-cpp-python"

    def __init__(self, model_path: Path, n_ctx: int, n_threads: int) -> None:
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._llm = None
        self._lock = threading.Lock()

    def open(self) -> None:
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError as exc:
            raise ProviderError("没有 llama-cpp-python") from exc
        try:
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=256,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"模型加载失败：{exc}") from exc

    def complete(
        self,
        prompt: str,
        config: GenerationConfig,
        on_token: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        if self._llm is None:
            raise ProviderError("本地模型未加载")
        out: list[str] = []
        with self._lock:
            stream = self._llm(
                prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                stop=["<|im_end|>", "<|endoftext|>"],
                stream=True,
            )
            for chunk in stream:
                if should_stop is not None and should_stop():
                    break
                piece = (chunk.get("choices") or [{}])[0].get("text", "")
                if piece:
                    out.append(piece)
                    if on_token is not None:
                        on_token(piece)
        return "".join(out).strip()

    def close(self) -> None:
        self._llm = None


class LocalGGUFProvider(ChatProvider):
    kind = "local"

    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 2048,
        n_threads: int = 4,
        max_tokens: int = 512,
    ) -> None:
        self.model_path = Path(model_path)
        self.n_ctx = int(n_ctx)
        self.n_threads = max(1, int(n_threads))
        self.default_max_tokens = int(max_tokens)
        self.name = "本地模型"
        self.model_label = self.model_path.name
        self._backend = None
        self._error = ""
        self._loading = False

    # ------------------------------------------------------------------ 状态
    def available(self) -> bool:
        return self._backend is not None

    @property
    def last_error(self) -> str:
        return self._error

    def describe(self) -> str:
        return f"本地 · {self.model_path.name}"

    # ------------------------------------------------------------------ 生命周期
    def load(self) -> bool:
        """同步加载模型。失败返回 False，原因见 ``last_error``。"""
        if self._backend is not None:
            return True
        self._loading = True
        errors: list[str] = []
        try:
            for factory in (_ShimBackend, _LlamaCppBackend):
                backend = factory(self.model_path, self.n_ctx, self.n_threads)
                try:
                    backend.open()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{factory.name}: {exc}")
                    continue
                self._backend = backend
                self._error = ""
                return True
            self._error = "；".join(errors) or "未知错误"
            return False
        finally:
            self._loading = False

    def close(self) -> None:
        if self._backend is not None:
            try:
                self._backend.close()
            finally:
                self._backend = None

    # ------------------------------------------------------------------ 推理
    def generate(
        self,
        messages: Iterable[Message],
        config: GenerationConfig | None = None,
        on_token: TokenCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        if self._backend is None:
            raise ProviderError(self._error or "本地模型未加载")
        config = config or GenerationConfig(max_tokens=self.default_max_tokens)
        prompt = chatml(messages)
        return self._backend.complete(prompt, config, on_token, should_stop)


def default_threads() -> int:
    """按 CPU 核数给个保守值：手机上 4 线程通常比 8 线程更省电也更快。"""
    try:
        cores = os.cpu_count() or 4
    except NotImplementedError:
        cores = 4
    return max(2, min(4, cores // 2))
