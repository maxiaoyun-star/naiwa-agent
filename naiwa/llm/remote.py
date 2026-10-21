"""OpenAI 兼容接口（国内合规厂商统一走这个协议）。

不依赖 requests：用标准库 urllib 手写 SSE 解析，好处是 Android 打包不用多编一个
依赖，坏处是要自己处理分块与超时 —— 下面都处理了。
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Callable, Iterable

from .base import ChatProvider, GenerationConfig, Message, ProviderError, TokenCallback

# 国内可用平台。base 都带 /v1 或等价前缀，拼上 /chat/completions 即可。
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "zhipu": {
        "label": "智谱 GLM",
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "hint": "在 bigmodel.cn 控制台创建 API Key",
    },
    "dashscope": {
        "label": "通义千问",
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "hint": "在阿里云百炼控制台创建 API Key",
    },
    "doubao": {
        "label": "豆包（火山方舟）",
        "base": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-pro-32k",
        "hint": "填方舟里的推理接入点 ID 作为模型名",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "hint": "在 platform.deepseek.com 创建 API Key",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容）",
        "base": "",
        "model": "",
        "hint": "填任何兼容 /chat/completions 的国内服务地址",
    },
}


class OpenAICompatibleProvider(ChatProvider):
    kind = "remote"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        name: str = "云端模型",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.name = name
        self.model_label = self.model
        self.timeout = timeout

    # ------------------------------------------------------------------ 状态
    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def describe(self) -> str:
        return f"{self.name} · {self.model}"

    # ------------------------------------------------------------------ 请求
    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def generate(
        self,
        messages: Iterable[Message],
        config: GenerationConfig | None = None,
        on_token: TokenCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        if not self.available():
            raise ProviderError("云端模型还没配置（地址 / 模型名 / API Key 缺一项）")

        config = config or GenerationConfig()
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_tokens,
            "stream": True,
        }
        if config.stop:
            payload["stop"] = config.stop

        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/event-stream",
                "User-Agent": "NaiwaAgent/0.1 (+Android)",
            },
            method="POST",
        )

        chunks: list[str] = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    if should_stop is not None and should_stop():
                        break
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except ValueError:
                        continue
                    piece = self._extract_delta(event)
                    if piece:
                        chunks.append(piece)
                        if on_token is not None:
                            on_token(piece)
        except urllib.error.HTTPError as exc:
            raise ProviderError(self._http_error_message(exc), retryable=exc.code >= 500) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"连不上模型服务：{exc.reason}", retryable=True) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderError("模型服务超时，稍后再试", retryable=True) from exc
        except OSError as exc:
            raise ProviderError(f"网络异常：{exc}", retryable=True) from exc

        text = "".join(chunks).strip()
        if not text:
            raise ProviderError("模型返回了空内容")
        return text

    # ------------------------------------------------------------------ 解析
    @staticmethod
    def _extract_delta(event: dict) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            return content
        # 少数平台在流式里用 message 字段
        message = choice.get("message") or {}
        if isinstance(message.get("content"), str):
            return message["content"]
        return ""

    @staticmethod
    def _http_error_message(exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            raw = exc.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            detail = (
                (parsed.get("error") or {}).get("message")
                or parsed.get("message")
                or raw[:200]
            )
        except Exception:  # noqa: BLE001
            detail = ""
        if exc.code == 401:
            return "API Key 无效或已过期（401）"
        if exc.code == 429:
            return "调用太频繁或额度用完（429）"
        return f"模型服务返回 {exc.code}" + (f"：{detail}" if detail else "")


def build_from_settings(settings, secrets) -> OpenAICompatibleProvider:
    """按设置里的配置造一个云端 provider（未配置时返回的对象 available() 为 False）。"""
    preset_key = settings.get("remote_provider", "zhipu") or "zhipu"
    preset = PROVIDER_PRESETS.get(preset_key, PROVIDER_PRESETS["zhipu"])
    base = (settings.get("remote_base") or "").strip() or preset["base"]
    model = (settings.get("remote_model") or "").strip() or preset["model"]
    api_key = secrets.get("remote_api_key", "")
    return OpenAICompatibleProvider(
        base_url=base,
        api_key=api_key,
        model=model,
        name=preset["label"],
    )
