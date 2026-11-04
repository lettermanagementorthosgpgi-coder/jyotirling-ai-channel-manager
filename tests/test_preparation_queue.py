import unittest
from src.preparation_queue import build_new_upload_preparation_queue

class PreparationQueueTests(unittest.TestCase):
    def test_today_scope_excludes_yesterday_gita_video(self):
        videos = [
            {"video_id": "today-shiv", "published_at": "2026-11-04T02:40:00Z", "title": "Tripur sahit unke swamiyon ke vadh ki Prarthna"},
            {"video_id": "yesterday-gita", "published_at": "2026-11-03T15:35:00Z", "title": "BhagvadGita Adhyay 16"},
        ]
        feeds = {"morning": {"programme": "shiv_puran", "chapter_number": 20, "section_name": "रुद्र संहिता"}, "evening": {"programme": "bhagavad_gita", "chapter_number": 17}}
        result = build_new_upload_preparation_queue(videos, "2026-11-04", end_date="2026-11-04", timezone="Asia/Kolkata", programme_feeds=feeds)
        self.assertEqual([x["video_id"] for x in result["items"]], ["today-shiv"])
        self.assertEqual(result["items"][0]["programme"], "shiv_puran")
        self.assertEqual(result["items"][0]["chapter_number"], 20)

    def test_explicit_review_video_can_be_included_outside_date(self):
        videos = [{"video_id": "review", "published_at": "2026-11-03T10:00:00Z", "title": "Bhagavad Gita"}]
        result = build_new_upload_preparation_queue(videos, "2026-11-04", end_date="2026-11-04", include_video_ids=["review"], timezone="Asia/Kolkata")
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(result["items"][0]["included_by_explicit_id"])

if __name__ == "__main__":
    unittest.main()
