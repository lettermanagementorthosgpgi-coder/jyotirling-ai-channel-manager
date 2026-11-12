"""Render the user-approved red/gold 16:9 scripture thumbnail layout.

Permanent elements: channel header, author portrait/name, decorative frame and
plaque geometry. Variable elements: scripture book, chapter-grounded hook,
verified lesson/chapter line, and generated devotional background.
"""
from pathlib import Path
import base64
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "author_photo.jpeg"
PHOTO_B64 = ROOT / "assets" / "author_photo.jpeg.b64"
DEVANAGARI_BOLD = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf")
DEVANAGARI_REGULAR = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf")
SIZE = (1280, 720)


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


def _clean(value):
    value = str(value or "").replace(chr(96), "")
    value = re.sub(r"[\*_]", "", value)
    return re.sub(r"\s+", " ", value).strip(" :-—“”\"'")


def _wrap(draw, text, font, max_width, max_lines=2):
    words = _clean(text).split()
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


def _text_center(draw, xy, text, font, fill, stroke=(28, 5, 3, 255), sw=3):
    draw.text(xy, text, font=font, fill=fill, anchor="mm",
              stroke_width=sw, stroke_fill=stroke)


def _red_gold_plaque(draw, bounds, radius=34, fill=(166, 0, 12, 248)):
    x1, y1, x2, y2 = bounds
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius,
                           fill=fill, outline=(255, 215, 90, 255), width=8)
    inset = 9
    draw.rounded_rectangle((x1+inset, y1+inset, x2-inset, y2-inset),
                           radius=max(8, radius-8), outline=(255, 239, 164, 255), width=3)
    draw.rounded_rectangle((x1+16, y1+16, x2-16, y2-16),
                           radius=max(6, radius-14), outline=(255, 145, 20, 220), width=2)


def _extract_headline(final_package, fallback):
    lines = [line.strip() for line in str(final_package or "").splitlines() if line.strip()]
    labels = ("संक्षिप्त हिंदी headline", "मुख्य headline", "thumbnail headline",
              "thumbnail text", "tricky topic", "ट्रिकी टॉपिक", "जिज्ञासा")
    for i, line in enumerate(lines):
        if any(label.lower() in line.lower() for label in labels):
            candidate = re.sub(
                r"^.*?(?:संक्षिप्त हिंदी headline|मुख्य headline|thumbnail headline|thumbnail text|tricky topic|ट्रिकी टॉपिक|जिज्ञासा)\s*[:：-]\s*",
                "", line, flags=re.I)
            candidate = _clean(candidate)
            if candidate:
                return candidate
            if i + 1 < len(lines):
                return _clean(lines[i + 1])
    return _clean(fallback)


def _extract_verified_lesson(video):
    source = video.get("primary_scripture_source") or {}
    if source.get("status") == "matched" and source.get("chapter_heading_verified"):
        heading = _clean(source.get("verified_chapter_heading"))
        if heading:
            section = _clean(video.get("khanda_name"))
            if section and section not in heading:
                return f"{section} — {heading}"
            return heading

    # A configured programme-feed chapter number is safe to show as a lesson
    # locator, but do not invent or print an unverified chapter title.
    chapter = video.get("chapter_number")
    if not chapter:
        feed = video.get("programme_feed") or {}
        chapter = feed.get("chapter_number")
    if not chapter:
        return ""
    section = _clean(video.get("khanda_name") or (video.get("programme_feed") or {}).get("section_name"))
    if video.get("programme") == "bhagavad_gita":
        verse_start = video.get("verse_start") or (video.get("programme_feed") or {}).get("verse_start")
        verse_end = video.get("verse_end") or (video.get("programme_feed") or {}).get("verse_end")
        if verse_start and verse_end:
            return f"अध्याय {chapter} • श्लोक {verse_start}–{verse_end} का भावार्थ"
        return f"अध्याय {chapter}"
    prefix = f"{section} • " if section else ""
    return f"{prefix}अध्याय {chapter}"


