"""Find evidence excerpts in locally provisioned primary scripture PDFs.

The PDFs are deliberately not committed to this public repository. Provision them
through a private runner-side source mount or another access-controlled store.
"""
from __future__ import annotations

import re
from pathlib import Path

DEVANAGARI_CHAPTERS = {
    1: "प्रथम", 2: "द्वितीय", 3: "तृतीय", 4: "चतुर्थ", 5: "पंचम",
    6: "षष्ठ", 7: "सप्तम", 8: "अष्टम", 9: "नवम", 10: "दशम",
    11: "एकादश", 12: "द्वादश", 13: "त्रयोदश", 14: "चतुर्दश",
    15: "पञ्चदश", 16: "षोडश", 17: "सप्तदश", 18: "अष्टादश",
}

STOP_WORDS = {
    "श्री", "भगवान", "भगवद्गीता", "श्रीमद्भगवद्गीता", "अध्याय",
    "शिव", "पुराण", "महापुराण", "कथा", "प्रवचन", "हिंदी", "और",
    "का", "की", "के", "में", "से", "है", "हैं", "तथा", "एवं",
}


def _programme(video: dict) -> str | None:
    text = " ".join(str(video.get(k) or "") for k in
                    ("source_title", "title", "source_description", "description")).lower()
    if any(x in text for x in ("bhagavad", "गीता", "गीताजी", "gita")):
        return "bhagavad_gita"
    if any(x in text for x in ("shiv puran", "शिवपुराण", "शिव पुराण", "shiv mahapuran")):
        return "shiv_puran"
    return None


def _chapter_number(text: str) -> int | None:
    patterns = (
        r"(?:अध्याय|अध्‍याय|chapter|adhyay)\s*[-:#]?\s*(\d{1,2})",
        r"(?:भाग|प्रकरण)\s*[-:#]?\s*(\d{1,2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 99:
                return value
    return None


def _keywords(text: str) -> list[str]:
    tokens = re.findall(r"[\u0900-\u097F]{3,}|[A-Za-z]{4,}", text.lower())
    return [t for t in dict.fromkeys(tokens) if t not in STOP_WORDS][:18]


def find_primary_scripture_source(video: dict, source_dir="scripture_sources/pdfs",
                                  max_chars: int = 7000) -> dict:
    """Return a small, page-cited evidence pack; never treat commentary as scripture."""
    programme = _programme(video)
    if not programme:
        return {"status": "not_applicable", "source_type": None}

    root = Path(source_dir)
    expected = {
        "bhagavad_gita": ("bhagavad_gita_yatharoop.pdf", "bhagavad_gita.pdf"),
        "shiv_puran": ("shiv_puran.pdf", "shiva_puran.pdf"),
    }[programme]
    pdf_path = next((root / name for name in expected if (root / name).is_file()), None)
    if pdf_path is None:
        return {
            "status": "source_file_not_provisioned",
            "source_type": "primary_scripture_reference",
            "programme": programme,
            "expected_files": list(expected),
            "note": "The source PDF is not mounted in the runner. Do not claim scripture lookup succeeded.",
        }

    try:
        import fitz
    except ImportError:
        return {"status": "dependency_missing", "source_type": "primary_scripture_reference",
                "error": "PyMuPDF is not installed."}

    title = str(video.get("source_title") or video.get("title") or "")
    description = str(video.get("source_description") or video.get("description") or "")
    query_text = (title + " " + description[:1200]).strip()
    keywords = _keywords(query_text)
    chapter = _chapter_number(query_text)
    pages = []

    try:
        with fitz.open(pdf_path) as document:
            for index, page in enumerate(document):
                text = page.get_text("text") or ""
                if not text.strip():
                    continue
                score = sum(2 for word in keywords if word in text.lower())
                if chapter and programme == "bhagavad_gita":
                    chapter_word = DEVANAGARI_CHAPTERS.get(chapter, "")
                    if (f"अध्याय {chapter}" in text or
                            (chapter_word and f"अध्याय {chapter_word}" in text)):
                        score += 12
                if score:
                    pages.append((score, index + 1, text))
    except Exception as exc:
        return {"status": "read_error", "source_type": "primary_scripture_reference",
                "error": f"{type(exc).__name__}: {exc}"[:400]}

    pages.sort(key=lambda item: (-item[0], item[1]))
    excerpts = []
    used = 0
    for score, page_number, text in pages[:8]:
        clean = re.sub(r"\s+", " ", text).strip()
        remaining = max_chars - used
        if remaining <= 0:
            break
        excerpt = clean[:min(remaining, 1500)]
        excerpts.append({"pdf_page": page_number, "relevance_score": score,
                         "excerpt": excerpt})
        used += len(excerpt)
    if not excerpts:
        return {"status": "no_relevant_passage_found",
                "source_type": "primary_scripture_reference",
                "programme": programme, "chapter_number": chapter}

    return {
        "status": "matched",
        "source_type": "primary_scripture_reference",
        "programme": programme,
        "source_file": pdf_path.name,
        "chapter_number": chapter,
        "evidence_type": "Hindi translation / explanatory text; distinguish Sanskrit verses from translator/editor commentary",
        "pages": excerpts,
        "note": "Cite PDF page numbers. Do not present translator/editor commentary as a verbatim statement of the deity or as an original Sanskrit verse.",
    }
