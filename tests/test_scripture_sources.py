from src.scripture_sources import find_primary_scripture_source


def test_scripture_lookup_reports_missing_private_pdf(tmp_path):
    result = find_primary_scripture_source(
        {"title": "Bhagavad Gita Adhyay 15 Purushottam Yog"},
        source_dir=tmp_path,
    )
    assert result["status"] == "source_file_not_provisioned"
    assert result["programme"] == "bhagavad_gita"
    assert "bhagavad_gita_yatharoop.pdf" in result["expected_files"]


def test_scripture_lookup_ignores_unrelated_video(tmp_path):
    result = find_primary_scripture_source(
        {"title": "Morning devotional bhajan"},
        source_dir=tmp_path,
    )
    assert result["status"] == "not_applicable"


def test_shiv_puran_programme_is_recognized(tmp_path):
    result = find_primary_scripture_source(
        {"title": "Shiv Puran Rudra Sanhita Adhyay 20"},
        source_dir=tmp_path,
    )
    assert result["status"] == "source_file_not_provisioned"
    assert result["programme"] == "shiv_puran"
