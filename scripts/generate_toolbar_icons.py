"""生成工具栏喜庆吉祥风格图标."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def interpolate_color(c1: tuple, c2: tuple, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int] | None = None,
    outline: tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)


def draw_3d_button_base(img: Image.Image, size: int) -> None:
    """绘制3D喜庆按钮底色、高光、阴影和边框."""
    draw = ImageDraw.Draw(img, "RGBA")
    radius = size // 5
    padding = size // 14

    # 底部阴影
    shadow_offset = size // 16
    draw.rounded_rectangle(
        (padding + shadow_offset, padding + shadow_offset, size - padding + shadow_offset, size - padding + shadow_offset),
        radius=radius,
        fill=(0, 0, 0, 90),
    )

    # 红色径向渐变底色（喜庆）
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    c1 = hex_to_rgb("#D32F2F")  # 中心亮红
    c2 = hex_to_rgb("#8E0000")  # 边缘深红
    cx, cy = size // 2, size // 2
    max_dist = math.sqrt(2) * size / 2
    for y in range(size):
        for x in range(size):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = min(1.0, dist / max_dist)
            bg_draw.point((x, y), fill=interpolate_color(c1, c2, t))

    # 应用圆角遮罩
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((padding, padding, size - padding, size - padding), radius=radius, fill=255)
    bg.putalpha(mask)
    img.paste(bg, (0, 0), bg)

    # 金色边框
    border_width = max(2, size // 32)
    draw.rounded_rectangle(
        (padding, padding, size - padding, size - padding),
        radius=radius,
        outline=(*hex_to_rgb("#FFD700"), 220),
        width=border_width,
    )

    # 顶部高光（模拟3D凸起）
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(highlight)
    h_pad = padding + border_width + 1
    h_radius = radius - border_width
    h_draw.rounded_rectangle(
        (h_pad, h_pad, size - h_pad, size // 2),
        radius=h_radius,
        fill=(255, 255, 255, 45),
    )
    img.paste(highlight, (0, 0), highlight)


def draw_symbol(img: Image.Image, name: str, size: int) -> None:
    """在中央绘制白色/金色符号."""
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = size // 2, size // 2
    symbol_color = (255, 255, 255, 245)
    gold_color = (*hex_to_rgb("#FFD700"), 245)

    if name == "generate":
        # 闪电符号
        points = [
            (cx + size // 12, cy - size // 5),
            (cx - size // 12, cy - size // 20),
            (cx + size // 20, cy - size // 20),
            (cx - size // 10, cy + size // 5),
            (cx + size // 12, cy + size // 20),
            (cx - size // 20, cy + size // 20),
        ]
        draw.polygon(points, fill=gold_color)

    elif name == "copy":
        # 两个重叠矩形
        w, h = size // 3, size // 2
        x1, y1 = cx - w // 2 - size // 12, cy - h // 2 - size // 12
        x2, y2 = cx - w // 2 + size // 12, cy - h // 2 + size // 12
        draw.rounded_rectangle((x1, y1, x1 + w, y1 + h), radius=size // 16, outline=symbol_color, width=size // 18)
        draw.rounded_rectangle((x2, y2, x2 + w, y2 + h), radius=size // 16, fill=(211, 47, 47, 200), outline=gold_color, width=size // 24)

    elif name == "print":
        # 打印机简笔画
        w, h = size // 2, size // 2
        x, y = cx - w // 2, cy - h // 3
        # 机身
        draw.rounded_rectangle((x, y + h // 4, x + w, y + h), radius=size // 24, fill=symbol_color)
        # 顶部纸张
        draw.rounded_rectangle((x + w // 6, y, x + w * 5 // 6, y + h // 2), radius=size // 32, fill=gold_color)
        # 底部出纸口
        draw.rectangle((x + w // 5, y + h * 2 // 3, x + w * 4 // 5, y + h), fill=(180, 30, 30, 200))

    elif name == "pdf":
        # 带 PDF 字样的文档
        w, h = size // 2, size // 2
        x, y = cx - w // 2, cy - h // 2
        draw.rounded_rectangle((x, y, x + w, y + h), radius=size // 20, fill=symbol_color)
        # 右上角折角
        draw.polygon(
            [(x + w * 3 // 4, y), (x + w, y), (x + w, y + h // 4)],
            fill=gold_color,
        )
        # PDF 文字
        try:
            font = ImageFont.truetype("msyhbd.ttc", size // 7)
        except Exception:
            font = ImageFont.load_default()
        text = "PDF"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), text, fill=(180, 30, 30, 255), font=font)

    elif name == "save":
        # 星星/爱心收藏
        r = size // 3
        # 五角星
        star_points = []
        for i in range(10):
            angle = math.radians(270 + i * 36)
            rr = r if i % 2 == 0 else r // 2
            star_points.append((cx + int(rr * math.cos(angle)), cy + int(rr * math.sin(angle))))
        draw.polygon(star_points, fill=gold_color)
        # 中心高光
        draw.ellipse((cx - r // 4, cy - r // 4, cx + r // 4, cy + r // 4), fill=(255, 255, 255, 120))

    elif name == "backtest":
        # 日历 + 放大镜（历史回测）
        w, h = size // 2, size // 2
        x, y = cx - w // 2, cy - h // 3
        # 日历主体
        draw.rounded_rectangle((x, y, x + w, y + h), radius=size // 20, fill=symbol_color)
        # 日历顶部
        draw.rectangle((x, y, x + w, y + h // 4), fill=gold_color)
        # 日期数字
        try:
            font = ImageFont.truetype("msyhbd.ttc", size // 6)
        except Exception:
            font = ImageFont.load_default()
        text = "1"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2 + size // 16), text, fill=(180, 30, 30, 255), font=font)

    elif name == "batch_backtest":
        # 多页日历叠放（批量回测）
        w, h = size // 2, size // 2
        x, y = cx - w // 2 - size // 12, cy - h // 3 - size // 12
        # 底层日历
        draw.rounded_rectangle((x + size // 12, y + size // 12, x + w + size // 12, y + h + size // 12), radius=size // 20, fill=(180, 30, 30, 200))
        # 中层日历
        draw.rounded_rectangle((x + size // 24, y + size // 24, x + w + size // 24, y + h + size // 24), radius=size // 20, fill=(211, 47, 47, 220))
        # 顶层日历
        draw.rounded_rectangle((x, y, x + w, y + h), radius=size // 20, fill=symbol_color)
        draw.rectangle((x, y, x + w, y + h // 4), fill=gold_color)
        # 省略号
        try:
            font = ImageFont.truetype("msyhbd.ttc", size // 7)
        except Exception:
            font = ImageFont.load_default()
        text = "..."
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2 + size // 24, cy - th // 2 + size // 24), text, fill=(180, 30, 30, 255), font=font)

    elif name == "update_all":
        # 金色环形刷新箭头
        r = size // 3
        bbox = (cx - r, cy - r, cx + r, cy + r)
        arc_width = max(3, size // 16)
        draw.arc(bbox, start=300, end=240, fill=gold_color, width=arc_width)

        # 箭头位于 240°（顺时针终点），指向继续旋转的方向
        theta = math.radians(240)
        ex = cx + r * math.cos(theta)
        ey = cy + r * math.sin(theta)
        # PIL 角度顺时针递增，切线方向为 (-sinθ, cosθ)
        dx, dy = -math.sin(theta), math.cos(theta)
        px, py = -dy, dx
        L = size // 6
        hw = size // 10
        tip = (ex + dx * L, ey + dy * L)
        c1 = (ex + px * hw, ey + py * hw)
        c2 = (ex - px * hw, ey - py * hw)
        draw.polygon([tip, c1, c2], fill=gold_color)


def create_icon(name: str, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_3d_button_base(img, size)
    draw_symbol(img, name, size)
    return img


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    resources_dir = project_root / "caipiao" / "ui" / "resources" / "toolbar"
    resources_dir.mkdir(parents=True, exist_ok=True)

    icons = {
        "generate": "立即生成",
        "copy": "复制全部",
        "print": "打印结果",
        "pdf": "导出 PDF",
        "save": "保存历史",
        "update_all": "更新全部",
        "backtest": "历史回测",
        "batch_backtest": "批量回测",
    }

    for key, label in icons.items():
        img = create_icon(key, size=64)
        path = resources_dir / f"{key}.png"
        img.save(path, "PNG")
        print(f"Saved {label} icon: {path}")


if __name__ == "__main__":
    main()
