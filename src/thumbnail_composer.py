"""Compose review thumbnails using the bundled legacy master frame."""
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "assets" / "karmsanyasyog.jpeg"

def _font(size):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)
    raise FileNotFoundError("Noto Devanagari font is required")

def _fit(draw, text, max_width, start=76, minimum=24):
    for size in range(start, minimum - 1, - 2):
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font, language="hi")
        if box[2] - box[0] <= max_width:
            return font
    return _font(minimum)

def _programme(video):
    text = (str(video.get("source_title") or video.get("title") or "") + " " +
            str(video.get("source_description") or video.get("description") or "")).lower()
    if any(word in text for word in ("bhagavad", "bhagwad", "गीता", "श्रीमद्भगवद्गीता")):
        return "bhagavadgita"
    if any(word in text for word in ("bhajan", "bhajans", "भजन", "सोमवार", "somvar", "somvaar", "monday")):
        return "bhajan"
    return "shivpuran"

def _chapter(text):
    match = re.search(r"(?:अध्याय|adhyay|chapter)\s*[-:：]?\s*(\d+)", text, re.I)
    return match.group(1) if match else None

def _gita_parts(video):
    raw = str(video.get("source_title") or video.get("title") or "धार्मिक प्रवचन").strip()
    raw = re.sub(r"^(?:अध्याय\s*)?\d+\s*[:：.\-—–]?\s*", "", raw).strip()
    parts = re.split(r"\s*[—–]\s*", raw, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

def _shiv_title(video):
    raw = str(video.get("source_title") or video.get("title") or "शिव महापुराण").strip()
    chapter = _chapter(raw)
    section = raw.split(" - ", 1)[0].strip()
    if "द्वितीय खंड" in raw:
        label = "श्री रुद्र संहिता — द्वितीय खंड"
    elif section and "संहिता" in section:
        label = section.replace("-", "—").strip()
    else:
        label = "श्री रुद्र संहिता"
    return f"{label} — अध्याय {chapter}" if chapter else label

def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    video = video or {"source_title": title}
    programme = _programme(video)
    if not MASTER.is_file():
        raise FileNotFoundError(f"Bundled master image missing: {MASTER}")
    # Start with the actual legacy JPEG: portrait, channel header, frame and author plaque stay intact.
    image = ImageOps.fit(Image.open(MASTER).convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
    # This is the exact story-art window from live_scheduler.py. Gita keeps its original Krishna-Arjuna art.
    if programme in ("shivpuran", "bhajan") and background_path and Path(background_path).is_file():
        art = ImageOps.fit(Image.open(background_path).convert("RGB"), (860, 410), method=Image.Resampling.LANCZOS)
        image.paste(art, (420, 78))

    draw = ImageDraw.Draw(image)
    if programme == "bhagavadgita":
        chapter_name, meaning = _gita_parts(video)
        if meaning:
            font = _fit(draw, meaning, 820, 35, 23)
            box = draw.textbbox((0, 0), meaning, font=font, language="hi", stroke_width=1)
            draw.text(((1280-(box[2]-box[0]))//2, 494-box[1]), meaning, font=font,
                      fill=(255,245,210), stroke_width=1, stroke_fill=(55,25,0), language="hi")
        plaque = (410, 550, 1248, 611)
        draw.rounded_rectangle(plaque, radius=15, fill=(2,14,35), outline=(246,190,35), width=3)
        font = _fit(draw, chapter_name, 790, 48, 25)
        box = draw.textbbox((0,0), chapter_name, font=font, language="hi", stroke_width=1)
        lines = [chapter_name]
        if box[2]-box[0] > 790:
            words = chapter_name.split()
            lines = [chapter_name]
            if len(words) > 1:
                candidates = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1,len(words))]
                lines = min(candidates, key=lambda pair: abs(len(pair[0])-len(pair[1])))
            font = _fit(draw, max(lines,key=len), 790, 36, 23)
            plaque = (410,536,1248,625)
            draw.rounded_rectangle(plaque, radius=15, fill=(2,14,35), outline=(246,190,35), width=3)
        boxes = [draw.textbbox((0,0), line, font=font, language="hi", stroke_width=1) for line in lines]
        heights = [b[3]-b[1] for b in boxes]
        y = plaque[1] + (plaque[3]-plaque[1]-(sum(heights)+2*(len(lines)-1)))//2
        for line, box, height in zip(lines, boxes, heights):
            x = plaque[0] + (plaque[2]-plaque[0]-(box[2]-box[0]))//2
            draw.text((x,y-box[1]), line, font=font, fill=(255,218,65), stroke_width=1,
                      stroke_fill=(105,34,0), language="hi")
            y += height + 2
    elif programme == "bhajan":
        # Bhajans have their own clean devotional layout: never show Shiv Puran chapter labels.
        hook = "भोलेनाथ के मधुर भजन"
        font = _fit(draw, hook, 820, 52, 30)
        box = draw.textbbox((0,0), hook, font=font, language="hi", stroke_width=1)
        draw.text(((1280-(box[2]-box[0]))//2,493-box[1]), hook, font=font,
                  fill=(255,245,210), stroke_width=1, stroke_fill=(55,25,0), language="hi")
        plaque = (410,550,1248,611)
        draw.rounded_rectangle(plaque, radius=15, fill=(2,14,35), outline=(246,190,35), width=3)
        headline = "सोमवार के शिव भजन"
        font = _fit(draw, headline, 790, 52, 30)
        box = draw.textbbox((0,0), headline, font=font, language="hi", stroke_width=1)
        x = plaque[0]+(plaque[2]-plaque[0]-(box[2]-box[0]))//2
        y = plaque[1]+(plaque[3]-plaque[1]-(box[3]-box[1]))//2-box[1]
        draw.text((x,y), headline, font=font, fill=(255,218,65), stroke_width=1,
                  stroke_fill=(105,34,0), language="hi")
        footer = (410,625,1248,686)
        draw.rounded_rectangle(footer, radius=15, fill=(20,13,12), outline=(246,190,35), width=3)
        draw.rounded_rectangle((418,632,1240,679), radius=10, outline=(125,83,22), width=2)
        footer_text = "हर हर महादेव"
        font = _fit(draw, footer_text, 790, 45, 30)
        box = draw.textbbox((0,0), footer_text, font=font, language="hi")
        x = footer[0]+(footer[2]-footer[0]-(box[2]-box[0]))//2
        y = footer[1]+(footer[3]-footer[1]-(box[3]-box[1]))//2-box[1]
        draw.text((x,y), footer_text, font=font, fill=(255,218,65), stroke_width=1,
                  stroke_fill=(65,30,0), language="hi")
    else:
        raw = str(video.get("source_title") or video.get("title") or "शिव महापुराण").strip()
        hook = ("जब वीरभद्र ने रोक दिया श्रीहरि का सुदर्शन चक्र!" if
                "श्रीहरि और वीरभद्र का युद्ध" in raw else re.sub(r"^.*?\s-\s*", "", raw, count=1).strip() or raw)
        font = _fit(draw, hook, 820, 38, 23)
        box = draw.textbbox((0,0), hook, font=font, language="hi", stroke_width=1)
        draw.text(((1280-(box[2]-box[0]))//2,493-box[1]), hook, font=font,
                  fill=(255,245,210), stroke_width=1, stroke_fill=(55,25,0), language="hi")
        chapter_title = _shiv_title(video)
        plaque = (410,550,1248,611)
        draw.rounded_rectangle(plaque, radius=15, fill=(2,14,35), outline=(246,190,35), width=3)
        font = _fit(draw, chapter_title, 790, 42, 22)
        box = draw.textbbox((0,0), chapter_title, font=font, language="hi", stroke_width=1)
        x = plaque[0]+(plaque[2]-plaque[0]-(box[2]-box[0]))//2
        y = plaque[1]+(plaque[3]-plaque[1]-(box[3]-box[1]))//2-box[1]
        draw.text((x,y), chapter_title, font=font, fill=(255,218,65), stroke_width=1,
                  stroke_fill=(105,34,0), language="hi")
        footer = (410,625,1248,686)
        draw.rounded_rectangle(footer, radius=15, fill=(20,13,12), outline=(246,190,35), width=3)
        draw.rounded_rectangle((418,632,1240,679), radius=10, outline=(125,83,22), width=2)
        text = "शिव महापुराण"
        font = _fit(draw, text, 790, 45, 30)
        box = draw.textbbox((0,0), text, font=font)
        x = footer[0]+(footer[2]-footer[0]-(box[2]-box[0]))//2
        y = footer[1]+(footer[3]-footer[1]-(box[3]-box[1]))//2-box[1]
        draw.text((x,y), text, font=font, fill=(255,218,65), stroke_width=1, stroke_fill=(65,30,0))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {"file": str(output), "author_photo_included": True,
            "master_template": "assets/karmsanyasyog.jpeg",
            "programme_template": programme, "dimensions": "1280x720"}
