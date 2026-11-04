"""Compose fixed Hindi scripture thumbnails with the original author portrait on the LEFT."""
from pathlib import Path
import base64
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "author_photo.jpeg"
PHOTO_B64 = ROOT / "assets" / "author_photo.jpeg.b64"
DEVANAGARI_BOLD = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf")
DEVANAGARI_REGULAR = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf")


def _photo_path():
    if PHOTO.is_file():
        return PHOTO
    if not PHOTO_B64.is_file():
        raise FileNotFoundError("Original author photo asset is missing")
    PHOTO.write_bytes(base64.b64decode(PHOTO_B64.read_text(encoding="ascii").strip()))
    return PHOTO


def _font(size, bold=True):
    candidates = [DEVANAGARI_BOLD, DEVANAGARI_REGULAR] if bold else [DEVANAGARI_REGULAR, DEVANAGARI_BOLD]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def _clean_markup(value):
    value = str(value or "").replace(chr(96), "")
    value = re.sub(r"[\\*_]", "", value)
    return re.sub(r"\s+", " ", value).strip(" :-—")


def _brief_lines(final_package):
    return [line.strip() for line in str(final_package or "").splitlines() if line.strip()]


def _extract_headline(final_package, fallback):
    lines = _brief_lines(final_package)
    labels = ("संक्षिप्त हिंदी headline", "मुख्य headline", "thumbnail headline", "thumbnail text")
    for i, line in enumerate(lines):
        if any(label.lower() in line.lower() for label in labels):
            candidate = re.sub(
                r"^.*?(?:संक्षिप्त हिंदी headline|मुख्य headline|thumbnail headline|thumbnail text)\s*[:：]",
                "", line, flags=re.I)
            candidate = _clean_markup(candidate).strip("“”\"'")
            if candidate:
                return candidate
            if i + 1 < len(lines):
                return _clean_markup(lines[i + 1]).strip("“”\"'")
    return ""


def _extract_chapter_text(video, final_package):
    source = video.get("primary_scripture_source") or {}
    if source.get("status") != "matched":
        return ""
    chapter = video.get("chapter_number")
    title = video.get("chapter_title")
    if chapter and title:
        return f"अध्याय {chapter} — {title}"
    lines = _brief_lines(final_package)
    for line in lines:
        if "अध्याय-सूचना" in line or "अध्याय पहचान" in line:
            candidate = re.sub(r"^.*?(?:अध्याय-सूचना(?: एक साथ)?|अध्याय पहचान)\s*[:：]", "", line)
            candidate = _clean_markup(candidate).strip("“”\"'")
            if "अध्याय" in candidate and len(candidate) > 5:
                return candidate
    for line in lines:
        match = re.search(r"(अध्याय\s*[0-9०-९]+\s*[—-]\s*.+)", line)
        if match:
            return _clean_markup(match.group(1))
    return f"अध्याय {chapter}" if chapter else ""


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


