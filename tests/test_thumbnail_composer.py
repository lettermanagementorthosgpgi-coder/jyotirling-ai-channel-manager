import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.thumbnail_composer import compose_thumbnail, TEMPLATES, _split_script_runs, _font_for_run


class MasterThumbnailComposerTests(unittest.TestCase):
    def test_both_permanent_book_templates_are_present(self):
        for programme in ("bhagavad_gita", "shiv_puran"):
            with self.subTest(programme=programme):
                self.assertTrue(TEMPLATES[programme].is_file())
                with Image.open(TEMPLATES[programme]) as image:
                    self.assertEqual(image.size, (1280, 720))

    def test_composer_uses_fixed_shiv_template_and_manual_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "shiv.png"
            with patch.dict(os.environ, {
                "THUMBNAIL_TRICKY_TITLE": "शिवतत्त्व का रहस्य",
                "THUMBNAIL_LESSON_TEXT": "पंचम खंड • अध्याय 13",
            }):
                result = compose_thumbnail(
                    None, output, "ignored AI title",
                    video={"programme": "shiv_puran"},
                    final_package="AI output is not used for thumbnail copy",
                )
            self.assertTrue(output.is_file())
            self.assertEqual(result["master_template"], "master_thumbnail_shiv_puran_reference.jpg")
            self.assertEqual(result["thumbnail_headline"], "शिवतत्त्व का रहस्य")
            self.assertEqual(result["chapter_text"], "पंचम खंड - अध्याय 13")
            self.assertFalse(result["youtube_uploaded"])

    def test_english_only_manual_copy_uses_latin_font_and_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "english.png"
            with patch.dict(os.environ, {
                "THUMBNAIL_TRICKY_TITLE": "THE SECRET OF KARMA YOGA",
                "THUMBNAIL_LESSON_TEXT": "BHAGAVAD GITA CHAPTER 2",
            }):
                result = compose_thumbnail(
                    None, output, "ignored",
                    video={"programme": "bhagavad_gita"},
                )
            self.assertTrue(output.is_file())
            self.assertEqual(result["thumbnail_headline"], "THE SECRET OF KARMA YOGA")
            self.assertEqual(result["chapter_text"], "BHAGAVAD GITA CHAPTER 2")
            self.assertLessEqual(result["title_layout"]["lines"], 3)
            self.assertEqual(result["lesson_layout"]["lines"], 1)

    def test_mixed_hindi_english_manual_copy_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "mixed.png"
            with patch.dict(os.environ, {
                "THUMBNAIL_TRICKY_TITLE": "कर्म योग का SECRET",
                "THUMBNAIL_LESSON_TEXT": "अध्याय 2 - CHAPTER TWO",
            }):
                result = compose_thumbnail(
                    None, output, "ignored",
                    video={"programme": "bhagavad_gita"},
                )
            self.assertTrue(output.is_file())
            self.assertEqual(result["thumbnail_headline"], "कर्म योग का SECRET")
            self.assertEqual(result["chapter_text"], "अध्याय 2 - CHAPTER TWO")

    def test_mixed_script_is_split_into_independent_font_runs(self):
        self.assertEqual(
            _split_script_runs("कर्म योग SECRET 123"),
            ["कर्म", " ", "योग", " SECRET 123"],
        )
        hindi_font = _font_for_run(28, "कर्म योग")
        latin_font = _font_for_run(28, "SECRET 123")
        self.assertNotEqual(hindi_font.path, latin_font.path)

    def test_composer_uses_fixed_gita_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gita.png"
            result = compose_thumbnail(
                None, output, "ignored",
                video={"programme": "bhagavad_gita"},
            )
            self.assertEqual(result["master_template"], "master_thumbnail_gita_blank_master.jpg")
            self.assertIsNone(result["thumbnail_headline"])
            self.assertIsNone(result["chapter_text"])

    def test_unknown_programme_is_rejected(self):
        with self.assertRaises(ValueError):
            compose_thumbnail(None, "/tmp/invalid.png", "", video={"programme": "unknown"})


if __name__ == "__main__":
    unittest.main()
