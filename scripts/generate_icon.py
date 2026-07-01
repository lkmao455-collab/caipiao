"""Generate application icon for the Caipiao Generator."""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def interpolate_color(c1: tuple, c2: tuple, t: float) -> tuple[int, int, int]:
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_radial_gradient(
    draw: ImageDraw.ImageDraw, size: int, center_color: str, edge_color: str
) -> None:
    """Draw a radial gradient."""
    c1 = hex_to_rgb(center_color)
    c2 = hex_to_rgb(edge_color)
    cx, cy = size // 2, size // 2
    max_dist = math.sqrt(2) * size / 2
    for y in range(size):
        for x in range(size):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = min(1.0, dist / max_dist)
            draw.point((x, y), fill=interpolate_color(c1, c2, t))


def draw_hex_grid(draw: ImageDraw.ImageDraw, size: int, color: tuple, spacing: int) -> None:
    """Draw a subtle hexagonal grid pattern."""
    h = spacing * math.sqrt(3) / 2
    for row in range(-1, int(size / h) + 2):
        for col in range(-1, int(size / spacing) + 2):
            x = col * spacing + (row % 2) * (spacing / 2)
            y = row * h
            radius = spacing / 3
            draw.regular_polygon(
                bounding_circle=((x, y), radius),
                n_sides=6,
                outline=color,
                width=1,
            )


