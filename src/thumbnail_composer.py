"""Compose thumbnails on the two fixed, user-approved master images.

The master artwork, portrait, channel identity, book label and frame are static.
Only the two manually supplied text fields are overlaid for each lesson.
Hindi, English and mixed-script copy use RAQM shaping and automatic wrapping.
"""
from pathlib import Path
import os
import re
import subprocess
from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1280, 720)
TEMPLATES = {
    "bhagavad_gita": ROOT / "assets" / "master_thumbnail_gita_blank_master.jpg",
    "shiv_puran": ROOT / "assets" / "master_thumbnail_shiv_puran_reference.jpg",
}


def _find_text_font():
    """Find a bold Noto Devanagari font; it also contains Latin glyphs."""
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "Noto Sans Devanagari:style=Bold"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        candidate = Path(result.stdout.strip())
        if candidate.is_file():
            return candidate
    except (OSError, subprocess.SubprocessError):
        pass

    roots = (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"))
    for root in roots:
        if root.exists():
            for pattern in ("*Devanagari*Bold*.ttf", "*NotoSans*Bold*.ttf"):
                matches = sorted(root.rglob(pattern))
                if matches:
                    return matches[0]
    raise RuntimeError(
        "A Noto Devanagari font was not found. Install fonts-noto-core and fontconfig."
    )


def _font(size):
    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow was built without libraqm; Hindi shaping is unavailable. "
            "Install libraqm, harfbuzz and fribidi, and use a Pillow build with RAQM."
        )
    return ImageFont.truetype(
        str(_find_text_font()), size, layout_engine=ImageFont.Layout.RAQM
    )


def _clean(value):
    value = str(value or "").replace("`", "")
    value = re.sub(r"[\\*_]", "", value)
    value = value.replace("•", " - ").replace("·", " - ")
    return re.sub(r"\\s+", " ", value).strip()


def _wrap_line(draw, text, font, max_width):
    """Greedy word wrapping, splitting an unusually long unbroken word safely."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if draw.textlength(word, font=font) <= max_width:
            current = word
            continue
        # Handle long URLs/compound words without allowing overflow.
        piece = ""
        for char in word:
            if piece and draw.textlength(piece + char, font=font) > max_width:
                lines.append(piece)
                piece = char
            else:
                piece += char
        current = piece
    if current:
        lines.append(current)
    return lines or [""]


def _fit_multiline(draw, text, max_width, max_height, start_size,
                   min_size=18, max_lines=3, stroke_width=2):
    """Shrink font and wrap to fit a fixed text area; return font and lines."""
    for size in range(start_size, min_size - 1, -2):
        font = _font(size)
        lines = _wrap_line(draw, text, font, max_width)
        spacing = max(1, size // 10)
        bounds = draw.multiline_textbbox(
            (0, 0), "\\n".join(lines), font=font, spacing=spacing,
            align="center", stroke_width=stroke_width,
        )
        height = bounds[3] - bounds[1]
        widest = max((draw.textlength(line, font=font) for line in lines), default=0)
        if len(lines) <= max_lines and widest <= max_width and height <= max_height:
            return font, lines, spacing, size
    # If still too long, preserve every word but return a clear overflow error
    # instead of silently clipping or shrinking to an unreadable size.
    font = _font(min_size)
    lines = _wrap_line(draw, text, font, max_width)
    if len(lines) > max_lines:
        raise ValueError(
            f"Thumbnail text is too long for this area at minimum font size {min_size}; "
            f"maximum is {max_lines} lines. Please shorten the text."
        )
    return font, lines, max(1, min_size // 10), min_size


def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    video = video or {}
    programme = video.get("programme")
    if programme not in TEMPLATES:
        raise ValueError("Programme must be bhagavad_gita or shiv_puran.")
    template = TEMPLATES[programme]
    if not template.is_file():
        raise FileNotFoundError(f"Approved master template missing: {template}")

    image = Image.open(template).convert("RGB")
    if image.size != SIZE:
        raise ValueError(f"Master template must be 1280x720, got {image.size}")
    draw = ImageDraw.Draw(image)

    # Manual values supplied in GitHub Actions take priority over AI-generated text.
    hook = _clean(video.get("manual_thumbnail_title") or os.getenv("THUMBNAIL_TRICKY_TITLE", ""))
    lesson = _clean(video.get("manual_thumbnail_lesson") or os.getenv("THUMBNAIL_LESSON_TEXT", ""))

    title_layout = None
    lesson_layout = None

    # Only user-entered copy is drawn. The approved artwork and identity never change.
    if hook:
        if programme == "shiv_puran":
            draw.rounded_rectangle(
                (520, 462, 1085, 550), radius=22,
                fill=(91, 0, 12), outline=(255, 205, 55), width=5,
            )
            draw.rounded_rectangle(
                (528, 470, 1077, 542), radius=17,
                outline=(255, 236, 145), width=2,
            )
        font, lines, spacing, size = _fit_multiline(
            draw, hook, max_width=510, max_height=76,
            start_size=46, min_size=20, max_lines=3, stroke_width=3,
        )
        draw.multiline_text(
            (802, 506), "\\n".join(lines), font=font,
            fill=(255, 244, 220), anchor="mm", align="center",
            spacing=spacing, stroke_width=3, stroke_fill=(58, 0, 0),
        )
        title_layout = {"font_size": size, "lines": len(lines)}

    if lesson:
        font, lines, spacing, size = _fit_multiline(
            draw, lesson, max_width=690, max_height=68,
            start_size=34, min_size=18, max_lines=2, stroke_width=2,
        )
        draw.multiline_text(
            (860, 665), "\\n".join(lines), font=font,
            fill=(0, 35, 190), anchor="mm", align="center",
            spacing=spacing, stroke_width=2, stroke_fill=(255, 224, 30),
        )
        lesson_layout = {"font_size": size, "lines": len(lines)}

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {
        "file": str(output),
        "master_template": template.name,
        "dimensions": "1280x720",
        "programme_label": "श्रीमद्भगवद्गीता" if programme == "bhagavad_gita" else "शिव महापुराण",
        "thumbnail_headline": hook or None,
        "chapter_text": lesson or None,
        "title_layout": title_layout,
        "lesson_layout": lesson_layout,
        "manual_text_fields": True,
        "automatic_font_sizing_and_wrapping": True,
        "supported_scripts": ["Devanagari", "Latin", "mixed"],
        "background_is_permanent": True,
        "author_portrait_and_identity_from_master": True,
        "youtube_uploaded": False,
    }
