"""Render the user's exact Shiv Puran master thumbnail without altering fixed branding.

The source master is an input asset and is never overwritten. Only the central
art window and the chapter subtitle inside the existing footer plaque are
updated. Unknown chapter data is rejected (manual mode).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = ROOT / "assets" / "shiv_puran_master.png"
SIZE = (1280, 720)

# Coordinates below are measured against the supplied 1672x941 master and
# scaled proportionally to 1280x720. The portrait, header, name plaque,
# upper "शिव पुराण कथा" plaque, outer border and "Shiv Puran" title are kept.
MASTER_SIZE = (1672, 941)
ART_WINDOW = (640, 304, 1660, 744)       # central scenery only
CHAPTER_WINDOW = (690, 852, 1510, 906)  # existing English subtitle only


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold else [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("Hindi font unavailable. Install fonts-noto-core on the runner.")


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int,
              start: int, minimum: int = 18) -> ImageFont.FreeTypeFont:
    for size in range(start, minimum - 1, -1):
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        if box[2] - box[0] <= max_width:
            return font
    raise ValueError("Chapter text is too long to fit the fixed footer subtitle area.")


def _scale_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    sx, sy = SIZE[0] / MASTER_SIZE[0], SIZE[1] / MASTER_SIZE[1]
    return tuple(round(v * (sx if i % 2 == 0 else sy))
                 for i, v in enumerate(box))


def render(master_path: Path, background_path: Path, output_path: Path,
           chapter_text: str, topic_title: str = "") -> Path:
    if not chapter_text.strip():
        raise ValueError("Chapter information is required; manual mode: supply --chapter-text.")
    if not master_path.is_file():
        raise FileNotFoundError(
            f"Master image not found: {master_path}. Add the user's exact image at "
            "assets/shiv_puran_master.png; do not substitute another design."
        )
    if not background_path.is_file():
        raise FileNotFoundError(f"Central background image not found: {background_path}")

    master = Image.open(master_path).convert("RGBA")
    if master.size != MASTER_SIZE:
        raise ValueError(f"Expected supplied master size {MASTER_SIZE}, got {master.size}.")
    master = master.resize(SIZE, Image.Resampling.LANCZOS)

    # Replace only the scenery window; all fixed master artwork remains untouched.
    art_box = _scale_box(ART_WINDOW)
    art = ImageOps.fit(
        Image.open(background_path).convert("RGB"),
        (art_box[2] - art_box[0], art_box[3] - art_box[1]),
        method=Image.Resampling.LANCZOS,
    ).convert("RGBA")
    master.alpha_composite(art, (art_box[0], art_box[1]))

    # Small, readable topic label over the central art; keep it clear of portrait
    # and fixed upper plaque. Omit when no verified topic title is supplied.
    if topic_title.strip():
        draw = ImageDraw.Draw(master)
        cx = round((art_box[0] + art_box[2]) / 2)
        cy = art_box[1] + 46
        font = _fit_font(draw, topic_title.strip(), 560, 34, 20)
        draw.rounded_rectangle((cx - 300, cy - 26, cx + 300, cy + 27),
                               radius=16, fill=(93, 8, 4, 225),
                               outline=(255, 211, 93, 255), width=3)
        draw.text((cx, cy), topic_title.strip(), font=font, fill=(255, 246, 205, 255),
                  anchor="mm", stroke_width=1, stroke_fill=(45, 10, 0, 255))

    # Replace only the old English chapter line inside the existing footer plaque.
    chapter_box = _scale_box(CHAPTER_WINDOW)
    draw = ImageDraw.Draw(master)
    x1, y1, x2, y2 = chapter_box
    draw.rectangle((x1, y1, x2, y2), fill=(177, 9, 7, 255))
    text = chapter_text.strip()
    font = _fit_font(draw, text, x2 - x1 - 34, 33, 17)
    draw.text(((x1 + x2) // 2, (y1 + y2) // 2), text, font=font,
              fill=(255, 255, 255, 255), anchor="mm",
              stroke_width=2, stroke_fill=(45, 5, 0, 255))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    master.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--chapter-text", required=True,
                        help='Verified Hindi line, e.g. "रुद्र संहिता खंड 5, अध्याय 6"')
    parser.add_argument("--topic-title", default="",
                        help="Optional verified short searchable Hindi topic title")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "shiv_puran_thumbnail.png")
    args = parser.parse_args()
    result = render(args.master, args.background, args.output,
                    args.chapter_text, args.topic_title)
    print(f"Thumbnail created: {result}")


if __name__ == "__main__":
    main()
