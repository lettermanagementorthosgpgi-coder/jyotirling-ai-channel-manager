"""Compose a branded 16:9 review thumbnail from generated background art."""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size, bold=True):
    pattern = "Noto Sans Devanagari:style=Bold" if bold else "Noto Sans Devanagari"
    try:
        path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", pattern], text=True, timeout=10
        ).strip()
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        pass
    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    return ImageFont.truetype(fallback, size=size) if Path(fallback).exists() else ImageFont.load_default()


def _wrap_title(title, width=25):
    words = str(title or "विशेष आध्यात्मिक प्रवचन").split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def compose_thumbnail(background_path, output_path, title, author_photo_path=None):
    image = Image.open(background_path).convert("RGB")
    image = ImageOps.fit(image, (1280, 720), method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Fixed channel header and lower speaker band.
    draw.rounded_rectangle((24, 18, 1256, 86), radius=18, fill=(10, 10, 10, 178))
    header_font = _font( thirty := 30)
    header = "JYOTIRLING SHIVMATH BARAULI LUCKNOW"
    draw.text((640, 52), header, font=header_font, fill="white",
              anchor="mm", stroke_width=1, stroke_fill=(0, 0, 0, 210))

    draw.rounded_rectangle((24, 610, 1256, 696), radius=18, fill=(8, 8, 8, 190))
    author_font = _font(28)
    draw.text((640, 653), "Mahant Rajesh Kumar Tiwari Ranjan",
              font=author_font, fill="white", anchor="mm",
              stroke_width=1, stroke_fill=(0, 0, 0, 220))

    # The original photograph is only resized proportionally, never retouched.
    photo_added = False
    if author_photo_path and Path(author_photo_path).is_file():
        photo = Image.open(author_photo_path).convert("RGB")
        photo.thumbnail((112, 150), Image.Resampling.LANCZOS)
        x, y = 38, 540
        image.paste(photo, (x, y))
        photo_added = True

    # Put topic text on a translucent panel so it remains legible on mobile.
    lines = _wrap_title(title)
    title_font = _font(66)
    while title_font.size > 40:
        max_width = max((draw.textbbox((0, 0), line, font=title_font)[2] for line in lines), default=0)
        if max_width <= 1120:
            break
        title_font = _font(title_font.size - 4)
    line_heights = [draw.textbbox((0, 0), line, font=title_font)[3] for line in lines]
    total_height = sum(line_heights) + (len(lines) - 1) * 18
    top = max(180, (720 - total_height) // 2)
    draw.rounded_rectangle((54, top - 28, 1226, top + total_height + 28),
                           radius=24, fill=(0, 0, 0, 115))
    y = top
    for line, line_height in zip(lines, line_heights):
        draw.text((640, y), line, font=title_font, fill="white", anchor="mt",
                  stroke_width=3, stroke_fill=(0, 0, 0, 230))
        y += line_height + 18

    final = Image.alpha_composite(image.convert("RGBA"), overlay)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    final.convert("RGB").save(output_path, format="PNG", optimize=True)
    return {"file": str(output_path), "author_photo_included": photo_added,
            "dimensions": "1280x720"}
