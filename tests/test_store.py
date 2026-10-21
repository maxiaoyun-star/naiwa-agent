"""设置 / 密钥 / 会话持久化的单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from naiwa import secure, store


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_defaults_present(self) -> None:
        settings = store.Settings(self.path)
        self.assertEqual(settings.get("llm_mode"), "auto")
        self.assertFalse(settings.get("cas_save_password"))
        self.assertEqual(settings.get("portal_api_schedule"), "")

    def test_persist(self) -> None:
        settings = store.Settings(self.path)
        settings.set("llm_mode", "local")
        settings.save()

        again = store.Settings(self.path)
        self.assertEqual(again.get("llm_mode"), "local")

    def test_corrupt_file_falls_back(self) -> None:
        self.path.write_text("{ not json", encoding="utf-8")
        settings = store.Settings(self.path)
        self.assertEqual(settings.get("llm_mode"), "auto")


class SecretsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.box = secure.SecretBox(root / ".device_key")
        self.path = root / "secrets.enc"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_and_reload(self) -> None:
        secrets = store.Secrets(self.path, self.box)
        secrets.set("remote_api_key", "sk-test-123")

        reloaded = store.Secrets(self.path, self.box)
        self.assertEqual(reloaded.get("remote_api_key"), "sk-test-123")

    def test_file_is_not_plaintext(self) -> None:
        secrets = store.Secrets(self.path, self.box)
        secrets.set("remote_api_key", "sk-plain-should-not-appear")
        self.assertNotIn(b"sk-plain-should-not-appear", self.path.read_bytes())


class SessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.box = secure.SecretBox(root / ".device_key")
        self.path = root / "session.enc"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_roundtrip(self) -> None:
        sessions = store.SessionStore(self.path, self.box)
        cookies = {"mysso.cust.edu.cn": {"JSESSIONID": "x"}}
        sessions.save("2021001", cookies)

        data = store.SessionStore(self.path, self.box).load()
        self.assertIsNotNone(data)
        self.assertEqual(data["username"], "2021001")
        self.assertEqual(data["cookies"], cookies)
        self.assertNotIn("password", data)

    def test_password_only_when_requested(self) -> None:
        sessions = store.SessionStore(self.path, self.box)
        sessions.save("2021001", {}, password="secret")
        self.assertEqual(sessions.load()["password"], "secret")

    def test_clear(self) -> None:
        sessions = store.SessionStore(self.path, self.box)
        sessions.save("2021001", {})
        sessions.clear()
        self.assertIsNone(sessions.load())


if __name__ == "__main__":
    unittest.main()
