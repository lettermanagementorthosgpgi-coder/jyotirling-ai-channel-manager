"""Calendar-driven, book-specific daily scripture chapter feeds.

The feed is deterministic by Asia/Kolkata date: hourly workflow retries never
advance a chapter more than once. Chapter titles remain sourced from the PDFs.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def _advance_book(start: dict, sections: list[dict], days_elapsed: int) -> dict:
    section_index = int(start.get("section_index", 0))
    chapter_number = int(start["chapter_number"]) + max(0, days_elapsed)
    while section_index < len(sections):
        section = sections[section_index]
        count = int(section["chapter_count"])
        if chapter_number <= count:
            return {
                "programme": start["programme"],
                "book": start["book"],
                "section_index": section_index,
                "section_name": section["name"],
                "chapter_number": chapter_number,
                "chapter_title": None,
                "source_of_truth": start.get("source_of_truth"),
                "status": "active",
                "title_lookup_required": True,
            }
        chapter_number -= count
        section_index += 1
    return {
        "programme": start["programme"], "book": start["book"],
        "status": "book_sequence_completed", "title_lookup_required": False,
        "note": "The configured contents sequence has ended; do not invent another chapter.",
    }


def build_daily_programme_feeds(config: dict, today: date | None = None) -> dict:
    """Return today's morning/evening chapter feeds without mutating config."""
    timezone_name = config.get("timezone", "Asia/Kolkata")
    today = today or datetime.now(ZoneInfo(timezone_name)).date()
    feeds = config.get("programme_feeds", {})
    start_date = date.fromisoformat(feeds["feed_date_local"])
    days_elapsed = max(0, (today - start_date).days)

    morning = dict(feeds["morning"])
    shiv_sections = feeds["morning"].get("book_sequence", [])
    morning_result = _advance_book(morning, shiv_sections, days_elapsed)

    evening = dict(feeds["evening"])
    gita_days = days_elapsed
    gita_chapter = int(evening["chapter_number"]) + gita_days
    gita_max = int(evening.get("total_chapters", 18))
    if gita_chapter <= gita_max:
        evening_result = {
            "programme": evening["programme"], "book": evening["book"],
            "chapter_number": gita_chapter,
            "chapter_title": evening.get("chapter_titles", {}).get(str(gita_chapter)),
            "source_of_truth": evening.get("source_of_truth"),
            "status": "active",
        }
    else:
        evening_result = {
            "programme": evening["programme"], "book": evening["book"],
            "status": "book_sequence_completed",
            "note": "Bhagavad Gita chapter sequence (18 chapters) completed.",
        }

    return {
        "feed_date_local": today.isoformat(),
        "days_elapsed_from_start": days_elapsed,
        "morning": morning_result,
        "evening": evening_result,
        "advance_policy": "One chapter per calendar day in Asia/Kolkata; hourly retries on the same date do not advance.",
    }
