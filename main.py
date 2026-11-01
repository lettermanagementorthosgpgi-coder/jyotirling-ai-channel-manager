"""Jyotirling AI Channel Manager — read-only Phase 1 audit."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.youtube_client import build_youtube_services
from src.audit import run_channel_audit

ROOT = Path(__file__).resolve().parent


def main() -> None:
    config_path = ROOT / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    youtube, analytics = build_youtube_services(ROOT)
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    result = run_channel_audit(
        youtube=youtube,
        analytics=analytics,
        max_videos=int(config["audit"]["max_videos_per_run"]),
        include_unlisted=bool(config["audit"]["include_unlisted"]),
    )
    out = report_dir / f"channel_audit_{stamp}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Audit complete. Report: {out}")
    print(f"Videos inventoried: {len(result['videos'])}")
    print("READ-ONLY MODE: no channel metadata or videos were changed.")


if __name__ == "__main__":
    main()
