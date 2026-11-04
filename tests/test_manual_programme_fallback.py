import unittest

from src.manual_programme_fallback import build_manual_programme_queue


class ManualProgrammeFallbackTests(unittest.TestCase):
    def test_builds_separate_morning_and_evening_book_items(self):
        feeds = {
            "feed_date_local": "2026-11-05",
            "morning": {
                "programme": "shiv_puran",
                "book": "शिव पुराण",
                "section_name": "पंचम खंड",
                "chapter_number": 6,
                "status": "active",
                "chapter_title": None,
            },
            "evening": {
                "programme": "bhagavad_gita",
                "book": "श्रीमद्भगवद्गीता",
                "chapter_number": 18,
                "chapter_title": "मोक्षसंन्यासयोग",
                "status": "active",
            },
        }
        queue = build_manual_programme_queue(feeds)
        self.assertEqual(queue["videos_in_queue"], 2)
        morning, evening = queue["items"]
        self.assertEqual(morning["programme"], "shiv_puran")
        self.assertEqual(morning["khanda_name"], "पंचम खंड")
        self.assertEqual(morning["chapter_number"], 6)
        self.assertTrue(morning["manual_book_mode"])
        self.assertEqual(evening["programme"], "bhagavad_gita")
        self.assertEqual(evening["chapter_number"], 18)
        self.assertEqual(evening["chapter_title"], "मोक्षसंन्यासयोग")
        self.assertNotEqual(morning["video_id"], evening["video_id"])

    def test_completed_programme_is_not_added(self):
        feeds = {
            "feed_date_local": "2026-11-06",
            "morning": {"programme": "shiv_puran", "status": "active", "chapter_number": 7},
            "evening": {"programme": "bhagavad_gita", "status": "book_sequence_completed"},
        }
        queue = build_manual_programme_queue(feeds)
        self.assertEqual(queue["videos_in_queue"], 1)
        self.assertEqual(queue["items"][0]["programme"], "shiv_puran")

    def test_empty_feeds_do_not_create_guessed_items(self):
        queue = build_manual_programme_queue({"feed_date_local": "2026-11-06"})
        self.assertEqual(queue["videos_in_queue"], 0)
        self.assertFalse(queue["safety"]["uploads_or_publications_made"])


if __name__ == "__main__":
    unittest.main()
