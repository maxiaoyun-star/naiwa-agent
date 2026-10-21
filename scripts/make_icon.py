"""生成 App 图标：纯白底 + 近黑圆角对话气泡 + 三个白点。

用 Pillow 画，避免引入 SVG 或第三方图标资源；尺寸 512×512 满足 Android 各密度。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
WHITE = (255, 255, 255, 255)
INK = (18, 20, 23, 255)


def main(out: Path) -> None:
    image = Image.new("RGBA", (SIZE, SIZE), WHITE)
    draw = ImageDraw.Draw(image)

    # 圆角气泡主体
    left, top, right, bottom = 72, 104, 440, 352
    draw.rounded_rectangle([left, top, right, bottom], radius=88, fill=INK)
    # 气泡尾巴
    draw.polygon(
        [(176, bottom - 6), (176, bottom + 62), (238, bottom - 6)],
        fill=INK,
    )
    # 三个点
    for index, cx in enumerate((168, 256, 344)):
        draw.ellipse([cx - 22, 206, cx + 22, 250], fill=WHITE)

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, format="PNG")
    print(f"wrote {out} ({image.size[0]}x{image.size[1]})")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    main(root / "assets" / "icon.png")
