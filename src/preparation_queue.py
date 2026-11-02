"""Build a durable, read-only queue of videos published from the configured start date."""
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo


def build_new_upload_preparation_queue(videos, start_date, timezone="Asia/Kolkata"):
    """Return every public video published on/after start_date in local channel time.

    This deliberately prepares review records only. It never edits YouTube metadata,
    downloads media, or uploads/publishes anything.
    """
    tz = ZoneInfo(timezone)
    cutoff = date.fromisoformat(start_date)
    queue = []
    for video in videos:
        published_at = video.get("published_at")
        if not published_at:
            continue
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=tz)
            published_local = published.astimezone(tz)
        except (TypeError, ValueError):
            continue
        if published_local.date() < cutoff:
            continue

        queue.append({
            "video_id": video.get("video_id"),
            "url": video.get("url"),
            "published_at": published_at,
            "published_local": published_local.isoformat(),
            "source_title": video.get("title"),
            "source_description": video.get("description"),
            "source_tags": video.get("tags", []),
            "duration": video.get("duration"),
            "lifetime_statistics": video.get("lifetime_statistics", {}),
            "last_90_days_analytics": video.get("last_90_days_analytics"),
            "daily_analytics": video.get("daily_analytics", []),
            "thumbnail_urls": video.get("thumbnail_urls", {}),
            "transcript": {
                "status": "pending_retrieval",
                "note": "Transcript must be retrieved from an authorized/available source and checked against the video."
            },
            "package": {
                "status": "pending_ai_preparation",
                "required_outputs": [
                    "YouTube-compliant title options",
                    "SEO description",
                    "relevant tags and hashtags",
                    "thumbnail concept and thumbnail image",
                    "transcript-grounded topic summary and chapters where applicable"
                ]
            },
            "review_rotation": {
                "status": "pending",
                "sequence": ["AI-1 data analysis", "AI-2 YouTube SEO", "AI-3 independent review"],
                "current_assignee": "AI-1",
                "handoff_rule": "If a reviewer cannot complete an assigned task, hand it to the next reviewer; continue rotating until complete or a concrete blocker is recorded.",
                "completed_reviews": [],
                "blockers": []
            },
            "implementation": {
                "status": "awaiting_user_approval",
                "youtube_changes_allowed": False
            }
        })

    queue.sort(key=lambda item: item["published_local"])
    return {
        "start_date_local": start_date,
        "timezone": timezone,
        "videos_in_queue": len(queue),
        "items": queue,
        "safety": {
            "read_only": True,
            "youtube_metadata_changed": False,
            "thumbnail_changed": False,
            "uploads_or_publications_made": False
        }
    }
