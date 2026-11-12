import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.thumbnail_composer import compose_thumbnail, TEMPLATES


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
