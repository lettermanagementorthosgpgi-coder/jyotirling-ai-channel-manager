import tempfile
import unittest
from pathlib import Path

from src.seo_performance import (
    build_performance_delta,
    get_seo_baseline,
    record_successful_seo_baseline,
)


class SEOPerformanceTests(unittest.TestCase):
    def test_verified_baseline_and_post_seo_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            record_successful_seo_baseline(
                db, "video-a",
                {"viewCount": "1000", "likeCount": "50", "commentCount": "7"},
                seo_changed_at="2026-08-06T10:00:00+05:30",
                old_metadata={"title": "Old"},
                new_metadata={"title": "Improved"}
            )
            baseline = get_seo_baseline(db, "video-a")
            self.assertEqual(baseline["baseline_views"], 1000)
            result = build_performance_delta(
                db, "video-a",
                {"viewCount": "1250", "likeCount": "65", "commentCount": "9"},
                subscribers_gained=12
            )
            self.assertEqual(result["observed_change"]["views"], 250)
            self.assertEqual(result["observed_change"]["likes"], 15)
            self.assertEqual(result["observed_change"]["comments"], 2)
            self.assertEqual(result["observed_change"]["subscribers_gained_since_seo"], 12)
            self.assertIn("not proof", result["interpretation"])

    def test_no_baseline_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_performance_delta(Path(tmp) / "state.sqlite", "missing",
                                             {"viewCount": "9"})
            self.assertFalse(result["baseline_available"])


if __name__ == "__main__":
    unittest.main()
