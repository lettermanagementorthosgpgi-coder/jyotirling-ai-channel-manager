import sys
import tempfile
import json
from datetime import datetime, timedelta, timezone
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.transcript_retrieval import _write_transcript, retrieve_video_transcript
from src.ai_providers import _extract_gemini_image


class TranscriptRetrievalTests(unittest.TestCase):
    def test_transcript_uses_real_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            result = _write_transcript(path, "पहली पंक्ति\nदूसरी पंक्ति")
            self.assertEqual(result["status"], "available")
            self.assertEqual(path.read_text(encoding="utf-8"), "पहली पंक्ति\nदूसरी पंक्ति\n")
            self.assertNotIn("\\n", path.read_text(encoding="utf-8"))

    def test_public_transcript_fallback_is_saved(self):
        snippet = types.SimpleNamespace(text="हरि ॐ")
        fetched = types.SimpleNamespace(snippets=[snippet])
        api_instance = types.SimpleNamespace(fetch=lambda *args, **kwargs: fetched)
        module = types.ModuleType("youtube_transcript_api")
        module.YouTubeTranscriptApi = lambda: api_instance
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {
            "youtube_transcript_api": module
        }):
            result = retrieve_video_transcript(None, "video-1", tmp)
            self.assertEqual(result["status"], "available")
            self.assertEqual(Path(result["file"]).read_text(encoding="utf-8"), "हरि ॐ\n")
            self.assertEqual(result["source"], "youtube_transcript_api_public_fallback")

    def test_official_caption_api_is_throttled_when_recently_checked(self):
        class Blocked:
            def fetch(self, *args, **kwargs):
                raise type("TranscriptsDisabled", (Exception,), {})("disabled")
        module = types.ModuleType("youtube_transcript_api")
        module.YouTubeTranscriptApi = lambda: Blocked()
        class YouTube:
            def captions(self):
                raise AssertionError("Official captions API should be throttled")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {
            "youtube_transcript_api": module
        }):
            checked = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            Path(tmp, "video-2.json").write_text(json.dumps({
                "status": "unavailable",
                "official_api_last_checked_at": checked
            }), encoding="utf-8")
            result = retrieve_video_transcript(YouTube(), "video-2", tmp)
            self.assertEqual(result["status"], "unavailable")
            self.assertTrue(any(
                item.get("status") == "deferred_to_reduce_quota"
                for item in result["attempts"]
            ))

    def test_gemini_image_output_image_shape(self):
        self.assertEqual(_extract_gemini_image({"output_image": {"data": "abc"}}), "abc")

    def test_gemini_image_model_output_step_shape(self):
        payload = {"steps": [{"type": "model_output", "content": [
            {"type": "text", "text": "ok"},
            {"type": "image", "data": "xyz", "mime_type": "image/png"}
        ]}]}
        self.assertEqual(_extract_gemini_image(payload), "xyz")


if __name__ == "__main__":
    unittest.main()
