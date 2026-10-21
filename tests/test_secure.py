"""加密存储的单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from naiwa.secure import SecretBox, SecureError


class SecretBoxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.key_path = Path(self.tmp.name) / ".device_key"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_roundtrip(self) -> None:
        box = SecretBox(self.key_path)
        plaintext = "学号 2021001 密码 p@ssw0rd".encode("utf-8")
        blob = box.seal(plaintext)

        self.assertNotEqual(blob, plaintext)
        self.assertTrue(blob.startswith(b"NW1"))
        # 新实例读同一个密钥文件也要能解开（模拟重启 App）
        self.assertEqual(SecretBox(self.key_path).open(blob), plaintext)

    def test_json_roundtrip(self) -> None:
        box = SecretBox(self.key_path)
        payload = {"username": "2021001", "cookies": {"JSESSIONID": "abc"}}
        self.assertEqual(box.open_json(box.seal_json(payload)), payload)

    def test_tamper_detected(self) -> None:
        box = SecretBox(self.key_path)
        blob = bytearray(box.seal(b"hello"))
        blob[-1] ^= 0x01
        with self.assertRaises(SecureError):
            box.open(bytes(blob))

    def test_wrong_key_rejected(self) -> None:
        first = SecretBox(self.key_path)
        blob = first.seal(b"hello")
        other = SecretBox(Path(self.tmp.name) / "other_key")
        with self.assertRaises(SecureError):
            other.open(blob)

    def test_garbage_rejected(self) -> None:
        box = SecretBox(self.key_path)
        with self.assertRaises(SecureError):
            box.open(b"not a sealed blob")


if __name__ == "__main__":
    unittest.main()
