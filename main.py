"""Approval-first channel audit and AI preparation entry point."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from src.youtube_client import build_youtube_services, run_write_permission_smoke_test, upload_one_thumbnail
from src.ai_providers import available_providers, generate_thumbnail_background
from src.thumbnail_composer import compose_thumbnail
from src.audit import run_channel_audit
from src.preparation_queue import build_new_upload_preparation_queue
from src.transcript_retrieval import retrieve_queue_transcripts
from src.ai_pipeline import run_ai_preparation
from src.seo_performance import get_seo_baseline, build_performance_delta, query_subscribers_gained_since
from src.programme_progression import build_daily_programme_feeds
from src.manual_programme_fallback import build_manual_programme_queue

ROOT = Path(__file__).resolve().parent


def main():
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    daily_programme_feeds = build_daily_programme_feeds(config)
    print("BOOK-BASED DAILY PROGRAMME FEEDS: " + json.dumps(daily_programme_feeds, ensure_ascii=False))
    manual_from = os.getenv("MANUAL_FROM_DATE", "").strip()
    manual_to = os.getenv("MANUAL_TO_DATE", "").strip()
    manual_range = bool(manual_from or manual_to)
    if manual_range and (not manual_from or not manual_to):
        raise ValueError("Manual date range requires both MANUAL_FROM_DATE and MANUAL_TO_DATE (YYYY-MM-DD).")
    try:
        youtube, analytics, reporting, session = build_youtube_services(ROOT)
        result = run_channel_audit(youtube, analytics, reporting=reporting,
            reporting_session=session,
            max_videos=int(config["audit"]["max_videos_per_run"]),
            include_unlisted=bool(config["audit"]["include_unlisted"]),
            daily_analytics_days=int(config["audit"].get("daily_analytics_days",30)),
            inventory_cache_path=ROOT / ".state" / "channel_inventory.json",
            manual_from_date=manual_from or None,
            manual_to_date=manual_to or None,
            timezone=config.get("timezone", "Asia/Kolkata"))
    except Exception as exc:
        # If YouTube inventory/data cannot be obtained, prepare today's scripture
        # programmes directly from the provisioned primary books instead.
        error_text = str(exc)
        manual_queue = build_manual_programme_queue(daily_programme_feeds)
        manual_result = run_ai_preparation(
            manual_queue,
            ROOT / ".state" / "preparation.sqlite",
            ROOT / "transcripts",
            ROOT / "thumbnails"
        )
        manual_report = {
            "report_type": "book_based_manual_fallback",
            "status": "manual_mode_attempted" if manual_result.get("items") else "manual_mode_no_active_feeds",
            "youtube_data_status": "unavailable",
            "youtube_error": error_text[:1500],
            "checked_at_local": datetime.now(ZoneInfo(config.get("timezone", "Asia/Kolkata"))).isoformat(),
            "daily_programme_feeds": daily_programme_feeds,
            "manual_book_queue": {
                "scope": manual_queue.get("scope"),
                "items_count": manual_queue.get("videos_in_queue"),
                "items": manual_result.get("items", [])
            },
            "ai_preparation_summary": {
                "providers_configured": manual_result.get("providers_configured", []),
                "items_processed_or_pending": manual_result.get("videos_processed_or_pending", 0),
                "note": manual_result.get("note")
            },
            "safety": {
                "book_based_source_required": True,
                "youtube_metadata_changed": False,
                "thumbnail_uploaded": False,
                "uploads_or_publications_made": False
            },
            "retry_policy": {
                "youtube_api_retry_enabled": True,
                "note": "The existing scheduled workflow will retry YouTube data retrieval. Manual book preparation is independent and does not advance the chapter more than once per local calendar date."
            }
        }
        out = report_dir / f"channel_audit_{stamp}_manual_fallback.json"
        out.write_text(json.dumps(manual_report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("YOUTUBE DATA UNAVAILABLE: switched to book-based MANUAL MODE.")
        print(f"Manual fallback report: {out}")
        print("No YouTube metadata, thumbnail upload, or publication was performed.")
        return

    # Explicit opt-in only: generate and upload a thumbnail to the single approved Monday bhajan video.
    if os.getenv("APPLY_MONDAY_BHAJAN_THUMBNAIL", "false").strip().lower() == "true":
        target_video_id = "5uh8YV4UHLI"
        target = next((v for v in result["videos"] if v.get("video_id") == target_video_id), None)
        if not target:
            raise RuntimeError(f"Safety stop: approved target video {target_video_id} was not found in the public channel inventory.")
        source_title = str(target.get("title") or "")
        source_description = str(target.get("description") or "")
        if not any(word in (source_title + " " + source_description).lower()
                   for word in ("bhajan", "bhajans", "भजन", "सोमवार", "somvar", "somvaar", "monday")):
            raise RuntimeError("Safety stop: target video metadata does not identify it as a Monday/Shiva bhajan.")
        providers = available_providers()
        image_order = (["cloudflare"] if "cloudflare" in providers else []) + [p for p in providers if p != "cloudflare"]
        if not image_order:
            raise RuntimeError("No configured image-generation provider is available.")
        prompt = (
            "Create only cinematic devotional background artwork for a 16:9 YouTube thumbnail for a Monday Shiva bhajan. "
            "Show a serene, majestic Lord Shiva devotional scene with luminous Himalayan/Kailash atmosphere, tasteful "
            "trishul and subtle sacred light, visually rich but uncluttered. Respectful traditional Hindu iconography. "
            "No words, no letters, no numbers, no logos, no watermarks, no banners, no captions, and no human portrait. "
            "Keep clear central space for Hindi typography and reserve the left side for an existing author photo that "
            "will be composited separately. Video title: " + source_title + ". Description: " + source_description[:1200]
        )
        image_path = ROOT / "thumbnails" / f"{target_video_id}_background.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_errors = []
        generated = False
        for provider in image_order:
            try:
                image_bytes, image_model = generate_thumbnail_background(provider, prompt)
                if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Image provider did not return PNG bytes")
                image_path.write_bytes(image_bytes)
                print(f"MONDAY BHAJAN BACKGROUND GENERATED: {provider} / {image_model}")
                generated = True
                break
            except Exception as exc:
                image_errors.append(f"{provider}: {type(exc).__name__}: {exc}"[:500])
        if not generated:
            raise RuntimeError("Thumbnail background generation failed: " + " | ".join(image_errors))
        final_path = ROOT / "thumbnails" / f"{target_video_id}_thumbnail.png"
        composition = compose_thumbnail(image_path, final_path, source_title, video=target)
        if composition.get("programme_template") != "bhajan":
            raise RuntimeError("Safety stop: target did not resolve to the dedicated Shiva bhajan template.")
        upload_result = upload_one_thumbnail(youtube, target_video_id, final_path)
        result["single_video_thumbnail_upload"] = {
            "status": "uploaded",
            "video_id": target_video_id,
            "video_url": f"https://www.youtube.com/watch?v={target_video_id}",
            "title": source_title,
            "composition": composition,
            "upload": upload_result,
            "note": "Only this exact video ID was passed to thumbnails.set; no title, description, tags, or other videos were changed."
        }
        print("MONDAY BHAJAN THUMBNAIL UPLOAD: SUCCESS " + target_video_id)

    # Explicit opt-in only: update one public video's snippet with the exact same values,
    # then read it back to verify that YouTube accepted the write request.
    if os.getenv("YT_WRITE_TEST", "false").strip().lower() == "true":
        candidate = next((v for v in result["videos"]
                          if v.get("privacy_status") == "public" and v.get("video_id")), None)
        if not candidate:
            raise RuntimeError("Write test requested, but no public video was found.")
        result["write_permission_test"] = run_write_permission_smoke_test(
            youtube, candidate["video_id"])
        print("YOUTUBE WRITE PERMISSION TEST: " +
              result["write_permission_test"]["status"])
    else:
        result["write_permission_test"] = {
            "status": "not_requested",
            "note": "No YouTube write request was made. Enable the workflow's write_test input for the one-video no-op test."
        }

    result["daily_programme_feeds"] = daily_programme_feeds
    prep = config.get("new_upload_preparation", {})
    today_local = datetime.now(ZoneInfo(config.get("timezone", "Asia/Kolkata"))).date()
    from datetime import timedelta
    default_start = (today_local - timedelta(days=90)).isoformat()
    queue = build_new_upload_preparation_queue(
        result["videos"],
        start_date=manual_from or default_start,
        end_date=manual_to or None,
        timezone=config.get("timezone", "Asia/Kolkata"),
        include_video_ids=[] if manual_range else prep.get("include_video_ids", []))
    performance_db = ROOT / ".state" / "preparation.sqlite"
    performance_end = today_local.isoformat()
    for item in queue.get("items", []):
        baseline = get_seo_baseline(performance_db, item.get("video_id"))
        if baseline:
            changed_date = datetime.fromisoformat(
                baseline["seo_changed_at"].replace("Z", "+00:00")
            ).astimezone(ZoneInfo(config.get("timezone", "Asia/Kolkata"))).date().isoformat()
            subscriber_result = query_subscribers_gained_since(
                analytics, item["video_id"], changed_date, performance_end)
            item["seo_performance"] = build_performance_delta(
                performance_db, item["video_id"], item.get("lifetime_statistics", {}),
                subscribers_gained=subscriber_result.get("subscribers_gained"),
                analytics_available=subscriber_result.get("available", False))
            item["seo_performance"]["subscriber_analytics_reason"] = subscriber_result.get("reason")
        else:
            item["seo_performance"] = {
                "baseline_available": False,
                "note": "Verified SEO-change baseline not yet recorded for this video. Future confirmed SEO updates will establish the starting point."
            }

    transcript_result = retrieve_queue_transcripts(youtube, queue.get("items", []), ROOT / "transcripts")
    for item in queue.get("items", []):
        item["transcript_retrieval"] = transcript_result["results"].get(item.get("video_id"), {})
    ai_result = run_ai_preparation(queue, ROOT / ".state" / "preparation.sqlite",
                                   ROOT / "transcripts",
                                   force_reprocess_video_ids=prep.get("force_reprocess_video_ids", []))
    result["new_upload_preparation"] = {
        "start_date_local": queue["start_date_local"],
        "end_date_local": queue.get("end_date_local"),
        "scope": "manual_inclusive_date_range" if manual_range else "new_uploads_and_selected_reviews",
        "timezone": queue["timezone"],
        "explicitly_included_video_ids": queue["explicitly_included_video_ids"],
        "videos_in_queue": queue["videos_in_queue"],
        "items": ai_result["items"],
        "providers_configured": ai_result["providers_configured"],
        "transcript_retrieval": {"videos_checked": transcript_result["videos_checked"], "transcripts_available": transcript_result["transcripts_available"]},
        "note": ai_result["note"]
    }
    result["ai_preparation_summary"] = {
        "providers_configured": ai_result["providers_configured"],
        "videos_processed_or_pending": ai_result["videos_processed_or_pending"]
    }

    out = report_dir / f"channel_audit_{stamp}.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Audit complete. Report: {out}")
    print(f"Videos inventoried: {len(result['videos'])}")
    print(f"New-upload queue: {queue['videos_in_queue']} videos since {queue['start_date_local']}")
    print(f"AI providers configured: {', '.join(ai_result['providers_configured']) or 'none'}")
    print("AI preparation itself remains review-only; uploads and publication are never performed.")


if __name__ == "__main__":
    main()
