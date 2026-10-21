"""LLM 抽象层。

统一约定：输入 ``list[Message]``，输出完整字符串；如果调用方给了 ``on_token``，
实现应当边生成边回调（UI 就能流式显示），但**仍然要返回完整文本**。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Iterable

TokenCallback = Callable[[str], None]


class ProviderError(RuntimeError):
    """LLM 调用失败。message 面向用户，可直接显示。"""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class GenerationConfig:
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512
    stop: list[str] = field(default_factory=list)


class ChatProvider(ABC):
    """所有模型后端（本地 / 云端）都实现这个接口。"""

    name: str = "provider"
    kind: str = "remote"      # local | remote
    model_label: str = ""

    @abstractmethod
    def available(self) -> bool:
        """当前是否可用（模型已加载 / API Key 已配置）。"""

    @abstractmethod
    def generate(
        self,
        messages: Iterable[Message],
        config: GenerationConfig | None = None,
        on_token: TokenCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        """生成回复。异常一律抛 :class:`ProviderError`。"""

    def close(self) -> None:
        """释放资源，默认无操作。"""

    def describe(self) -> str:
        return f"{self.name} · {self.model_label}" if self.model_label else self.name


def join_messages(messages: Iterable[Message]) -> str:
    """把消息拼成纯文本（调试 / 极端情况下的兜底）。"""
    lines = []
    for msg in messages:
        lines.append(f"[{msg.role}] {msg.content}")
    return "\n".join(lines)


def chatml(messages: Iterable[Message]) -> str:
    """Qwen / 多数国产开源模型使用的 ChatML 模板。

    手工拼接是为了不依赖 tokenizer 的 chat template（端侧拿不到 jinja 运行时）。
    """
    parts = []
    for msg in messages:
        parts.append(f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)
