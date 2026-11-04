"""Compose finished scripture thumbnails with exact channel text and the supplied original portrait."""
from pathlib import Path
import base64
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "author_photo.jpeg"
PHOTO_B64 = ROOT / "assets" / "author_photo.jpeg.b64"
DEVANAGARI_BOLD = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf")
DEVANAGARI_REGULAR = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf")
LATIN_BOLD = Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf")
LATIN_REGULAR = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")


def _photo_path():
    if PHOTO.is_file():
        return PHOTO
    if not PHOTO_B64.is_file():
        raise FileNotFoundError("Author photo asset is missing")
    PHOTO.write_bytes(base64.b64decode(PHOTO_B64.read_text(encoding="ascii").strip()))
    return PHOTO


def _font(size, devanagari=True, bold=True):
    candidates = (
        [DEVANAGARI_BOLD, DEVANAGARI_REGULAR] if devanagari and bold else
        [DEVANAGARI_REGULAR, DEVANAGARI_BOLD] if devanagari else
        [LATIN_BOLD, LATIN_REGULAR] if bold else
        [LATIN_REGULAR, LATIN_BOLD]
    )
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def _clean_markup(value):
    value = re.sub(r"[\*_`]", "", str(value or ""))
    return re.sub(r"\s+", " ", value).strip(" :-—")


def _brief_lines(final_package):
    return [line.strip() for line in str(final_package or "").splitlines() if line.strip()]


def _extract_headline(final_package, fallback):
    lines = _brief_lines(final_package)
    for i, line in enumerate(lines):
        if "संक्षिप्त हिंदी headline" in line or "मुख्य headline" in line:
            candidate = re.sub(r"^.*?(?:संक्षिप्त हिंदी headline|मुख्य headline)\s*[:：]", "", line, flags=re.I)
            candidate = _clean_markup(candidate)
            if candidate:
                return candidate.strip("“”\"'")
            if i + 1 < len(lines):
                return _clean_markup(lines[i + 1]).strip("“”\"'")
    return fallback


def _extract_chapter_text(video, final_package):
    chapter = video.get("chapter_number")
    title = video.get("chapter_title")
    if chapter and title:
        return f"अध्याय {chapter} — {title}"
    lines = _brief_lines(final_package)
    for line in lines:
        if "अध्याय-सूचना" in line or "अध्याय पहचान" in line:
            candidate = re.sub(r"^.*?(?:अध्याय-सूचना(?: एक साथ)?|अध्याय पहचान)\s*[:：]", "", line)
            candidate = _clean_markup(candidate).strip("“”\"'")
            if "अध्याय" in candidate and len(candidate) > 8:
                return candidate
    for line in lines:
        match = re.search(r"`(अध्याय\s*[0-9०-९]+\s*[—-]\s*[^`]+)`", line)
        if match:
            return _clean_markup(match.group(1))
    return f"अध्याय {chapter}" if chapter else "विशेष आध्यात्मिक प्रवचन"


def _wrap_text(draw, text, font, max_width, max_lines=2):
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + "…"
    return lines


def _draw_centered(draw, xy, text, font, fill, anchor="mm", stroke_width=0, stroke_fill=(0, 0, 0)):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    if not background_path or not Path(background_path).is_file():
        raise FileNotFoundError(f"AI-generated thumbnail artwork missing: {background_path}")
    video = video or {}
    image = ImageOps.fit(Image.open(background_path).convert("RGB"), (1280, 720),
                         method=Image.Resampling.LANCZOS).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    programme = video.get("programme")
    programme_label = "BHAGVADGITA" if programme == "bhagavad_gita" else "SHIV MAHA PURAN"
    chapter_text = _extract_chapter_text(video, final_package)
    headline = _extract_headline(final_package, chapter_text)

    # Clear, exact channel header.
    draw.rounded_rectangle((36, 22, 1244, 94), radius=22,
                           fill=(7, 15, 31, 225), outline=(235, 190, 94, 255), width=3)
    header_font = _font(32, devanagari=False, bold=True)
    _draw_centered(draw, (640, 58), "JYOTIRLING SHIVMATH BARAULI LUCKNOW",
                   header_font, (255, 248, 226, 255), stroke_width=1, stroke_fill=(0, 0, 0, 220))

    # Programme label.
    draw.rounded_rectangle((54, 120, 430, 178), radius=18,
                           fill=(222, 171, 65, 245), outline=(255, 236, 180, 255), width=2)
    programme_font = _font(28, devanagari=False, bold=True)
    _draw_centered(draw, (242, 149), programme_label, programme_font, (26, 20, 12, 255))

    # Main information panel; it protects typography from busy or bright AI artwork.
    draw.rounded_rectangle((42, 202, 930, 602), radius=30,
                           fill=(5, 12, 27, 178), outline=(231, 184, 82, 230), width=3)
    headline_font = _font(62, devanagari=True, bold=True)
    headline_lines = _wrap_text(draw, headline, headline_font, 820, max_lines=2)
    y = 286 if len(headline_lines) == 1 else 260
    for line in headline_lines:
        draw.text((82, y), line, font=headline_font, fill=(255, 225, 142, 255),
                  stroke_width=3, stroke_fill=(20, 13, 5, 255))
        y += 84

    chapter_font = _font(31, devanagari=True, bold=True)
    chapter_lines = _wrap_text(draw, chapter_text, chapter_font, 820, max_lines=2)
    chapter_y = max(y + 24, 455)
    for line in chapter_lines:
        draw.text((84, chapter_y), line, font=chapter_font, fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 255))
        chapter_y += 48

    # Composite the supplied real portrait at its original aspect ratio, without cropping or retouching.
    portrait = Image.open(_photo_path()).convert("RGB")
    portrait.thumbnail((248, 360), Image.Resampling.LANCZOS)
    x = 1280 - portrait.width - 34
    y_photo = 214
    p = 7
    draw.rounded_rectangle((x-p, y_photo-p, x+portrait.width+p, y_photo+portrait.height+p),
                           radius=18, fill=(245, 205, 105, 255),
                           outline=(255, 239, 190, 255), width=3)

    # Merge the graphic elements, then paste the unaltered portrait pixels.
    image = Image.alpha_composite(image, overlay).convert("RGB")
    image.paste(portrait, (x, y_photo))

    # Name plaque below the portrait.
    draw_name = ImageDraw.Draw(image)
    name_font = _font(18, devanagari=False, bold=True)
    name = "Mahant Rajesh Kumar Tiwari Ranjan"
    name_lines = _wrap_text(draw_name, name, name_font, 270, max_lines=2)
    plaque_top = min(610, y_photo + portrait.height + 16)
    draw_name.rounded_rectangle((x-28, plaque_top, 1260, min(696, plaque_top + 62)),
                                radius=12, fill=(7, 15, 31), outline=(235, 190, 94), width=2)
    line_y = plaque_top + 10
    for line in name_lines:
        draw_name.text((x-15, line_y), line, font=name_font, fill=(255, 248, 226),
                       stroke_width=1, stroke_fill=(0, 0, 0))
        line_y += 22

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {
        "file": str(output),
        "author_photo_included": True,
        "author_photo_source": "assets/author_photo.jpeg",
        "master_template": None,
        "programme_template": "ai_creative_with_brand_typography",
        "dimensions": "1280x720",
        "channel_header": "JYOTIRLING SHIVMATH BARAULI LUCKNOW",
        "programme_label": programme_label,
        "chapter_text": chapter_text,
        "thumbnail_headline": headline,
        "author_name": "Mahant Rajesh Kumar Tiwari Ranjan",
        "author_photo_unchanged": True,
    }
