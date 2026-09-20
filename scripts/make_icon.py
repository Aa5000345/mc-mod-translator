#!/usr/bin/env python3
"""生成应用图标 icon.ico 和 icon.png。

运行一次即可，无需任何外部素材。生成的图标：
  - 蓝色渐变背景
  - 白色"译"字居中
  - 圆角矩形（透明背景）
  - 输出 1024x1024 PNG + 多分辨率 ICO

用法：
    pip install Pillow
    python scripts/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("缺少依赖 Pillow。请先运行：")
    print("    pip install Pillow")
    sys.exit(1)


# 输出到仓库根目录
REPO_ROOT = Path(__file__).resolve().parent.parent
PNG_PATH = REPO_ROOT / "icon.png"
ICO_PATH = REPO_ROOT / "icon.ico"


# ------------------------------ 配色 ------------------------------
BG_TOP = (37, 99, 235)       # #2563EB 亮蓝
BG_BOTTOM = (30, 58, 138)    # #1E3A8A 深蓝
FG = (255, 255, 255, 255)    # 白色
SHADOW = (0, 0, 0, 110)      # 文字阴影
HIGHLIGHT = (255, 255, 255, 32)


# --------------------------- 字体查找 ---------------------------
FONT_CANDIDATES = [
    # Windows（按优先级）
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "C:/Windows/Fonts/simsun.ttc",   # 宋体
    "C:/Windows/Fonts/msjhbd.ttc",   # 微软正黑体 Bold
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font(size: int) -> "ImageFont.FreeTypeFont | None":
    for path in FONT_CANDIDATES:
        p = Path(path)
        if not p.exists():
            continue
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return None


# --------------------------- 图像构建 ---------------------------

def _make_gradient(size: int) -> Image.Image:
    """垂直渐变背景。"""
    img = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        img.putpixel((0, y), (r, g, b))
    return img.resize((size, size))


def _draw_main_character(draw: ImageDraw.ImageDraw, size: int) -> None:
    """在图标中心画一个大号"译"字。"""
    font_size = int(size * 0.70)
    font = find_font(font_size)

    if font is None:
        # 兜底：找不到中文字体，画一个白框 + "A"
        margin = int(size * 0.22)
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=int(size * 0.06),
            outline=FG,
            width=max(2, int(size * 0.03)),
        )
        fallback_font = find_font(int(size * 0.45))
        if fallback_font is not None:
            text = "A"
            bbox = draw.textbbox((0, 0), text, font=fallback_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
                text,
                font=fallback_font,
                fill=FG,
            )
        return

    text = "译"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]

    # 阴影（偏移 1.2%）
    offset = int(size * 0.012)
    draw.text((x + offset, y + offset), text, font=font, fill=SHADOW)
    # 主字
    draw.text((x, y), text, font=font, fill=FG)


def draw_icon(size: int = 1024) -> Image.Image:
    """生成完整图标，返回 RGBA Image。"""
    # 1. 渐变背景 + 圆角蒙版
    gradient = _make_gradient(size).convert("RGBA")

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=int(size * 0.20),
        fill=255,
    )

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    # 2. 左上角柔和高光
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.ellipse(
        [(-size * 0.15, -size * 0.35), (size * 0.85, size * 0.45)],
        fill=HIGHLIGHT,
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(size * 0.06))
    highlight.putalpha(
        Image.composite(highlight.getchannel("A"), Image.new("L", (size, size), 0), mask)
    )
    img = Image.alpha_composite(img, highlight)

    # 3. 白色"译"字
    draw = ImageDraw.Draw(img)
    _draw_main_character(draw, size)

    return img


# --------------------------- 主流程 ---------------------------

def main() -> int:
    print("正在生成图标...")

    # 生成大尺寸主图标
    img = draw_icon(1024)

    # 保存 PNG（源文件，方便以后修改）
    img.save(PNG_PATH, "PNG", optimize=True)
    print(f"[生成] {PNG_PATH.relative_to(REPO_ROOT)}")

    # 保存多分辨率 ICO
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICO_PATH, format="ICO", sizes=sizes)
    print(f"[生成] {ICO_PATH.relative_to(REPO_ROOT)}")

    print()
    print("完成！下一步：")
    print("  1. 把 icon.ico 和 icon.png 提交到仓库")
    print("  2. CI 里打包已自动加 --icon icon.ico（见 .github/workflows/）")
    print("  3. 本地打包时也要加：--icon icon.ico --add-data \"icon.ico;.\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())