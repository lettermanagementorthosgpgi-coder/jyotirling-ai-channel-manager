"""Compose AI-designed thumbnails and overlay the supplied original host portrait."""
from pathlib import Path
import base64
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "author_photo.jpeg"
PHOTO_B64 = ROOT / "assets" / "author_photo.jpeg.b64"

def _photo_path():
    if PHOTO.is_file():
        return PHOTO
    if not PHOTO_B64.is_file():
        raise FileNotFoundError("Author photo asset is missing")
    PHOTO.write_bytes(base64.b64decode(PHOTO_B64.read_text(encoding="ascii").strip()))
    return PHOTO

def compose_thumbnail(background_path, output_path, title, video=None, final_package=None):
    if not background_path or not Path(background_path).is_file():
        raise FileNotFoundError(f"AI-generated thumbnail artwork missing: {background_path}")
    # The AI artwork is the complete canvas; never restore the legacy fixed master frame.
    image = ImageOps.fit(Image.open(background_path).convert("RGB"), (1280, 720),
                         method=Image.Resampling.LANCZOS)
    portrait = Image.open(_photo_path()).convert("RGB")
    # Keep the complete original portrait and preserve its proportions; no face retouching or cropping.
    portrait.thumbnail((330, 610), Image.Resampling.LANCZOS)
    x = 1280 - portrait.width - 24
    y = (720 - portrait.height) // 2
    draw = ImageDraw.Draw(image)
    p = 7
    draw.rounded_rectangle((x-p, y-p, x+portrait.width+p, y+portrait.height+p),
                           radius=18, fill=(245, 205, 105), outline=(255, 239, 190), width=3)
    image.paste(portrait, (x, y))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    return {"file": str(output), "author_photo_included": True,
            "author_photo_source": "assets/author_photo.jpeg",
            "master_template": None, "programme_template": "ai_creative",
            "dimensions": "1280x720"}
