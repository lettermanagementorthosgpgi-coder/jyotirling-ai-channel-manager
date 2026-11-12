"""Compose thumbnails on the two fixed, user-approved master images.

The master artwork, portrait, channel identity, book label and frame are static.
Only the two manually supplied text fields are overlaid for each lesson.
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
def _find_devanagari_font():
    # Resolve the actual installed font through fontconfig; package versions
    # use different Noto Devanagari filenames across Ubuntu releases.
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
            matches = sorted(root.rglob("*Devanagari*Bold*.ttf"))
            if matches:
                return matches[0]
    raise RuntimeError(
        "Noto Sans Devanagari Bold font not found. Install fonts-noto-core and fontconfig."
    )


def _font(size):
    path = _find_devanagari_font()
    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow was built without libraqm; Hindi shaping is unavailable. "
            "Install libraqm/harfbuzz/fribidi and a Pillow build with RAQM support."
        )
    return ImageFont.truetype(
        str(path), size, layout_engine=ImageFont.Layout.RAQM
    )


def _clean(value):
    value = str(value or "").replace("`", "")
    value = re.sub(r"[\\*_]", "", value)
    value = value.replace("•", " - ").replace("·", " - ")
    return re.sub(r"\s+", " ", value).strip()


def _fit_font(draw, text, max_width, start_size, min_size=22):
    for size in range(start_size, min_size - 1, -2):
        font = _font(size)
        if draw.textbbox((0, 0), text, font=font, stroke_width=2)[2] <= max_width:
            return font
    return _font(min_size)


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

    # Manual values supplied in the GitHub Actions Run workflow take priority.
    hook = _clean(video.get("manual_thumbnail_title") or os.getenv("THUMBNAIL_TRICKY_TITLE", ""))
    lesson = _clean(video.get("manual_thumbnail_lesson") or os.getenv("THUMBNAIL_LESSON_TEXT", ""))

    # Draw only user-entered copy. Empty values leave the template untouched.
    # The artwork, portrait, author plaque, book name and channel header are never regenerated.
    if hook:
        if programme == "shiv_puran":
            draw.rounded_rectangle((520, 462, 1085, 550), radius=22,
                                   fill=(91, 0, 12), outline=(255, 205, 55), width=5)
            draw.rounded_rectangle((528, 470, 1077, 542), radius=17,
                                   outline=(255, 236, 145), width=2)
        font = _fit_font(draw, hook, 510, 46, 24)
        draw.text((802, 506), hook, font=font, fill=(255, 244, 220),
                  anchor="mm", stroke_width=3, stroke_fill=(58, 0, 0))

    if lesson:
        font = _fit_font(draw, lesson, 690, 34, 20)
        draw.text((860, 665), lesson, font=font, fill=(0, 35, 190),
                  anchor="mm", stroke_width=2, stroke_fill=(255, 224, 30))

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
        "manual_text_fields": True,
        "background_is_permanent": True,
        "author_portrait_and_identity_from_master": True,
        "youtube_uploaded": False,
    }
