import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ai_pipeline import run_ai_preparation


class AIPipelineTests(unittest.TestCase):
    def test_two_providers_cross_review_and_thumbnail_fallback(self):
        queue = {"items": [{
            "video_id": "video-1",
            "source_title": "Shiv Puran Adhyay",
            "source_description": "Hindi devotional discourse",
            "source_tags": ["Shiv Puran"],
            "url": "https://youtube.com/watch?v=video-1",
            "daily_analytics": []
        }]}
        calls = []

        def fake_generate(provider, prompt):
            calls.append(provider)
            return (("शिव पुराण त्रिपुर प्रसंग शीर्षक विवरण टैग thumbnail headline " + "यह प्रमाण आधारित विस्तृत सामग्री है। " * 18), f"{provider}-test-model")

        def fake_image(provider, prompt):
            if provider == "openai":
                raise RuntimeError("simulated image outage")
            return b"\x89PNG\r\n\x1a\nfake-png", "gemini-image-test"

        def fake_compose(background, output, title, **kwargs):
            Path(output).write_bytes(b"composed-preview")
            return {"file": str(output), "author_photo_included": False,
                    "dimensions": "1280x720"}

        with tempfile.TemporaryDirectory() as tmp:
            transcript_dir = Path(tmp) / "transcripts"
            transcript_dir.mkdir()
            (transcript_dir / "video-1.txt").write_text("शिव पुराण का परीक्षण प्रतिलेख", encoding="utf-8")
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "GEMINI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "must-not-be-used"
            }), patch("src.ai_pipeline.generate", side_effect=fake_generate), \
                 patch("src.ai_pipeline.generate_thumbnail_background", side_effect=fake_image), \
                 patch("src.ai_pipeline.compose_thumbnail", side_effect=fake_compose):
                result = run_ai_preparation(
                    queue, os.path.join(tmp, "state.sqlite"),
                    str(transcript_dir), os.path.join(tmp, "thumbnails"))

        item = result["items"][0]
        self.assertEqual(result["providers_configured"], ["openai", "gemini"])
        self.assertEqual(item["ai_preparation"]["status"], "ready_for_user_review")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-1_data_analysis"]["provider"], "openai")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-2_youtube_seo_and_thumbnail_brief"]["provider"], "gemini")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-3_cross_review"]["provider"], "openai")
        self.assertEqual(item["ai_preparation"]["thumbnail"]["status"], "thumbnail_ready_for_user_review")
        self.assertTrue(item["ai_preparation"]["thumbnail"]["file"].endswith("_thumbnail.png"))
        self.assertIn("openai", calls)
        self.assertIn("gemini", calls)

    def test_fallback_to_gemini_when_openai_fails(self):
        queue = {"items": [{"video_id": "v2", "source_title": "Bhagavad Gita"}]}

        def fake_generate(provider, prompt):
            if provider == "openai":
                raise RuntimeError("simulated provider outage")
            return ("भगवद्गीता कृष्ण अर्जुन अध्याय श्रद्धा शीर्षक विवरण टैग thumbnail headline " + "यह प्रमाण आधारित सामग्री है। " * 18), "gemini-test-model"

        def fake_image(provider, prompt):
            return b"\x89PNG\r\n\x1a\nfake-png", "gemini-image-test"

        def fake_compose(background, output, title, **kwargs):
            Path(output).write_bytes(b"composed-preview")
            return {"file": str(output), "author_photo_included": True,
                    "dimensions": "1280x720"}

        with tempfile.TemporaryDirectory() as tmp:
            transcript_dir = Path(tmp) / "transcripts"
            transcript_dir.mkdir()
            (transcript_dir / "v2.txt").write_text("भगवद्गीता का परीक्षण प्रतिलेख", encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True), \
                 patch("src.ai_pipeline.generate", side_effect=fake_generate), \
                 patch("src.ai_pipeline.generate_thumbnail_background", side_effect=fake_image), \
                 patch("src.ai_pipeline.compose_thumbnail", side_effect=fake_compose):
                result = run_ai_preparation(
                    queue, os.path.join(tmp, "state.sqlite"),
                    str(transcript_dir), os.path.join(tmp, "thumbnails"))
        stages = result["items"][0]["ai_preparation"]["stages"]
        self.assertTrue(all(v["provider"] == "gemini" for v in stages.values()))

    def test_missing_transcript_waits_before_description_fallback(self):
        queue = {"items": [{"video_id": "new-video", "source_title": "Shiv Puran"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            result = run_ai_preparation(queue, os.path.join(tmp, "state.sqlite"))
        prep = result["items"][0]["ai_preparation"]
        self.assertEqual(prep["status"], "waiting_for_transcript_or_primary_scripture_source")
        self.assertFalse(prep["transcript_available"])
        self.assertEqual(prep["hours_until_description_fallback"], 48)

    def test_no_keys_does_not_mark_anything_complete(self):
        queue = {"items": [{"video_id": "v1"}]}
        with tempfile.TemporaryDirectory() as tmp:
            transcript_dir = Path(tmp) / "transcripts"
            transcript_dir.mkdir()
            (transcript_dir / "v1.txt").write_text("परीक्षण प्रतिलेख", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                result = run_ai_preparation(queue, os.path.join(tmp, "state.sqlite"),
                                            str(transcript_dir))
        self.assertEqual(result["items"][0]["ai_preparation"]["status"], "blocked_missing_api_keys")


if __name__ == "__main__":
    unittest.main()
