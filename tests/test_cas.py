"""CAS 客户端里可以离线验证的部分：登录页解析、Cookie 罐、错误提示提取。

真正发请求的部分需要学校网络和真实账号，不做自动化测试（也不应该把账号写进仓库）。
"""

from __future__ import annotations

import unittest

from naiwa.campus.cas import CookieJar, _extract_error, parse_login_form

LOGIN_HTML = """
<html><head><title>统一身份认证</title></head><body>
<form method="post" id="fm1" action="login">
  <input class="form-control" id="username" type="text" name="username" value="" />
  <input class="form-control" type="password" id="password" name="password" value="" />
  <input class="form-control" id="captcha" type="text" name="captcha" />
  <input type="hidden" name="execution" value="43f557f4-7d83-45cc-b317-0a0b24aa9635_ZXlKaGJ" />
  <input type="hidden" name="_eventId" value="submit" />
  <input type="submit" name="submit" value="LOGIN" />
</form>
<img id="captcha_img" src="captcha" />
</body></html>
"""


class LoginFormTest(unittest.TestCase):
    def test_extracts_execution_and_captcha(self) -> None:
        form = parse_login_form(LOGIN_HTML)
        self.assertTrue(form.execution.startswith("43f557f4"))
        self.assertTrue(form.has_captcha)
        self.assertTrue(form.has_password)
        self.assertEqual(form.action, "login")

    def test_page_without_form(self) -> None:
        form = parse_login_form("<html><body>服务暂时不可用</body></html>")
        self.assertEqual(form.execution, "")
        self.assertFalse(form.has_captcha)


class CookieJarTest(unittest.TestCase):
    def test_host_cookie(self) -> None:
        jar = CookieJar()
        jar.update_from_headers(
            "mysso.cust.edu.cn",
            ["JSESSIONID=ABC123; Path=/cas; Secure; HttpOnly"],
        )
        self.assertEqual(jar.header_for("mysso.cust.edu.cn"), "JSESSIONID=ABC123")

    def test_domain_cookie_shared(self) -> None:
        jar = CookieJar()
        jar.update_from_headers(
            "mysso.cust.edu.cn",
            ["CASTGC=TGT-1000; Domain=.cust.edu.cn; Path=/; Secure"],
        )
        header = jar.header_for("portal.cust.edu.cn")
        self.assertIn("CASTGC=TGT-1000", header)

    def test_max_age_zero_removes(self) -> None:
        jar = CookieJar()
        jar.update_from_headers("mysso.cust.edu.cn", ["JSESSIONID=ABC"])
        jar.update_from_headers("mysso.cust.edu.cn", ["JSESSIONID=; Max-Age=0"])
        self.assertEqual(jar.header_for("mysso.cust.edu.cn"), "")

    def test_roundtrip_dict(self) -> None:
        jar = CookieJar()
        jar.update_from_headers("portal.cust.edu.cn", ["SESSION=xyz; Path=/"])
        restored = CookieJar(jar.as_dict())
        self.assertEqual(restored.header_for("portal.cust.edu.cn"), "SESSION=xyz")

    def test_unrelated_host_gets_nothing(self) -> None:
        jar = CookieJar()
        jar.update_from_headers("mysso.cust.edu.cn", ["JSESSIONID=ABC"])
        self.assertEqual(jar.header_for("example.com"), "")


class ErrorExtractTest(unittest.TestCase):
    def test_known_hint(self) -> None:
        html = "<div>用户名或密码错误，请重试</div>"
        self.assertEqual(_extract_error(html), "用户名或密码错误")

    def test_alert_block(self) -> None:
        html = '<div class="alert alert-danger">验证码不正确</div>'
        self.assertTrue(_extract_error(html))

    def test_no_error(self) -> None:
        self.assertEqual(_extract_error("<div>请登录</div>"), "")


if __name__ == "__main__":
    unittest.main()
