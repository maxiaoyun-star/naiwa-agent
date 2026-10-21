"""门户接口探测：登录一次，然后逐个试候选路径，看哪条返回 JSON。

用途：学校门户的课表/考试接口没有文档，用它 5 分钟定位真实地址。
只用自己的账号、只访问学校域名，不做任何越权尝试。

用法：
    python scripts/probe_portal.py --user 2021xxxx [--path /custp/api/kbcx ...]

不传 --path 时会试一组常见路径；也可以直接在命令行给多条。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiwa.campus.cas import CasClient, CasError  # noqa: E402

DEFAULT_PATHS = [
    "/custp/api/schedule",
    "/custp/api/course",
    "/custp/api/exam",
    "/custp/student/schedule",
    "/custp/xskbcx",
    "/custp/kscx",
]


def show_image(data: bytes) -> Path:
    """把验证码存成文件并尝试用系统看图器打开。"""
    path = Path(tempfile.gettempdir()) / "naiwa_captcha.png"
    path.write_bytes(data)
    opener = {"nt": "start", "darwin": "open"}.get(os.name, "xdg-open")
    try:
        subprocess.Popen([opener, str(path)], shell=(os.name == "nt"))  # noqa: S603
    except OSError:
        pass
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="探测校园门户的 JSON 接口")
    parser.add_argument("--user", required=True, help="一卡通号")
    parser.add_argument("--path", action="append", default=[], help="候选路径，可重复")
    parser.add_argument("--cookie-file", default="", help="可选：把会话 Cookie 存成 JSON")
    args = parser.parse_args()

    client = CasClient()
    print("→ 打开登录页…")
    try:
        challenge = client.fetch_challenge()
    except CasError as exc:
        print(f"✗ {exc}")
        return 1

    if challenge.captcha_png:
        path = show_image(challenge.captcha_png)
        print(f"→ 验证码已保存：{path}（已尝试用系统看图器打开）")

    password = input("密码：").strip()
    captcha = input("验证码（图上那几位）：").strip() if challenge.captcha_required else ""

    print("→ 登录…")
    result = client.login(args.user, password, captcha, challenge)
    if not result.ok:
        print(f"✗ {result.message}")
        return 1
    print(f"✓ 登录成功，最终落在 {result.final_url}")

    if args.cookie_file:
        import json

        Path(args.cookie_file).write_text(
            json.dumps(result.cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"→ Cookie 已写入 {args.cookie_file}")

    for path in args.path or DEFAULT_PATHS:
        print(f"\n--- {path}")
        url = "https://portal.cust.edu.cn" + path
        try:
            status, raw, final, headers = client._request(url)  # noqa: SLF001
        except CasError as exc:
            print(f"    请求失败：{exc}")
            continue

        text = raw.decode("utf-8", "ignore")
        content_type = headers.get("Content-Type", "") or headers.get("content-type", "")
        print(f"    HTTP {status} · {content_type} · 落在 {final}")
        head = text.lstrip()[:200].replace("\n", " ")
        print(f"    {head}")
        if head.startswith(("{", "[")):
            print("    ↑ 这一条是 JSON，填进 App 的「教务接口」里")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
