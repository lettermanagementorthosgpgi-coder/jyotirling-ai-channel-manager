"""Read-only channel audit entry point."""
import json
from datetime import datetime
from pathlib import Path
from src.youtube_client import build_youtube_services
from src.audit import run_channel_audit

ROOT = Path(__file__).resolve().parent


def main():
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    youtube, analytics, reporting, session = build_youtube_services(ROOT)
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    result = run_channel_audit(youtube, analytics, reporting=reporting,
        reporting_session=session,
        max_videos=int(config["audit"]["max_videos_per_run"]),
        include_unlisted=bool(config["audit"]["include_unlisted"]),
        daily_analytics_days=int(config["audit"].get("daily_analytics_days",30)))
    out = report_dir / f"channel_audit_{stamp}.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Audit complete. Report: {out}")
    print(f"Videos inventoried: {len(result['videos'])}")
    print("READ-ONLY MODE: no channel metadata or videos were changed.")


if __name__ == "__main__":
    main()
