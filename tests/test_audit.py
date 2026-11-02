"""Unit tests for paginated YouTube Analytics collection."""
import unittest

from src.audit import (
    _analytics_by_video, _daily_analytics_by_video,
    _unique_playlist_video_ids, _unique_video_details,
)


class FakeRequest:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


class FakeReports:
    def __init__(self, pages, fail_at=None):
        self.pages = pages
        self.fail_at = fail_at
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        page_number = len(self.calls)
        if self.fail_at == page_number:
            return FakeRequest(error=RuntimeError("simulated API failure"))
        return FakeRequest(self.pages[page_number - 1])


class FakeAnalytics:
    def __init__(self, reports):
        self._reports = reports

    def reports(self):
        return self

    def query(self, **kwargs):
        return self._reports.query(**kwargs)


class InventoryDeduplicationTests(unittest.TestCase):
    def test_repeated_playlist_video_is_reported_but_counted_once(self):
        items = [
            {"id": "p1", "snippet": {"title": "A", "position": 0},
             "contentDetails": {"videoId": "video-A"}},
            {"id": "p2", "snippet": {"title": "B", "position": 1},
             "contentDetails": {"videoId": "video-B"}},
            {"id": "p3", "snippet": {"title": "A", "position": 2},
             "contentDetails": {"videoId": "video-A"}},
        ]
        ids, duplicates = _unique_playlist_video_ids(items)
        self.assertEqual(ids, ["video-A", "video-B"])
        self.assertEqual(duplicates[0]["playlist_item_id"], "p3")

    def test_same_title_different_ids_are_distinct(self):
        ids, duplicates = _unique_playlist_video_ids([
            {"snippet": {"title": "Same"}, "contentDetails": {"videoId": "A"}},
            {"snippet": {"title": "Same"}, "contentDetails": {"videoId": "B"}},
        ])
        self.assertEqual(ids, ["A", "B"])
        self.assertEqual(duplicates, [])

    def test_missing_ids_are_ignored(self):
        ids, duplicates = _unique_playlist_video_ids([
            {"snippet": {"title": "No ID"}, "contentDetails": {}},
            {"contentDetails": {"videoId": "A"}},
        ])
        self.assertEqual(ids, ["A"])
        self.assertEqual(duplicates, [])

    def test_duplicate_video_resources_are_suppressed(self):
        unique, duplicates = _unique_video_details([
            {"id": "A"}, {"id": "B"}, {"id": "A"},
        ])
        self.assertEqual([v["id"] for v in unique], ["A", "B"])
        self.assertEqual(duplicates, ["A"])


class AnalyticsPaginationTests(unittest.TestCase):
    def test_per_video_metrics_include_impressions_and_ctr(self):
        headers = [{"name": "video"}, {"name": "views"},
                   {"name": "impressions"}, {"name": "impressionClickThroughRate"}]
        reports = FakeReports([{
            "columnHeaders": headers, "rows": [["video-A", 123, 4000, 0.035]]
        }])
        result = _analytics_by_video(FakeAnalytics(reports), "2026-10-01", "2026-11-01")
        self.assertTrue(result["available"])
        self.assertEqual(result["by_video"]["video-A"]["impressions"], 4000)
        self.assertEqual(result["by_video"]["video-A"]["impressionClickThroughRate"], 0.035)
        self.assertIn("impressions", reports.calls[0]["metrics"])

    def test_daily_metrics_are_grouped_by_video_and_date(self):
        headers = [{"name": "video"}, {"name": "day"}, {"name": "views"},
                   {"name": "impressions"}, {"name": "impressionClickThroughRate"}]
        reports = FakeReports([{
            "columnHeaders": headers,
            "rows": [["video-A", "2026-10-31", 50, 1000, 0.05],
                     ["video-A", "2026-11-01", 60, 1200, 0.05]],
        }])
        result = _daily_analytics_by_video(FakeAnalytics(reports), "2026-10-01", "2026-11-01")
        self.assertTrue(result["available"])
        self.assertEqual(result["daily_rows"], 2)
        self.assertEqual(result["by_video"]["video-A"][1]["date"], "2026-11-01")
        self.assertEqual(reports.calls[0]["dimensions"], "video,day")

    def test_pagination_fetches_all_rows(self):
        headers = [{"name": "video"}, {"name": "views"}]
        first = [[f"v{i}", i] for i in range(200)]
        reports = FakeReports([
            {"columnHeaders": headers, "rows": first},
            {"columnHeaders": headers, "rows": [["v200", 200]]},
        ])
        result = _analytics_by_video(FakeAnalytics(reports), "2026-10-01", "2026-11-01")
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(len(result["by_video"]), 201)
        self.assertEqual([c["startIndex"] for c in reports.calls], [1, 201])

    def test_failed_analytics_query_is_marked_unavailable(self):
        reports = FakeReports([{"columnHeaders": [{"name": "video"}], "rows": []}], fail_at=1)
        result = _daily_analytics_by_video(FakeAnalytics(reports), "2026-10-01", "2026-11-01")
        self.assertFalse(result["available"])
        self.assertEqual(result["by_video"], {})


if __name__ == "__main__":
    unittest.main()
