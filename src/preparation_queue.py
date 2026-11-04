"""Build a durable, read-only queue of recent and explicitly selected videos."""
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo
import re


def _classify_programme(video):
    text = " ".join(str(video.get(key) or "") for key in
                    ("title", "description", "source_title", "source_description")).lower()
    if any(term in text for term in ("bhagavad gita", "bhagvadgita", "bhagavadgita", "गीता", "गीताजी", "gita")):
        return "bhagavad_gita"
    if any(term in text for term in ("shiv puran", "shiv mahapuran", "शिवपुराण", "शिव पुराण",
                                     "त्रिपुर", "tripur", "रुद्र", "rudra", "महादेव", "शंकर")):
        return "shiv_puran"
    return None


def _chapter_number(text):
    match = re.search(r"(?:अध्याय|adhyay|chapter)\s*[-:#]?\s*([0-9]{1,2})", text, re.I)
    return int(match.group(1)) if match else None


def build_new_upload_preparation_queue(videos, start_date, timezone="Asia/Kolkata",
                                       include_video_ids=None, end_date=None,
                                       programme_feeds=None):
    """Queue public videos on/after start_date plus explicitly selected video IDs.

    This prepares review records only. It never edits YouTube metadata, downloads
    media, or uploads/publishes anything.
    """
    tz = ZoneInfo(timezone)
    cutoff = date.fromisoformat(start_date)
    end_cutoff = date.fromisoformat(end_date) if end_date else None
    if end_cutoff and end_cutoff < cutoff:
        raise ValueError("end_date must be on or after start_date")
    explicit_ids = set(include_video_ids or [])
    queue = []
    for video in videos:
        video_id = video.get("video_id")
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
        explicitly_selected = video_id in explicit_ids
        if published_local.date() < cutoff and not explicitly_selected:
            continue
        if end_cutoff and published_local.date() > end_cutoff and not explicitly_selected:
            continue

        programme = _classify_programme(video)
        slot = "evening" if programme == "bhagavad_gita" else "morning" if programme == "shiv_puran" else None
        feed = ((programme_feeds or {}).get(slot) or {}) if slot else {}
        source_text = " ".join(str(video.get(key) or "") for key in ("title", "description"))
        chapter_number = _chapter_number(source_text) or feed.get("chapter_number")
        chapter_title = feed.get("chapter_title") if chapter_number == feed.get("chapter_number") else None
        section_name = feed.get("section_name") or feed.get("khanda_name")

        queue.append({
            "video_id": video_id,
            "url": video.get("url"),
            "published_at": published_at,
            "published_local": published_local.isoformat(),
            "included_by_explicit_id": explicitly_selected,
            "source_title": video.get("title"),
            "source_description": video.get("description"),
            "source_tags": video.get("tags", []),
            "programme": programme,
            "programme_slot": slot,
            "programme_feed": feed or None,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "khanda_name": section_name,
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
        "end_date_local": end_date,
        "date_scope": "inclusive_local_calendar_dates",
        "timezone": timezone,
        "explicitly_included_video_ids": sorted(explicit_ids),
        "videos_in_queue": len(queue),
        "items": queue,
        "safety": {
            "read_only": True,
            "youtube_metadata_changed": False,
            "thumbnail_changed": False,
            "uploads_or_publications_made": False
        }
    }
