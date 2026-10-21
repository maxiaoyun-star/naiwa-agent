"""LLM 层：本地 GGUF / 云端 API / 路由。"""

from .base import (
    ChatProvider,
    GenerationConfig,
    Message,
    ProviderError,
    chatml,
    join_messages,
)
from .local_gguf import LocalGGUFProvider, default_threads
from .remote import PROVIDER_PRESETS, OpenAICompatibleProvider, build_from_settings
from .router import MODE_AUTO, MODE_LABELS, MODE_LOCAL, MODE_REMOTE, LLMRouter, RouteResult

__all__ = [
    "ChatProvider", "GenerationConfig", "Message", "ProviderError", "chatml",
    "join_messages", "LocalGGUFProvider", "default_threads", "PROVIDER_PRESETS",
    "OpenAICompatibleProvider", "build_from_settings", "LLMRouter", "RouteResult",
    "MODE_AUTO", "MODE_LOCAL", "MODE_REMOTE", "MODE_LABELS",
]
