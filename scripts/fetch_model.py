"""把 GGUF 模型下到本地（给桌面调试 / 手动传手机用）。

用法：
    python scripts/fetch_model.py --url https://example.com/Qwen3.5-2B-Q4_K_M.gguf
    python scripts/fetch_model.py --url ... --out models/Qwen3.5-2B-Q4_K_M.gguf

特性：断点续传、进度显示、大小校验。下完直接 adb push 到手机即可：
    adb push models/Qwen3.5-2B-Q4_K_M.gguf /sdcard/Android/data/com.naiwa.naiwaagent/files/models/
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiwa import config, defaults  # noqa: E402


def human(num: float) -> str:
    return config.human_size(num)


def main() -> int:
    parser = argparse.ArgumentParser(description="下载本地模型 GGUF")
    parser.add_argument("--url", required=True, help="模型直链")
    parser.add_argument("--out", default="", help="保存路径（默认 models/<文件名>）")
    args = parser.parse_args()

    out = Path(args.out) if args.out else Path("models") / defaults.MODEL_FILENAME
    part = out.with_suffix(out.suffix + ".part")
    out.parent.mkdir(parents=True, exist_ok=True)

    done = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": config.USER_AGENT}
    if done:
        headers["Range"] = f"bytes={done}-"
        print(f"→ 续传，已有 {human(done)}")

    request = urllib.request.Request(args.url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        print(f"✗ HTTP {exc.code}")
        return 1
    except urllib.error.URLError as exc:
        print(f"✗ 连接失败：{exc.reason}")
        return 1

    total = int(response.headers.get("Content-Length") or 0) + done
    mode = "ab" if getattr(response, "status", 200) == 206 and done else "wb"
    if mode == "wb":
        done = 0

    print(f"→ 开始下载到 {out}（总大小 {human(total) if total else '未知'}）")
    try:
        with open(part, mode) as handle:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if total:
                    percent = done * 100 // total
                    bar = "#" * (percent // 4)
                    print(f"\r  {percent:3d}% {bar:<25} {human(done)}", end="", flush=True)
                else:
                    print(f"\r  {human(done)}", end="", flush=True)
    finally:
        response.close()
    print()

    size = part.stat().st_size
    if size < 32 * 1024 * 1024:
        print(f"✗ 文件太小（{human(size)}），地址可能不对")
        return 1

    part.replace(out)
    print(f"✓ 完成：{out}（{human(size)}）")
    print("  传到手机：")
    print(f"  adb push {out} /sdcard/Android/data/com.naiwa.naiwaagent/files/models/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
