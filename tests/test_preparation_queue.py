import unittest

from src.preparation_queue import build_new_upload_preparation_queue


class PreparationQueueTests(unittest.TestCase):
    def test_includes_every_upload_on_or_after_local_start_date(self):
        videos = [
            {"video_id": "before", "published_at": "2026-11-01T17:00:00Z"},
            {"video_id": "today", "published_at": "2026-11-02T01:00:00Z", "title": "Morning upload"},
            {"video_id": "later", "published_at": "2026-11-03T01:00:00Z", "title": "Next upload"},
        ]
        result = build_new_upload_preparation_queue(videos, "2026-11-02", "Asia/Kolkata")
        self.assertEqual(result["videos_in_queue"], 2)
        self.assertEqual([item["video_id"] for item in result["items"]], ["today", "later"])
        self.assertFalse(result["safety"]["youtube_metadata_changed"])
        self.assertEqual(result["items"][0]["implementation"]["status"], "awaiting_user_approval")

    def test_manual_date_range_is_inclusive(self):
        videos = [
            {"video_id": "before", "published_at": "2026-11-01T18:00:00Z"},
            {"video_id": "start", "published_at": "2026-11-02T00:00:00Z"},
            {"video_id": "end", "published_at": "2026-11-03T18:29:00Z"},
            {"video_id": "after", "published_at": "2026-11-03T18:31:00Z"}
        ]
        result = build_new_upload_preparation_queue(
            videos, "2026-11-02", "Asia/Kolkata", end_date="2026-11-03")
        self.assertEqual([item["video_id"] for item in result["items"]], ["start", "end"])
        self.assertEqual(result["end_date_local"], "2026-11-03")

    def test_invalid_or_missing_publish_dates_are_skipped(self):
        videos = [{"video_id": "missing"}, {"video_id": "bad", "published_at": "not-a-date"}]
        result = build_new_upload_preparation_queue(videos, "2026-11-02")
        self.assertEqual(result["videos_in_queue"], 0)


if __name__ == "__main__":
    unittest.main()