def _centered(draw, xy, text, font, fill, stroke_width=2, stroke_fill=(18, 10, 3, 255)):
    draw.text(xy, text, font=font, fill=fill, anchor="mm",
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def _ornamental_plaque(draw, bounds, fill=(8, 20, 39, 238), outline=(239, 195, 103, 255), width=4):
    """Compact double-edged plaque with pointed ends, not a plain rectangle."""
    x1, y1, x2, y2 = bounds
    h = y2 - y1
    inset = min(32, h // 2)
    points = [(x1 + inset, y1), (x2 - inset, y1), (x2, y1 + h // 2),
              (x2 - inset, y2), (x1 + inset, y2), (x1, y1 + h // 2)]
    draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=outline, width=width, joint="curve")
    inner = [(x1 + inset + 9, y1 + 7), (x2 - inset - 9, y1 + 7),
             (x2 - 9, y1 + h // 2), (x2 - inset - 9, y2 - 7),
             (x1 + inset + 9, y2 - 7), (x1 + 9, y1 + h // 2)]
    draw.line(inner + [inner[0]], fill=(255, 232, 174, 180), width=2, joint="curve")


def _glow_text(draw, xy, text, font, fill):
    x, y = xy
    draw.text((x + 3, y + 5), text, font=font, fill=(0, 0, 0, 170), anchor="mm",
              stroke_width=7, stroke_fill=(0, 0, 0, 190))
    draw.text((x, y), text, font=font, fill=fill, anchor="mm",
              stroke_width=3, stroke_fill=(22, 12, 4, 245))


def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    if not background_path or not Path(background_path).is_file():
        raise FileNotFoundError(f"AI-generated thumbnail artwork missing: {background_path}")
    video = video or {}
    image = ImageOps.fit(Image.open(background_path).convert("RGB"), (1280, 720),
                         method=Image.Resampling.LANCZOS).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    programme = video.get("programme")
    if programme not in ("shiv_puran", "bhagavad_gita"):
        raise ValueError("Programme could not be identified; refusing to place an incorrect book label on the thumbnail.")
    book_label = "भगवद्गीता" if programme == "bhagavad_gita" else "शिव महापुराण"
    chapter_text = _extract_chapter_text(video, final_package)
    section_name = video.get("khanda_name")
    if section_name and section_name not in chapter_text:
        chapter_text = f"{section_name} — {chapter_text}"
    headline = _extract_headline(final_package, title)
    if not headline:
        raise ValueError("AI SEO package did not provide a usable thumbnail headline.")

    # FIXED TOP-MIDDLE identity: two Hindi lines in a compact ornamental plaque.
    _ornamental_plaque(draw, (340, 6, 940, 104), fill=(7, 19, 39, 225))
    _centered(draw, (640, 39), "ज्योतिर्लिंग शिवमठ", _font(38), (255, 239, 193, 255))
    _centered(draw, (640, 73), "बरौली, लखनऊ", _font(23), (255, 255, 255, 255),
              stroke_width=1, stroke_fill=(20, 12, 4, 255))

    # Main subject is directly over the artwork, never inside a large dark panel.
    headline_font = _font(65)
    headline_lines = _wrap_text(draw, headline, headline_font, 830, max_lines=3)
    if len(headline_lines) == 1:
        start_y, step = 330, 86
    elif len(headline_lines) == 2:
        start_y, step = 300, 84
    else:
        start_y, step = 270, 78
    for index, line in enumerate(headline_lines):
        _glow_text(draw, (790, start_y + index * step), line, headline_font,
                   (255, 225, 133, 255))

    # Chapter information sits immediately above the bottom book plaque.
    if chapter_text:
        chapter_font = _font(30)
        chapter_lines = _wrap_text(draw, chapter_text, chapter_font, 790, max_lines=2)
        chapter_start_y = 574 if len(chapter_lines) == 1 else 552
        for index, line in enumerate(chapter_lines):
            _glow_text(draw, (790, chapter_start_y + index * 38), line, chapter_font,
                       (255, 255, 255, 255))

    # Original author portrait stays on the LEFT, unflipped and unretouched.
    portrait = Image.open(_photo_path()).convert("RGB")
    portrait.thumbnail((238, 338), Image.Resampling.LANCZOS)
    x_photo, y_photo = 42, 190
    p = 7
    draw.rounded_rectangle((x_photo - p, y_photo - p,
                            x_photo + portrait.width + p, y_photo + portrait.height + p),
                           radius=22, fill=(245, 205, 105, 255),
                           outline=(255, 239, 190, 255), width=3)

    # FIXED BOTTOM-MIDDLE book name in Hindi.
    _ornamental_plaque(draw, (430, 644, 850, 710), fill=(7, 19, 39, 242), width=3)
    _centered(draw, (640, 677), book_label, _font(36), (255, 239, 193, 255))

    # Paste the exact original portrait after graphics so no overlay touches its pixels.
    image = Image.alpha_composite(image, overlay).convert("RGB")
    image.paste(portrait, (x_photo, y_photo))

    # Author name sits directly below the portrait: plain readable text, NO plaque or box.
    name_draw = ImageDraw.Draw(image)
    name = "महंत राजेश कुमार तिवारी ‘रंजन’"
    name_font = _font(18)
    name_lines = _wrap_text(name_draw, name, name_font, 270, max_lines=2)
    name_y = 548 if len(name_lines) == 1 else 541
    for line in name_lines:
        # A restrained local shadow keeps the lettering legible without adding a panel.
        name_draw.text((161 + 2, name_y + 3), line, font=name_font,
                       fill=(0, 0, 0, 190), anchor="mm",
                       stroke_width=3, stroke_fill=(0, 0, 0, 150))
        _centered(name_draw, (161, name_y), line, name_font,
                  (255, 248, 226, 255), stroke_width=1,
                  stroke_fill=(24, 15, 8, 255))
        name_y += 25

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {
        "file": str(output),
        "author_photo_included": True,
        "author_photo_source": "assets/author_photo.jpeg.b64",
        "author_photo_position": "left",
        "author_photo_unchanged": True,
        "master_template": "fixed_hindi_scripture_branding_v3_no_author_plaque",
        "programme_template": "fixed_hindi_scripture_branding_v2",
        "dimensions": "1280x720",
        "channel_header": "ज्योतिर्लिंग शिवमठ | बरौली, लखनऊ",
        "programme_label": book_label,
        "chapter_text": chapter_text or None,
        "chapter_verified": bool(video.get("primary_scripture_source", {}).get("status") == "matched" and video.get("chapter_number")),
        "thumbnail_headline": headline,
        "author_name": "महंत राजेश कुमार तिवारी ‘रंजन’",
        "background_overlay": "localized_text_shadow_only",
    }
