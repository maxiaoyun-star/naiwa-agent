"""检查 APK 里的 .so 是否按 16 KB 页对齐（Android 15+ 的要求）。

不依赖 pyelftools：直接读 ELF 头 + program headers，只看 PT_LOAD 的 p_align。
用法：
    python scripts/check_apk_libs.py path/to/app.apk
"""

from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

PT_LOAD = 1
PAGE_16K = 0x4000


def load_alignments(elf: bytes) -> list[int]:
    if elf[:4] != b"\x7fELF":
        return []
    is64 = elf[4] == 2
    little = elf[5] == 1
    endian = "<" if little else ">"

    if is64:
        e_phoff = struct.unpack_from(endian + "Q", elf, 0x20)[0]
        e_phentsize = struct.unpack_from(endian + "H", elf, 0x36)[0]
        e_phnum = struct.unpack_from(endian + "H", elf, 0x38)[0]
        aligns = []
        for i in range(e_phnum):
            base = e_phoff + i * e_phentsize
            p_type = struct.unpack_from(endian + "I", elf, base)[0]
            if p_type != PT_LOAD:
                continue
            p_align = struct.unpack_from(endian + "Q", elf, base + 0x30)[0]
            aligns.append(int(p_align))
        return aligns

    e_phoff = struct.unpack_from(endian + "I", elf, 0x1C)[0]
    e_phentsize = struct.unpack_from(endian + "H", elf, 0x2A)[0]
    e_phnum = struct.unpack_from(endian + "H", elf, 0x2C)[0]
    aligns = []
    for i in range(e_phnum):
        base = e_phoff + i * e_phentsize
        p_type = struct.unpack_from(endian + "I", elf, base)[0]
        if p_type != PT_LOAD:
            continue
        p_align = struct.unpack_from(endian + "I", elf, base + 0x1C)[0]
        aligns.append(int(p_align))
    return aligns


def main(apk_path: str) -> int:
    apk = Path(apk_path)
    if not apk.is_file():
        print(f"✗ 找不到 {apk}")
        return 1

    bad = 0
    total = 0
    with zipfile.ZipFile(apk) as zf:
        for name in sorted(zf.namelist()):
            if not name.endswith(".so"):
                continue
            total += 1
            data = zf.read(name)
            aligns = load_alignments(data)
            if not aligns:
                print(f"  ? {name}: 不是 ELF，跳过")
                continue
            ok = all(align >= PAGE_16K for align in aligns)
            flag = "✓" if ok else "✗"
            worst = min(aligns)
            print(f"  {flag} {name}: p_align min=0x{worst:x} ({len(aligns)} LOAD)")
            if not ok:
                bad += 1

    print(f"\n共 {total} 个原生库，{bad} 个未按 16 KB 对齐")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "dist/app.apk"))
