"""Reuse the exact legacy master-thumbnail frame and overlay logic."""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

MASTER_URL = (
    "https://raw.githubusercontent.com/"
    "lettermanagementorthosgpgi-coder/jyotirlingshivmathlive/main/"
    "karmsanyasyog.jpeg"
)


def _ensure_master(master_path):
    path = Path(master_path)
    if path.is_file() and path.stat().st_size > 20000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        MASTER_URL, headers={"User-Agent": "Jyotirling-AI-Channel-Manager"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
    if len(content) < 20000:
        raise RuntimeError("Legacy master thumbnail download is incomplete")
    path.write_bytes(content)
    return path


def _font_path():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Noto Devanagari font not installed")


def _fit_font(draw, text, font_path, max_width, start_size=76, min_size=23):
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(
            font_path, size=size, layout_engine=ImageFont.Layout.RAQM
        )
        box = draw.textbbox((0, 0), text, font=font, language="hi")
        if box[2] - box[0] <= max_width:
            return font
    return ImageFont.truetype(
        font_path, size=min_size, layout_engine=ImageFont.Layout.RAQM
    )


def _balanced_lines(text):
    words = text.split()
    if len(words) < 2:
        return [text]
    choices = []
    for index in range(1, len(words)):
        left, right = " ".join(words[:index]), " ".join(words[index:])
        choices.append((abs(len(left) - len(right)), [left, right]))
    return min(choices, key=lambda item: item[0])[1]


def _thumbnail_labels(video, final_package):
    title = str(video.get("source_title") or video.get("title") or "धार्मिक प्रवचन").strip()
    is_shiv = bool(re.search(r"शिव\s*पुराण|shiv\s*puran|रुद्र\s*संहिता", title, re.I))
    chapter = re.search(r"(?:अध्याय|chapter|adhyay)\s*[-:]?\s*(\d+)", title, re.I)
    chapter_text = f"अध्याय {chapter.group(1)}" if chapter else ""
    clean = re.sub(r"^(?:अध्याय\s*)?\d+\s*[:：.\-—–]?\s*", "", title).strip()
    clean = re.sub(r"^(?:श्री\s*)?(?:शिव\s*पुराण|शिवपुराण|रुद्र\s*संहिता)\s*[-—:：]?\s*", "", clean, flags=re.I).strip()
    if is_shiv:
        section = "श्री रुद्र संहिता"
        if "द्वितीय खंड" in title:
            section = "श्री रुद्र संहिता — द्वितीय खंड"
        if chapter_text:
            section += " — " + chapter_text
        topic = clean or title
        return "shivpuran", topic, section, "शिव महापुराण"

    # Use the AI-reviewed Hindi headline when the video title is too long.
    headline = ""
    for pattern in (r"(?:THUMBNAIL_HEADLINE|thumbnail_headline|मुख्य शीर्षक)\s*[:：]\s*([^\n]+)",
                    r'"thumbnail_headline"\s*:\s*"([^"]+)"'):
        match = re.search(pattern, final_package, re.I)
        if match:
            headline = match.group(1).strip()
            break
    topic = headline or clean or title
    gita_chapter = chapter_text or (f"अध्याय {chapter.group(1)}" if chapter else "")
    return "bhagavadgita", topic, gita_chapter or clean, "श्रीमद्भगवद्गीता"


def compose_thumbnail(background_path, output_path, title, author_photo_path=None,
                      master_path="assets/karmsanyasyog.jpeg", video=None,
                      final_package=""):
    """Keep the legacy master frame, portrait, plaques, header and footer intact."""
    video = dict(video or {})
    video.setdefault("source_title", title)
    base = Image.open(_ensure_master(master_path)).convert("RGB")
    base = ImageOps.fit(base, (1280, 720), method=Image.Resampling.LANCZOS)

    programme, topic, chapter_label, footer = _thumbnail_labels(video, final_package)

    # Legacy layout: only replace the central/right story-art window for Shiv Puran.
    if programme == "shivpuran" and background_path and Path(background_path).is_file():
        generated = Image.open(background_path).convert("RGB")
        generated = ImageOps.fit(
            generated, (860, 410), method=Image.Resampling.LANCZOS
        )
        base.paste(generated, (420, 78))

    draw = ImageDraw.Draw(base)
    font_path = _font_path()

    # The original master already contains the fixed channel header,
    # original speaker photograph, author plaque and decorative framing.
    # Add only the episode hook and dynamic chapter/section labels.
    topic = topic[:110]
    hook_font = _fit_font(draw, topic, font_path, 820, 38, 23)
    hook_box = draw.textbbox((0, 0), topic, font=hook_font, language="hi", stroke_width=1)
    hook_width = hook_box[2] - hook_box[0]
    draw.text(
        ((1280-hook_width)//2, 493-hook_box[1]), topic, font=hook_font,
        fill=(255, 245, 210), stroke_width=1, stroke_fill=(55, 25, 0),
        language="hi"
    )

    if chapter_label:
        plaque = (410, 550, 1248, 611)
        draw.rounded_rectangle(
            plaque, radius=15, fill=(2, 14, 35), outline=(246, 190, 35), width=3
        )
        lines = [chapter_label]
        font = _fit_font(draw, chapter_label, font_path, 790, 42, 22)
        box = draw.textbbox((0, 0), chapter_label, font=font, language="hi", stroke_width=1)
        if box[2] - box[0] > 790:
            lines = _balanced_lines(chapter_label)
            font = _fit_font(draw, max(lines, key=len), font_path, 790, 36, 22)
            plaque = (410, 536, 1248, 625)
            draw.rounded_rectangle(
                plaque, radius=15, fill=(2, 14, 35), outline=(246, 190, 35), width=3
            )
        boxes = [draw.textbbox((0, 0), line, font=font, language="hi", stroke_width=1) for line in lines]
        heights = [b[3]-b[1] for b in boxes]
        gap = 2
        y = plaque[1] + (plaque[3]-plaque[1]-(sum(heights)+gap*(len(lines)-1)))//2
        for line, box, height in zip(lines, boxes, heights):
            width = box[2]-box[0]
            x = plaque[0] + (plaque[2]-plaque[0]-width)//2
            draw.text((x, y-box[1]), line, font=font, fill=(255,218,65),
                      stroke_width=1, stroke_fill=(105,34,0), language="hi")
            y += height + gap

    if programme == "shivpuran":
        footer_banner = (410, 625, 1248, 686)
        draw.rounded_rectangle(
            footer_banner, radius=15, fill=(20,13,12), outline=(246,190,35), width=3
        )
        draw.rounded_rectangle((418,632,1240,679), radius=10, outline=(125,83,22), width=2)
        font = _fit_font(draw, footer, font_path, 790, 45, 30)
        box = draw.textbbox((0,0), footer, font=font)
        width, height = box[2]-box[0], box[3]-box[1]
        x = footer_banner[0] + (footer_banner[2]-footer_banner[0]-width)//2
        y = footer_banner[1] + (footer_banner[3]-footer_banner[1]-height)//2-box[1]
        draw.text((x,y), footer, font=font, fill=(255,218,65),
                  stroke_width=1, stroke_fill=(65,30,0))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    base.save(output_path, "JPEG", quality=94, optimize=True)
    return {"file": str(output_path), "author_photo_included": True,
            "dimensions": "1280x720", "master_template": "legacy-karmsanyasyog.jpeg",
            "layout_source": "jyotirlingshivmathlive/live_scheduler.py"}
