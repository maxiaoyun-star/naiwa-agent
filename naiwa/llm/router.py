"""模型路由：本地优先 → 云端兜底 → 模板兜底。

UI 只跟这个类打交道，不关心背后是哪个后端。任何一层失败都不应该让对话中断，
这是「手机上必须能用的智能体」最基本的可靠性要求。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import config, defaults
from .base import ChatProvider, GenerationConfig, Message, ProviderError, TokenCallback
from .local_gguf import LocalGGUFProvider, default_threads
from .remote import build_from_settings

MODE_AUTO = "auto"
MODE_LOCAL = "local"
MODE_REMOTE = "remote"
MODE_LABELS = {MODE_AUTO: "自动", MODE_LOCAL: "仅本地", MODE_REMOTE: "仅云端"}


@dataclass
class RouteResult:
    text: str
    provider_label: str
    kind: str  # local | remote | template


class LLMRouter:
    def __init__(self, settings, secrets) -> None:
        self.settings = settings
        self.secrets = secrets
        self._lock = threading.RLock()
        self._local: LocalGGUFProvider | None = None
        self._local_error = ""
        self._remote: ChatProvider | None = None
        self._model_path: Path | None = None
        self.reload()

    # ------------------------------------------------------------------ 配置
    def reload(self) -> None:
        with self._lock:
            self._remote = build_from_settings(self.settings, self.secrets)
            mode = self.settings.get("llm_mode", MODE_AUTO)
            if mode == MODE_AUTO or mode == MODE_LOCAL:
                self._prepare_local()

    def model_path(self) -> Path | None:
        return config.find_model(defaults.MODEL_FILENAME)

    def _prepare_local(self) -> None:
        path = self.model_path()
        if path is None:
            self._local = None
            self._model_path = None
            self._local_error = "没找到模型文件"
            return
        if self._local is not None and self._model_path == path:
            return
        self._local = LocalGGUFProvider(
            path,
            n_ctx=int(self.settings.get("local_n_ctx", defaults.DEFAULT_N_CTX)),
            n_threads=int(self.settings.get("local_n_threads", default_threads())),
            max_tokens=int(self.settings.get("max_tokens", defaults.DEFAULT_MAX_TOKENS)),
        )
        self._model_path = path

    def load_local(self, on_progress: Callable[[str], None] | None = None) -> bool:
        """在后台线程里加载模型；返回是否可用。"""
        with self._lock:
            self._prepare_local()
            if self._local is None:
                return False
            if self._local.available():
                return True
            if on_progress:
                on_progress("正在加载本地模型…")
            ok = self._local.load()
            if not ok:
                self._local_error = self._local.last_error
            return ok

    # ------------------------------------------------------------------ 状态
    @property
    def local_error(self) -> str:
        return self._local_error

    def local_ready(self) -> bool:
        return self._local is not None and self._local.available()

    def remote_ready(self) -> bool:
        return self._remote is not None and self._remote.available()

    def status(self) -> tuple[str, str]:
        """返回 (短标签, 说明)，给界面右上角用。"""
        mode = self.settings.get("llm_mode", MODE_AUTO)
        if mode == MODE_LOCAL:
            return ("本地", "只用本地模型") if self.local_ready() else ("本地未就绪", self._local_error or "模型未加载")
        if mode == MODE_REMOTE:
            return ("API", self._remote.describe()) if self.remote_ready() else ("API 未配置", "去设置里填 API Key")
        if self.local_ready():
            return "本地", "本地模型已就绪，断网也能聊"
        if self.remote_ready():
            return "API", "本地不可用，已切到云端"
        return "离线", self._local_error or "没有可用模型"

    # ------------------------------------------------------------------ 生成
    def generate(
        self,
        messages: list[Message],
        *,
        on_token: TokenCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
        config_override: GenerationConfig | None = None,
    ) -> RouteResult:
        mode = self.settings.get("llm_mode", MODE_AUTO)
        config = config_override or GenerationConfig(
            temperature=float(self.settings.get("temperature", defaults.DEFAULT_TEMPERATURE)),
            top_p=defaults.DEFAULT_TOP_P,
            max_tokens=int(self.settings.get("max_tokens", defaults.DEFAULT_MAX_TOKENS)),
        )

        # 1) 本地
        if mode in (MODE_AUTO, MODE_LOCAL) and self.local_ready():
            try:
                text = self._local.generate(messages, config, on_token, should_stop)
                if text:
                    return RouteResult(text, "本地模型", "local")
            except ProviderError as exc:
                self._local_error = str(exc)
                if mode == MODE_LOCAL:
                    raise

        # 2) 云端
        if mode in (MODE_AUTO, MODE_REMOTE) and self.remote_ready():
            try:
                text = self._remote.generate(messages, config, on_token, should_stop)
                if text:
                    return RouteResult(text, self._remote.describe(), "remote")
            except ProviderError:
                if mode == MODE_REMOTE:
                    raise

        # 3) 兜底：交给上层用模板回复
        detail = self._local_error if not self.local_ready() else "模型没有返回内容"
        raise ProviderError(f"当前没有可用的模型：{detail}", retryable=True)
