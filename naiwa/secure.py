"""轻量加密存储。

设计目标是「避免账号密码、会话 Cookie 以明文形式落盘」，而不是对抗取证级的攻击者。
设备上没有接入 Android Keystore（Kivy + 纯标准库做不到），所以这里用标准原语拼一个
最小可用的加密方案：

    keystream_i = HMAC-SHA256(enc_key, nonce ‖ i)
    ciphertext  = plaintext XOR keystream
    tag         = HMAC-SHA256(mac_key, "NW1" ‖ nonce ‖ ciphertext)

密钥来自应用私有目录里的 32 字节随机文件（权限 0600），App 私有目录本身受 Android
沙箱保护。换设备或重装 App 后旧数据无法解开，这是预期行为。

**不要**把这个模块用在需要长期保密、跨设备同步的场景。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

_MAGIC = b"NW1"
_NONCE_LEN = 16
_TAG_LEN = 32
_HEADER_LEN = len(_MAGIC) + _NONCE_LEN + _TAG_LEN


class SecureError(RuntimeError):
    """解密失败（密钥不匹配或数据被篡改）。"""


def _derive(master: bytes, label: bytes) -> bytes:
    return hmac.new(master, label, hashlib.sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


class SecretBox:
    """基于设备密钥的对称加解密。"""

    def __init__(self, key_path: Path) -> None:
        self.key_path = Path(key_path)
        self._master: bytes | None = None

    # ---------------------------------------------------------------- 密钥
    def _load_master(self) -> bytes:
        if self._master is not None:
            return self._master
        path = self.key_path
        if path.is_file():
            master = path.read_bytes()
            if len(master) < 32:
                raise SecureError("设备密钥损坏")
        else:
            master = secrets.token_bytes(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(master)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        self._master = master[:32]
        return self._master

    # ---------------------------------------------------------------- 加解密
    def seal(self, plaintext: bytes) -> bytes:
        master = self._load_master()
        enc_key = _derive(master, b"enc")
        mac_key = _derive(master, b"mac")
        nonce = secrets.token_bytes(_NONCE_LEN)
        stream = _keystream(enc_key, nonce, len(plaintext))
        cipher = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(mac_key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
        return _MAGIC + nonce + tag + cipher

    def open(self, blob: bytes) -> bytes:
        if len(blob) < _HEADER_LEN or not blob.startswith(_MAGIC):
            raise SecureError("不是本应用生成的数据")
        master = self._load_master()
        enc_key = _derive(master, b"enc")
        mac_key = _derive(master, b"mac")
        nonce = blob[len(_MAGIC): len(_MAGIC) + _NONCE_LEN]
        tag = blob[len(_MAGIC) + _NONCE_LEN: _HEADER_LEN]
        cipher = blob[_HEADER_LEN:]
        expect = hmac.new(mac_key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expect):
            raise SecureError("校验失败，数据可能被修改或密钥不匹配")
        stream = _keystream(enc_key, nonce, len(cipher))
        return bytes(a ^ b for a, b in zip(cipher, stream))

    # ---------------------------------------------------------------- JSON 便捷接口
    def seal_json(self, obj: Any) -> bytes:
        return self.seal(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def open_json(self, blob: bytes) -> Any:
        return json.loads(self.open(blob).decode("utf-8"))
