"""Unit tests for paginated YouTube Analytics collection."""
import unittest

from src.audit import _analytics_by_video, _unique_playlist_video_ids


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
        self.start_indexes = []

    def query(self, **kwargs):
        start_index = kwargs["startIndex"]
        self.start_indexes.append(start_index)
        page_number = len(self.start_indexes)
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



class PlaylistVideoDeduplicationTests(unittest.TestCase):
    def test_repeated_video_id_is_reported_but_counted_once(self):
        items = [
            {
                "id": "playlist-item-1",
                "snippet": {"title": "Same title", "position": 0},
                "contentDetails": {"videoId": "video-A"},
            },
            {
                "id": "playlist-item-2",
                "snippet": {"title": "Different title", "position": 1},
                "contentDetails": {"videoId": "video-B"},
            },
            {
                "id": "playlist-item-3",
                "snippet": {"title": "Same title", "position": 2},
                "contentDetails": {"videoId": "video-A"},
            },
        ]

        unique_ids, duplicates = _unique_playlist_video_ids(items)

        self.assertEqual(unique_ids, ["video-A", "video-B"])
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["video_id"], "video-A")
        self.assertEqual(duplicates[0]["playlist_item_id"], "playlist-item-3")
        self.assertEqual(duplicates[0]["position"], 2)

    def test_same_title_with_different_video_ids_are_kept(self):
        items = [
            {
                "snippet": {"title": "CHARON DHAM YATRA"},
                "contentDetails": {"videoId": "video-A"},
            },
            {
                "snippet": {"title": "CHARON DHAM YATRA"},
                "contentDetails": {"videoId": "video-B"},
            },
        ]

        unique_ids, duplicates = _unique_playlist_video_ids(items)

        self.assertEqual(unique_ids, ["video-A", "video-B"])
        self.assertEqual(duplicates, [])

    def test_missing_video_ids_are_ignored(self):
        unique_ids, duplicates = _unique_playlist_video_ids([
            {"snippet": {"title": "No ID"}, "contentDetails": {}},
            {"contentDetails": {"videoId": "video-A"}},
        ])

        self.assertEqual(unique_ids, ["video-A"])
        self.assertEqual(duplicates, [])


class AnalyticsPaginationTests(unittest.TestCase):
    def setUp(self):
        self.headers = [
            {"name": "video"},
            {"name": "views"},
        ]

    def test_fetches_more_than_one_page(self):
        first_rows = [[f"video-{i}", i] for i in range(200)]
        second_rows = [["video-200", 200]]
        reports = FakeReports([
            {"columnHeaders": self.headers, "rows": first_rows},
            {"columnHeaders": self.headers, "rows": second_rows},
        ])

        result = _analytics_by_video(FakeAnalytics(reports), "2026-08-01", "2026-11-01")

        self.assertTrue(result["available"])
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(result["videos_with_analytics"], 201)
        self.assertEqual(reports.start_indexes, [1, 201])
        self.assertEqual(result["by_video"]["video-200"]["views"], 200)

    def test_exact_page_size_checks_for_another_page(self):
        rows = [[f"video-{i}", i] for i in range(200)]
        reports = FakeReports([
            {"columnHeaders": self.headers, "rows": rows},
            {"columnHeaders": self.headers, "rows": []},
        ])

        result = _analytics_by_video(FakeAnalytics(reports), "2026-08-01", "2026-11-01")

        self.assertTrue(result["available"])
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(result["videos_with_analytics"], 200)
        self.assertEqual(reports.start_indexes, [1, 201])

    def test_later_page_failure_discards_partial_data(self):
        rows = [[f"video-{i}", i] for i in range(200)]
        reports = FakeReports(
            [{"columnHeaders": self.headers, "rows": rows}],
            fail_at=2,
        )

        result = _analytics_by_video(FakeAnalytics(reports), "2026-08-01", "2026-11-01")

        self.assertFalse(result["available"])
        self.assertEqual(result["pages_fetched"], 1)
        self.assertEqual(result["by_video"], {})
        self.assertEqual(result["videos_with_analytics"], 0)
        self.assertIn("simulated API failure", result["reason"])


if __name__ == "__main__":
    unittest.main()
