"""模型文件管理：定位、下载、校验。

1.19 GB 的 GGUF 不进 APK（GitHub 对单文件、对 APK 体积都有限制），所以走「首次启动下载」。
下载实现要点：
* 先写 ``.part`` 再改名，中途断掉不会留下一个"看起来能用"的坏文件；
* 支持 ``Range`` 续传，宿舍网断了能接着下；
* 下完按大小（可选 SHA256）校验，不符合就删掉重来。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import config, defaults

ProgressCallback = Callable[[int, int], None]   # (已下载, 总字节)
StopCallback = Callable[[], bool]


class ModelError(RuntimeError):
    pass


class ModelManager:
    def __init__(self, settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------ 路径
    @property
    def filename(self) -> str:
        return defaults.MODEL_FILENAME

    def existing(self) -> Path | None:
        return config.find_model(self.filename)

    def target(self) -> Path:
        return config.models_dir() / self.filename

    def url(self) -> str:
        return str(self.settings.get("model_url") or defaults.DEFAULT_MODEL_URL or "").strip()

    # ------------------------------------------------------------------ 导入
    def import_from(self, source: Path) -> Path:
        """把用户选中的文件复制进私有目录。"""
        source = Path(source)
        if not source.is_file():
            raise ModelError("文件不存在")
        dest = self.target()
        if dest.exists() and dest.stat().st_size == source.stat().st_size:
            return dest
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            raise ModelError(f"复制失败：{exc}") from exc
        return dest

    # ------------------------------------------------------------------ 下载
    def download(
        self,
        url: str | None = None,
        on_progress: ProgressCallback | None = None,
        should_stop: StopCallback | None = None,
    ) -> Path:
        target_url = (url or self.url()).strip()
        if not target_url:
            raise ModelError("先填模型下载地址（设置 → 本地模型）")
        if not target_url.lower().startswith(("http://", "https://")):
            raise ModelError("下载地址要以 http:// 或 https:// 开头")

        dest = self.target()
        part = dest.with_suffix(dest.suffix + ".part")
        dest.parent.mkdir(parents=True, exist_ok=True)

        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": config.USER_AGENT}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"

        request = urllib.request.Request(target_url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT_LONG)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:  # 已经下完了
                response = None
            elif exc.code == 404:
                raise ModelError("下载地址 404，检查一下链接") from exc
            else:
                raise ModelError(f"下载失败 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ModelError(f"连不上下载地址：{getattr(exc, 'reason', exc)}") from exc

        total = 0
        mode = "ab"
        if response is not None:
            content_length = int(response.headers.get("Content-Length") or 0)
            http_status = getattr(response, "status", 200)
            if http_status == 200:
                # 服务器不支持续传，从头写
                downloaded = 0
                mode = "wb"
            total = content_length + downloaded
            try:
                with open(part, mode) as handle:
                    while True:
                        if should_stop is not None and should_stop():
                            raise ModelError("已取消")
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if on_progress is not None:
                            on_progress(downloaded, total)
            finally:
                response.close()
        else:
            downloaded = part.stat().st_size if part.exists() else 0
            total = downloaded

        size = part.stat().st_size if part.exists() else 0
        if size < 32 * 1024 * 1024:
            raise ModelError(f"文件太小（{config.human_size(size)}），地址可能不对")

        expected = defaults.MODEL_SHA256.strip()
        if expected:
            if not self._sha256_matches(part, expected):
                try:
                    part.unlink()
                except OSError:
                    pass
                raise ModelError("SHA256 校验失败，文件已删除，请重新下载")

        os.replace(part, dest)
        self.settings.set("last_model_check", time.time())
        return dest

    @staticmethod
    def _sha256_matches(path: Path, expected: str) -> bool:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower() == expected.lower()

    # ------------------------------------------------------------------ 状态
    def status(self) -> tuple[bool, str]:
        path = self.existing()
        if path is None:
            return False, "未安装"
        try:
            size = path.stat().st_size
        except OSError:
            return False, "文件不可读"
        return True, f"{config.human_size(size)} · {path.parent}"