def draw_rounded_rect_mask(size: int, radius: int) -> Image.Image:
    """Create an alpha mask for a rounded rectangle."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def draw_ball(
    img: Image.Image,
    cx: int,
    cy: int,
    radius: int,
    base_color: str,
    glow_color: str,
) -> None:
    """Draw a 3D glossy lottery ball with outer glow."""
    draw = ImageDraw.Draw(img, "RGBA")
    base = hex_to_rgb(base_color)

    # Outer glow
    for r in range(radius + 14, radius, -1):
        alpha = int(35 * (1 - (r - radius) / 14))
        glow = (*hex_to_rgb(glow_color), alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=glow)

    # Main ball body: radial gradient from light top-left to dark bottom-right
    for r in range(radius, 0, -1):
        t = r / radius
        # Slightly lighter at center, darker toward edges
        shade = tuple(int(c * (1.0 - 0.35 * t)) for c in base)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade)

    # Soft large highlight at top-left
    hl_x = cx - radius // 3
    hl_y = cy - radius // 3
    hl_r = radius // 2
    for r in range(hl_r, 0, -1):
        t = r / hl_r
        alpha = int(140 * (1 - t))
        draw.ellipse([hl_x - r, hl_y - r, hl_x + r, hl_y + r], fill=(255, 255, 255, alpha))

    # Tiny sharp specular highlight
    spec_x = cx - radius // 2
    spec_y = cy - radius // 2
    spec_r = radius // 5
    for r in range(spec_r, 0, -1):
        t = r / spec_r
        alpha = int(220 * (1 - t))
        draw.ellipse([spec_x - r, spec_y - r, spec_x + r, spec_y + r], fill=(255, 255, 255, alpha))


def draw_drop_shadow(img: Image.Image, size: int, corner_radius: int) -> None:
    """Draw a subtle drop shadow behind the icon."""
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    offset = size // 40
    shadow_draw.rounded_rectangle(
        (offset, offset, size - offset // 2, size - offset // 2),
        radius=corner_radius,
        fill=(0, 0, 0, 90),
    )
    # Blur-like effect by drawing larger softer shadow
    for i in range(8, 0, -1):
        alpha = int(20 * (1 - i / 8))
        shadow_draw.rounded_rectangle(
            (offset - i, offset - i, size - offset // 2 + i, size - offset // 2 + i),
            radius=corner_radius + i,
            outline=(0, 0, 0, alpha),
            width=1,
        )
    img.paste(shadow, (0, 0), shadow)


def create_icon(size: int = 512) -> Image.Image:
    """Create the application icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    corner_radius = size // 6

    # Drop shadow
    draw_drop_shadow(img, size, corner_radius)

    # Background with gradient and hex grid
    bg = Image.new("RGBA", (size, size))
    bg_draw = ImageDraw.Draw(bg)
    draw_radial_gradient(bg_draw, size, "#132240", "#05070A")

    # Hex grid
    hex_color = (0, 210, 255, 25)
    draw_hex_grid(bg_draw, size, hex_color, size // 12)

    # Apply rounded mask
    mask = draw_rounded_rect_mask(size, corner_radius)
    bg.putalpha(mask)
    img.paste(bg, (0, 0), bg)

    draw = ImageDraw.Draw(img, "RGBA")

    # Cyan neon border
    border_width = max(2, size // 70)
    draw.rounded_rectangle(
        (border_width, border_width, size - border_width, size - border_width),
        radius=corner_radius - border_width,
        outline=(0, 210, 255, 160),
        width=border_width,
    )

    # Inner thin ring
    ring_margin = size // 10
    draw.ellipse(
        [ring_margin, ring_margin, size - ring_margin, size - ring_margin],
        outline=(0, 210, 255, 45),
        width=max(1, size // 120),
    )

    # Balls layout
    center_x, center_y = size // 2, size // 2
    orbit_radius = size // 4
    ball_radius = size // 13

    # 6 red balls arranged in a slightly tilted ring (top-left to bottom-right arc)
    red_color = "#EF233C"
    red_glow = "#FF5C7F"
    start_angle = math.radians(160)
    angle_step = math.radians(220 / 5)
    for i in range(6):
        angle = start_angle + i * angle_step
        bx = center_x + int(orbit_radius * math.cos(angle))
        by = center_y + int(orbit_radius * math.sin(angle))
        draw_ball(img, bx, by, ball_radius, red_color, red_glow)

    # Blue ball positioned at bottom-right, slightly outside the ring
    blue_color = "#00B4D8"
    blue_glow = "#48CAE4"
    blue_x = center_x + int(orbit_radius * 0.75)
    blue_y = center_y + int(orbit_radius * 0.95)
    draw_ball(img, blue_x, blue_y, int(ball_radius * 1.2), blue_color, blue_glow)

    # Tech scan line at bottom
    line_y = size - size // 8
    draw.line(
        [(size // 7, line_y), (size - size // 7, line_y)],
        fill=(0, 210, 255, 80),
        width=max(1, size // 120),
    )

    return img


def create_ico_file(images: list[Image.Image], path: Path) -> None:
    """Manually write a multi-resolution ICO file from PNG data."""
    png_data_list: list[bytes] = []
    for img in images:
        buffer = io.BytesIO()
        # PNG supports alpha and scales well for icon use
        img.save(buffer, format="PNG")
        png_data_list.append(buffer.getvalue())

    count = len(images)
    # ICONDIR: reserved(2) + type(2) + count(2)
    header = struct.pack("<HHH", 0, 1, count)

    # Each directory entry is 16 bytes; data starts after header + entries
    offset = 6 + 16 * count
    entries = b""
    data = b""

    for img, png_bytes in zip(images, png_data_list):
        width = img.width if img.width < 256 else 0
        height = img.height if img.height < 256 else 0
        size = len(png_bytes)
        # ICONDIRENTRY
        entries += struct.pack(
            "<BBBBHHII",
            width,  # width (0 means 256)
            height,  # height (0 means 256)
            0,  # colors (0 = >256)
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            size,  # data size
            offset,  # data offset
        )
        data += png_bytes
        offset += size

    with path.open("wb") as f:
        f.write(header + entries + data)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    resources_dir = project_root / "caipiao" / "ui" / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)

    source = create_icon(512)

    png_path = resources_dir / "icon.png"
    source.save(png_path, "PNG")
    print(f"Saved PNG preview: {png_path}")

    ico_path = resources_dir / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [source.resize((s, s), Image.Resampling.LANCZOS) for s in sizes]
    create_ico_file(icons, ico_path)
    print(f"Saved ICO: {ico_path}")


if __name__ == "__main__":
    main()
