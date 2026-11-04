"""Tests for incremental YouTube inventory caching."""
import tempfile
import unittest
from pathlib import Path

from src.audit import _incremental_inventory, _read_inventory_cache, _write_inventory_cache


class Request:
    def __init__(self, payload):
        self.payload = payload
    def execute(self):
        return self.payload


class PlaylistItems:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
    def list(self, **kwargs):
        self.calls.append(kwargs)
        token = kwargs.get("pageToken")
        index = 0 if token is None else int(token)
        payload = dict(self.pages[index])
        if payload.get("nextPageToken") is not None:
            payload["nextPageToken"] = str(payload["nextPageToken"])
        return Request(payload)


class Videos:
    def __init__(self):
        self.calls = []
    def list(self, **kwargs):
        self.calls.append(kwargs)
        ids = kwargs["id"].split(",")
        return Request({"items": [{"id": vid, "status": {"privacyStatus": "public"}}
                                  for vid in ids]})


class YouTube:
    def __init__(self, pages):
        self.playlists = PlaylistItems(pages)
        self.video_service = Videos()
    def playlistItems(self):
        return self.playlists
    def videos(self):
        return self.video_service


class InventoryCacheTests(unittest.TestCase):
    def test_incremental_scan_stops_at_first_known_upload(self):
        pages = [{
            "items": [
                {"contentDetails": {"videoId": "new-a"}},
                {"contentDetails": {"videoId": "new-b"}},
                {"contentDetails": {"videoId": "known"}},
                {"contentDetails": {"videoId": "older"}}
            ],
            "nextPageToken": None
        }]
        yt = YouTube(pages)
        cached = {"known": {"id": "known", "status": {"privacyStatus": "public"}}}
        updated, scanned, duplicates, new_count = _incremental_inventory(
            yt, "uploads", cached, 5000)
        self.assertEqual(scanned, 3)  # Two new entries plus the first cached entry examined.
        self.assertEqual(new_count, 2)
        self.assertEqual(set(updated), {"known", "new-a", "new-b"})
        self.assertEqual(len(yt.video_service.calls), 1)
        self.assertEqual(yt.video_service.calls[0]["id"], "new-a,new-b")

    def test_cache_round_trip_and_channel_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "inventory.json"
            data = {"video-1": {"id": "video-1"}}
            _write_inventory_cache(path, "channel-a", "uploads-a", data)
            self.assertEqual(_read_inventory_cache(path, "channel-a", "uploads-a"), data)
            self.assertEqual(_read_inventory_cache(path, "channel-b", "uploads-a"), {})


if __name__ == "__main__":
    unittest.main()
