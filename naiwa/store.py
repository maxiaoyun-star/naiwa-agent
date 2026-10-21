"""持久化：设置、加密会话、加密密钥、对话记录。

原则：
* 普通设置明文 JSON（可以被人看，无所谓）；
* 账号、Cookie、API Key 一律走 :class:`~naiwa.secure.SecretBox` 加密后落盘；
* 写入用「临时文件 + 替换」，避免进程被杀导致文件半截。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from . import config
from .secure import SecretBox, SecureError

DEFAULT_SETTINGS: dict[str, Any] = {
    "llm_mode": "auto",              # auto | local | remote
    "local_n_ctx": 2048,
    "local_n_threads": 4,
    "temperature": 0.7,
    "max_tokens": 512,
    "remote_provider": "zhipu",
    "remote_base": "",
    "remote_model": "",
    "model_url": "",
    "cas_username": "",
    "cas_remember": True,            # 保存 Cookie，保持登录态
    "cas_save_password": False,      # 默认不存密码
    # 教务接口：路径没有公开文档，只能抓包后填写
    "portal_api_schedule": "",
    "portal_api_schedule_path": "",
    "portal_api_exams": "",
    "portal_api_exams_path": "",
    "portal_api_profile": "",
    "portal_api_profile_path": "",
    "onboarded": False,
    "last_model_check": 0.0,
}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, data: bytes) -> None:
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


class Settings:
    """明文设置，字典语义。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.settings_path()
        data = read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        self._data: dict[str, Any] = {**DEFAULT_SETTINGS, **data}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, **kwargs: Any) -> None:
        self._data.update(kwargs)

    def save(self) -> None:
        atomic_write(self.path, json.dumps(self._data, ensure_ascii=False, indent=2).encode("utf-8"))

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


class Secrets:
    """加密的小型 KV（API Key、密码）。"""

    def __init__(self, path: Path | None = None, box: SecretBox | None = None) -> None:
        self.path = path or (config.data_dir() / "secrets.enc")
        self.box = box or SecretBox(config.device_key_path())
        self._data: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        try:
            blob = self.path.read_bytes()
        except OSError:
            return
        if not blob:
            return
        try:
            data = self.box.open_json(blob)
        except (SecureError, ValueError):
            return
        if isinstance(data, dict):
            self._data = {str(k): str(v) for k, v in data.items()}

    def save(self) -> None:
        atomic_write(self.path, self.box.seal_json(self._data))

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self.save()

    def pop(self, key: str) -> None:
        self._data.pop(key, None)
        self.save()

    def clear(self) -> None:
        """清空所有加密项（退出登录 / 清除数据时用）。"""
        self._data = {}
        try:
            self.path.unlink()
        except OSError:
            pass


class SessionStore:
    """CAS 会话（Cookie + 学号）。

    只存 Cookie 就能保持登录态，比存密码安全得多，所以默认只存这个。
    用户显式勾选「记住密码」时才额外保存密码。
    """

    def __init__(self, path: Path | None = None, box: SecretBox | None = None) -> None:
        self.path = path or config.session_path()
        self.box = box or SecretBox(config.device_key_path())

    def save(self, username: str, cookies: dict[str, str], password: str = "") -> None:
        payload: dict[str, Any] = {
            "username": username,
            "cookies": cookies,
            "saved_at": time.time(),
        }
        if password:
            payload["password"] = password
        atomic_write(self.path, self.box.seal_json(payload))

    def load(self) -> dict[str, Any] | None:
        try:
            blob = self.path.read_bytes()
        except OSError:
            return None
        if not blob:
            return None
        try:
            data = self.box.open_json(blob)
        except (SecureError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def clear(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


class HistoryStore:
    """对话记录，按轮追加，只保留最近 ``limit`` 轮。"""

    def __init__(self, path: Path | None = None, limit: int = 200) -> None:
        self.path = path or config.history_path()
        self.limit = limit

    def load(self) -> list[dict[str, str]]:
        data = read_json(self.path, [])
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict) and item.get("role") and item.get("content")]

    def append(self, role: str, content: str) -> None:
        items = self.load()
        items.append({"role": role, "content": content, "ts": str(time.time())})
        if len(items) > self.limit:
            items = items[-self.limit:]
        atomic_write(self.path, json.dumps(items, ensure_ascii=False, indent=1).encode("utf-8"))

    def clear(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass
