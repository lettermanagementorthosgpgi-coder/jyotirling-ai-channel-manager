from datetime import date

from src.programme_progression import build_daily_programme_feeds


def sample_config():
    return {
        "timezone": "Asia/Kolkata",
        "programme_feeds": {
            "feed_date_local": "2026-11-04",
            "morning": {
                "programme": "shiv_puran", "book": "शिव पुराण",
                "section_index": 0, "chapter_number": 5,
                "source_of_truth": "Soochi Shiv Puran ki.pdf",
                "book_sequence": [
                    {"name": "पंचम खंड", "chapter_count": 59},
                    {"name": "शतरुद्र संहिता", "chapter_count": 42},
                ],
            },
            "evening": {
                "programme": "bhagavad_gita", "book": "श्रीमद्भगवद्गीता",
                "chapter_number": 17, "total_chapters": 18,
                "chapter_titles": {"17": "श्रद्धात्रयविभागयोग", "18": "मोक्षसंन्यासयोग"},
                "source_of_truth": "bhagavad_gita_yatharoop.pdf",
            },
        },
    }


def test_feed_starts_with_separately_fed_chapters():
    feeds = build_daily_programme_feeds(sample_config(), date(2026, 11, 4))
    assert feeds["morning"]["section_name"] == "पंचम खंड"
    assert feeds["morning"]["chapter_number"] == 5
    assert feeds["evening"]["chapter_number"] == 17


def test_feed_advances_once_per_calendar_day_and_keeps_books_separate():
    feeds = build_daily_programme_feeds(sample_config(), date(2026, 11, 5))
    assert feeds["morning"]["chapter_number"] == 6
    assert feeds["evening"]["chapter_number"] == 18
    assert feeds["evening"]["chapter_title"] == "मोक्षसंन्यासयोग"


def test_shiv_puran_moves_to_next_section_using_contents_sequence():
    feeds = build_daily_programme_feeds(sample_config(), date(2026, 12, 29))
    assert feeds["morning"]["section_name"] == "शतरुद्र संहिता"
    assert feeds["morning"]["chapter_number"] == 1


def test_gita_stops_after_eighteen_chapters():
    feeds = build_daily_programme_feeds(sample_config(), date(2026, 11, 6))
    assert feeds["evening"]["status"] == "book_sequence_completed"
