"""Build an approval-only preparation queue from the daily scripture book feeds."""
from __future__ import annotations


def build_manual_programme_queue(daily_feeds: dict) -> dict:
    """Create synthetic programme items without requiring YouTube inventory/API data."""
    items = []
    feed_date = daily_feeds.get("feed_date_local")
    for slot in ("morning", "evening"):
        feed = daily_feeds.get(slot) or {}
        if feed.get("status") != "active":
            continue
        programme = feed.get("programme")
        chapter = feed.get("chapter_number")
        if not programme or not chapter:
            continue
        book = feed.get("book") or ("शिव पुराण" if programme == "shiv_puran" else "श्रीमद्भगवद्गीता")
        section = feed.get("section_name") or feed.get("khanda_name")
        chapter_title = feed.get("chapter_title")
        parts = [book]
        if section:
            parts.append(section)
        parts.append(f"अध्याय {chapter}")
        if chapter_title:
            parts.append(chapter_title)
        source_title = " — ".join(parts)
        source_description = (
            "यह सामग्री YouTube API डेटा उपलब्ध न होने पर पुस्तक-आधारित Manual Mode में तैयार की जा रही है। "
            f"कार्यक्रम: {slot}; पुस्तक: {book}; "
            f"खंड/संहिता: {section or 'लागू नहीं'}; अध्याय: {chapter}; "
            f"पुस्तक में दिया अध्याय शीर्षक: {chapter_title or 'मूल PDF से सत्यापित करना अनिवार्य'}। "
            "संबंधित निजी मूल PDF को पढ़कर ही अध्याय का विषय, शीर्षक, सार, SEO विवरण, टैग, हैशटैग "
            "और Thumbnail brief तैयार करें। अध्याय शीर्षक या श्लोक अनुमान से न लिखें।"
        )
        items.append({
            "video_id": f"manual-{programme}-{feed_date}-{chapter}",
            "url": None,
            "published_at": None,
            "source_title": source_title,
            "source_description": source_description,
            "source_tags": [],
            "title": source_title,
            "description": source_description,
            "tags": [],
            "programme": programme,
            "programme_slot": slot,
            "programme_feed": feed,
            "chapter_number": chapter,
            "chapter_title": chapter_title,
            "khanda_name": section,
            "transcript": {"status": "not_applicable_manual_book_mode"},
            "package": {
                "status": "pending_book_based_ai_preparation",
                "required_outputs": [
                    "YouTube title options",
                    "complete Hindi-first description",
                    "tags and hashtags",
                    "chapter-grounded thumbnail concept and image",
                    "chapter title/topic verified from the original PDF"
                ]
            },
            "implementation": {
                "status": "awaiting_user_approval",
                "youtube_changes_allowed": False
            }
        })
    return {
        "start_date_local": feed_date,
        "end_date_local": feed_date,
        "timezone": "Asia/Kolkata",
        "scope": "daily_book_based_manual_fallback",
        "videos_in_queue": len(items),
        "items": items,
        "safety": {
            "youtube_api_data_required": False,
            "youtube_metadata_changed": False,
            "thumbnail_uploaded": False,
            "uploads_or_publications_made": False
        }
    }
