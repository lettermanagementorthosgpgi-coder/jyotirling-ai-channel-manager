import os
import tempfile
import unittest
from unittest.mock import patch

from src.ai_pipeline import run_ai_preparation


class AIPipelineTests(unittest.TestCase):
    def test_three_roles_rotate_to_next_provider_on_failure(self):
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
            if provider == "openai":
                raise RuntimeError("simulated provider outage")
            return f"draft from {provider}", f"{provider}-test-model"

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "GEMINI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "test"
            }), patch("src.ai_pipeline.generate", side_effect=fake_generate):
                result = run_ai_preparation(queue, os.path.join(tmp, "state.sqlite"),
                                            os.path.join(tmp, "transcripts"))

        item = result["items"][0]
        self.assertEqual(item["ai_preparation"]["status"], "ready_for_user_review")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-1_data_analysis"]["provider"], "gemini")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-2_youtube_seo"]["provider"], "gemini")
        self.assertEqual(item["ai_preparation"]["stages"]["AI-3_independent_review"]["provider"], "anthropic")
        self.assertIn("openai", calls)

    def test_no_keys_does_not_mark_anything_complete(self):
        queue = {"items": [{"video_id": "v1"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                result = run_ai_preparation(queue, os.path.join(tmp, "state.sqlite"))
        self.assertEqual(result["items"][0]["ai_preparation"]["status"], "blocked_missing_api_keys")


if __name__ == "__main__":
    unittest.main()
