# Final Shiv Puran master thumbnail template

This is an isolated renderer for the exact master thumbnail supplied by the channel owner. It does **not** replace or modify `src/thumbnail_composer.py`, the existing live scheduler, the website, or YouTube metadata.

## Required input assets

1. Save the owner's exact master image as `assets/shiv_puran_master.png`.
2. Supply one chapter-specific central artwork image (PNG/JPG) to the renderer.

The master image is deliberately not synthesized or substituted. The renderer stops with a clear error if the exact master asset is missing. The master is opened read-only and is never overwritten.

## Run manually

```bash
python -m pip install Pillow
python src/shiv_puran_master_template.py \
  --background path/to/chapter_artwork.png \
  --chapter-text "रुद्र संहिता खंड 5, अध्याय 6" \
  --topic-title "विषय का सत्यापित संक्षिप्त शीर्षक" \
  --output output/shiv_puran_thumbnail.png
```

- `--chapter-text` is mandatory. No chapter number or title is guessed.
- `--topic-title` is optional and should only be supplied when verified.
- Output is PNG at 1280×720 (16:9).
- The central artwork window and existing English chapter subtitle area are the only edited regions. Header, portrait/name plaque, upper plaque, fixed “Shiv Puran” title and outer border are preserved from the master.
- Coordinates are measured from the owner's 1672×941 supplied master and scaled to 1280×720. Review the first preview before enabling unattended automation.

## Safety

This module is intentionally not wired into the hourly YouTube preparation/upload workflow yet. First add the exact master image at the path above and approve a rendered preview. No YouTube upload or metadata write is performed.
