"""对话记忆。

只做「最近 N 轮」的短期记忆：2B 模型的上下文窗口很小（2048 token 起），
塞多了反而会挤掉系统提示词，导致它开始胡说。
长期记忆（比如"我叫什么、喜欢什么课"）留给后续版本，用本地小向量库做。
"""

from __future__ import annotations

from ..store import HistoryStore


class ConversationMemory:
    def __init__(self, store: HistoryStore | None = None, max_turns: int = 12) -> None:
        self.store = store or HistoryStore()
        self.max_turns = max_turns
        self._items: list[dict[str, str]] = self.store.load()

    def recent(self, limit: int | None = None) -> list[dict[str, str]]:
        count = (limit or self.max_turns) * 2
        return self._items[-count:]

    def add(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        item = {"role": role, "content": text}
        self._items.append(item)
        if len(self._items) > self.max_turns * 2:
            self._items = self._items[-self.max_turns * 2:]
        try:
            self.store.append(role, text)
        except OSError:
            pass  # 磁盘满 / 权限问题不该影响聊天

    def clear(self) -> None:
        self._items = []
        try:
            self.store.clear()
        except OSError:
            pass
