"""Android 兼容层的单元测试。

重点不是验证真实 insets（那需要真机），而是保证：
* 桌面环境不会因为缺 jnius 而崩；
* 拿不到 Java 侧对象时安全退化为 0；
* dp 换算正确（读 insets 时要靠它把 px 转成 dp）。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from naiwa import platform_compat


class DpTest(unittest.TestCase):
    def test_density_conversion(self) -> None:
        self.assertEqual(platform_compat._dp(48, 2.0), 24.0)
        self.assertEqual(platform_compat._dp(72, 3.0), 24.0)

    def test_bad_density(self) -> None:
        self.assertEqual(platform_compat._dp(48, 0), 48.0)
        self.assertEqual(platform_compat._dp(0, 2.0), 0.0)


class InsetsTest(unittest.TestCase):
    def setUp(self) -> None:
        platform_compat.reset_cache()

    def tearDown(self) -> None:
        platform_compat.reset_cache()

    def test_desktop_returns_zero(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANDROID_PRIVATE", None)
            os.environ.pop("ANDROID_ARGUMENT", None)
            self.assertFalse(platform_compat.is_android())
            self.assertEqual(platform_compat.insets_dp(), (0.0, 0.0))

    def test_android_without_jnius_degrades(self) -> None:
        """模拟「在 Android 上但 jnius 不可用」：必须返回 0 而不是抛异常。"""
        with mock.patch.dict(os.environ, {"ANDROID_PRIVATE": "/data/user/0/x/files"}):
            platform_compat.reset_cache()
            self.assertTrue(platform_compat.is_android())
            top, bottom = platform_compat.insets_dp()
            self.assertEqual((top, bottom), (0.0, 0.0))

    def test_cached(self) -> None:
        with mock.patch.dict(os.environ, {"ANDROID_PRIVATE": "/data/user/0/x/files"}):
            platform_compat.reset_cache()
            first = platform_compat.insets_dp()
            second = platform_compat.insets_dp()
            self.assertIs(first, second)

    def test_light_system_bars_is_noop_on_desktop(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANDROID_PRIVATE", None)
            platform_compat.reset_cache()
            platform_compat.set_light_system_bars()  # 不抛异常即通过


if __name__ == "__main__":
    unittest.main()