def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    if not background_path or not Path(background_path).is_file():
        raise FileNotFoundError(f"AI-generated thumbnail artwork missing: {background_path}")
    video = video or {}
    programme = video.get("programme")
    if programme not in ("shiv_puran", "bhagavad_gita"):
        raise ValueError("Programme could not be identified; refusing an incorrect scripture label.")

    image = ImageOps.fit(Image.open(background_path).convert("RGB"), SIZE,
                         method=Image.Resampling.LANCZOS).convert("RGBA")
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    book_label = "श्रीमद्भगवद्गीता" if programme == "bhagavad_gita" else "शिव महापुराण"
    headline = _extract_headline(final_package, title)
    if not headline:
        raise ValueError("AI package did not provide a usable Hindi Tricky Topic.")
    lesson = _extract_verified_lesson(video)

    # Permanent top identity banner (same position and two-line wording on every video).
    _red_gold_plaque(draw, (278, 5, 1268, 119), radius=54)
    _text_center(draw, (773, 46), "JYOTIRLING SHIVMATH", _font(46), (255, 245, 45, 255), sw=4)
    _text_center(draw, (773, 91), "BARAULI LUCKNOW", _font(36), (255, 255, 255, 255), sw=4)

    # Variable scripture title banner: Gita or Shiv Mahapuran.
    _red_gold_plaque(draw, (380, 130, 1248, 243), radius=48)
    book_font = _font(65)
    book_lines = _wrap(draw, book_label, book_font, 790, max_lines=1)
    _text_center(draw, (814, 188), book_lines[0], book_font, (255, 239, 32, 255), sw=5)

    # Main variable hook is deliberately in the old large "अध्याय 2" location.
    hook_font = _font(58)
    hook_lines = _wrap(draw, headline, hook_font, 735, max_lines=2)
    hook_y = 465 if len(hook_lines) == 1 else 438
    for i, line in enumerate(hook_lines):
        # Semi-transparent dark local shadow only; generated artwork remains visible.
        draw.text((820+3, hook_y+i*67+4), line, font=hook_font, fill=(0,0,0,160),
                  anchor="mm", stroke_width=7, stroke_fill=(0,0,0,150))
        _text_center(draw, (820, hook_y+i*67), line, hook_font,
                     (255, 239, 215, 255), sw=4)

    # Lesson/chapter strip at the bottom is printed only when the source verifies it.
    if lesson:
        _red_gold_plaque(draw, (460, 620, 1268, 710), radius=34, fill=(179, 0, 10, 250))
        lesson_font = _font(34)
        lesson_lines = _wrap(draw, lesson, lesson_font, 750, max_lines=2)
        if len(lesson_lines) == 1:
            _text_center(draw, (864, 665), lesson_lines[0], lesson_font,
                         (255, 245, 45, 255), sw=3)
        else:
            _text_center(draw, (864, 649), lesson_lines[0], _font(29),
                         (255, 245, 45, 255), sw=3)
            _text_center(draw, (864, 683), lesson_lines[1], _font(29),
                         (255, 245, 45, 255), sw=3)

    # Original author photograph remains on the left, unchanged and unflipped.
    portrait = Image.open(_photo_path()).convert("RGB")
    portrait.thumbnail((395, 515), Image.Resampling.LANCZOS)
    px, py = 18, 48
    image = Image.alpha_composite(image, overlay).convert("RGB")
    image.paste(portrait, (px, py))

    # Permanent author-name plaque and professional descriptor.
    name_draw = ImageDraw.Draw(image)
    _red_gold_plaque(name_draw, (12, 570, 448, 680), radius=30, fill=(166, 0, 12, 250))
    _text_center(name_draw, (230, 612), "Mahant Rajesh Kumar", _font(29), (255,255,255,255), sw=3)
    _text_center(name_draw, (230, 645), "Tiwari “Ranjan”", _font(29), (255,255,255,255), sw=3)
    _text_center(name_draw, (230, 690), "लेखक • कवि • योगाचार्य • आध्यात्मिक विद्वान",
                 _font(17), (255,255,255,255), sw=2)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {
        "file": str(output),
        "master_template": "user_approved_red_gold_scripture_layout_v1",
        "dimensions": "1280x720",
        "author_photo_included": True,
        "author_photo_source": "assets/author_photo.jpeg.b64",
        "author_photo_position": "left",
        "author_photo_unchanged": True,
        "channel_header": "JYOTIRLING SHIVMATH / BARAULI LUCKNOW",
        "programme_label": book_label,
        "thumbnail_headline": headline,
        "chapter_text": lesson or None,
        "chapter_verified": bool(lesson),
        "author_name": "Mahant Rajesh Kumar Tiwari “Ranjan”",
        "layout_policy": "fixed identity and plaques; only book, hook, verified lesson and devotional artwork vary"
    }
