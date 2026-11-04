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

CHAPTER_WORD_VARIANTS = {
    1: ("पहला", "प्रथम"),
    2: ("दूसरा", "द्वितीय"),
    3: ("तीसरा", "तृतीय"),
    4: ("चौथा", "चतुर्थ"),
    5: ("पांचवा", "पांचवां", "पाँचवा", "पाँचवां", "पंचम"),
    6: ("छठा", "छठवां", "छठवाँ", "षष्ठ"),
    7: ("सातवां", "सातवाँ", "सप्तम"),
    8: ("आठवां", "आठवाँ", "अष्टम"),
    9: ("नवां", "नौवां", "नवम"),
    10: ("दसवां", "दसवाँ", "दशम"),
    11: ("ग्यारहवां", "ग्यारहवाँ", "एकादश"),
    12: ("बारहवां", "बारहवाँ", "द्वादश"),
    13: ("तेरह", "तेरहवां", "तेरहवाँ", "त्रयोदश"),
    14: ("चौदह", "चौदहवां", "चौदहवाँ", "चतुर्दश"),
    15: ("पंद्रहवां", "पन्द्रहवां", "पंद्रहवाँ", "पन्द्रहवाँ", "पञ्चदश", "पंचदश"),
    16: ("सोलहवां", "सोलहवाँ", "षोडश"),
    17: ("सत्रह", "सत्रहवां", "सत्रहवाँ", "सप्तदश"),
    18: ("अठारह", "अठारहवां", "अठारहवाँ", "अष्टादश"),
}

STOP_WORDS = {
    "श्री", "भगवान", "भगवद्गीता", "श्रीमद्भगवद्गीता", "अध्याय",
    "शिव", "पुराण", "महापुराण", "कथा", "प्रवचन", "हिंदी", "और",
    "का", "की", "के", "में", "से", "है", "हैं", "तथा", "एवं",
}


def _programme(video: dict) -> str | None:
    explicit = video.get("programme")
    if explicit in ("shiv_puran", "bhagavad_gita"):
        return explicit
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
    chapter = video.get("chapter_number") or _chapter_number(query_text)
    section_name = str(video.get("khanda_name") or
                       (video.get("programme_feed") or {}).get("section_name") or "")
    pages = []
    manual_mode = bool(video.get("manual_book_mode"))
    heading_prefix = r"(?:अध्याय|अध्‍याय|अ[^\s]{0,3}याय)"
    all_chapter_words = sorted(
        {word for variants in CHAPTER_WORD_VARIANTS.values() for word in variants},
        key=len, reverse=True
    )
    all_words_pattern = "|".join(re.escape(word) for word in all_chapter_words)
    generic_heading = re.compile(
        rf"^(?:{heading_prefix}\s*[-:#]?\s*(?:[0-9]{{1,2}}|[०-९]{{1,2}}|{all_words_pattern})|"
        rf"(?:{all_words_pattern})\s*{heading_prefix})(?:\s|$|[:：])",
        flags=re.IGNORECASE
    )
    chapter = video.get("chapter_number") or _chapter_number(query_text)
    section_name = str(video.get("khanda_name") or
                       (video.get("programme_feed") or {}).get("section_name") or "")
    target_heading = None
    if chapter:
        chapter_word = DEVANAGARI_CHAPTERS.get(int(chapter), "")
        chapter_digits = str(int(chapter)).translate(str.maketrans("0123456789", "०१२३४५६७८९"))
        variants = CHAPTER_WORD_VARIANTS.get(int(chapter), ())
        target_words = "|".join(re.escape(word) for word in sorted(variants, key=len, reverse=True))
        target_parts = [str(int(chapter)), chapter_digits]
        if target_words:
            target_parts.append(target_words)
        target_heading = re.compile(
            rf"^(?:{heading_prefix}\s*[-:#]?\s*(?:{'|'.join(target_parts)})|"
            rf"(?:{target_words})\s*{heading_prefix})(?:\s|$|[:：])",
            flags=re.IGNORECASE
        )

    try:
        with fitz.open(pdf_path) as document:
            all_pages = [(index + 1, page.get_text("text") or "")
                         for index, page in enumerate(document)]
            exact_heading_pages = []
            for index, (page_number, text) in enumerate(all_pages):
                if not text.strip():
                    continue
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                heading_lines = [line for line in lines if generic_heading.match(line)]
                # Table-of-contents pages contain many chapter headings. Ignore them;
                # only accept a single, printed chapter heading on a content page.
                if manual_mode:
                    if len(heading_lines) == 1 and target_heading and any(
                            target_heading.match(line) for line in lines[:8]):
                        exact_heading_pages.append(index)
                    continue

                score = sum(2 for word in keywords if word in text.lower())
                if chapter and target_heading and any(target_heading.match(line) for line in lines[:8]):
                    score += 25
                if section_name and section_name in text:
                    score += 30
                if score:
                    pages.append((score, page_number, text))

            if manual_mode:
                section_markers = [i for i, (_, page_text) in enumerate(all_pages)
                                   if section_name and section_name in page_text]
                scoped_headings = list(exact_heading_pages)
                if section_name:
                    scoped_headings = []
                    for heading_index in exact_heading_pages:
                        previous_markers = [i for i in section_markers if i <= heading_index]
                        if not previous_markers:
                            continue
                        section_start = previous_markers[-1]
                        next_markers = [i for i in section_markers if i > section_start]
                        section_end = next_markers[0] if next_markers else len(all_pages)
                        if section_start <= heading_index < section_end:
                            scoped_headings.append(heading_index)
                if not scoped_headings:
                    return {
                        "status": "requested_chapter_heading_not_found",
                        "source_type": "primary_scripture_reference",
                        "programme": programme,
                        "chapter_number": chapter,
                        "section_name": section_name or None,
                        "note": "Manual book mode requires one unambiguous printed chapter heading in the requested book/section. Contents pages and guessed topics are not accepted."
                    }

                allowed_pages = set()
                for heading_index in scoped_headings:
                    section_end = len(all_pages)
                    if section_name:
                        previous_markers = [i for i in section_markers if i <= heading_index]
                        if previous_markers:
                            next_markers = [i for i in section_markers if i > previous_markers[-1]]
                            section_end = next_markers[0] if next_markers else len(all_pages)
                    next_chapters = [
                        i for i in range(heading_index + 1, section_end)
                        if any(generic_heading.match(line.strip())
                               for line in all_pages[i][1].splitlines() if line.strip())
                    ]
                    # Some editions omit the next Gita chapter heading in the body.
                    # In that case keep a bounded, sequential evidence window.
                    fallback_window = 21 if programme == "bhagavad_gita" else 8
                    chapter_end = (next_chapters[0] if next_chapters
                                   else min(section_end, heading_index + fallback_window))
                    allowed_pages.update(range(heading_index, chapter_end))
                pages = [
                    (25 if page_no - 1 in scoped_headings else 10, page_no, page_text)
                    for page_no, page_text in all_pages
                    if page_no - 1 in allowed_pages and page_text.strip()
                ]
    except Exception as exc:
        return {"status": "read_error", "source_type": "primary_scripture_reference",
                "error": f"{type(exc).__name__}: {exc}"[:400]}

    if video.get("manual_book_mode"):
        scoped_headings = list(exact_heading_pages)
        section_markers = [i for i, (_, page_text) in enumerate(all_pages)
                           if section_name and section_name in page_text]
        if section_name:
            scoped_headings = []
            for heading_index in exact_heading_pages:
                previous_markers = [i for i in section_markers if i <= heading_index]
                if not previous_markers:
                    continue
                section_start = previous_markers[-1]
                next_markers = [i for i in section_markers if i > section_start]
                section_end = next_markers[0] if next_markers else len(all_pages)
                if section_start <= heading_index < section_end:
                    scoped_headings.append(heading_index)
        if not scoped_headings:
            return {
                "status": "requested_chapter_heading_not_found",
                "source_type": "primary_scripture_reference",
                "programme": programme,
                "chapter_number": chapter,
                "section_name": section_name or None,
                "note": "Manual book mode requires an exact printed chapter heading in the requested book/section. No chapter topic or metadata was guessed."
            }
        allowed_pages = set()
        ordinal_words = "|".join(re.escape(word) for word in DEVANAGARI_CHAPTERS.values())
        generic_heading = re.compile(
            r"(?:अध्याय|अध्‍याय|chapter)\s*[-:#]?\s*(?:[0-9]{1,2}|[०-९]{1,2})|"
            + rf"(?:{ordinal_words})(?:ो)?ऽ?अध्याय(?:ः)?",
            flags=re.IGNORECASE
        )
        for heading_index in scoped_headings:
            section_end = len(all_pages)
            if section_name:
                previous_markers = [i for i in section_markers if i <= heading_index]
                if previous_markers:
                    next_markers = [i for i in section_markers if i > previous_markers[-1]]
                    section_end = next_markers[0] if next_markers else len(all_pages)
            next_chapters = [i for i in range(heading_index + 1, section_end)
                             if generic_heading.search(all_pages[i][1])]
            chapter_end = next_chapters[0] if next_chapters else section_end
            allowed_pages.update(range(heading_index, chapter_end))
        # Keep the complete matched chapter in book order, subject to the
        # evidence character cap below; do not truncate arbitrarily to 4 pages.
        pages = [(25 if page_no - 1 in scoped_headings else 10, page_no, page_text)
                 for page_no, page_text in all_pages
                 if page_no - 1 in allowed_pages and page_text.strip()]

    pages.sort(key=(lambda item: item[1]) if manual_mode else
               (lambda item: (-item[0], item[1])))
    excerpts = []
    used = 0
    page_limit = 21 if manual_mode and programme == "bhagavad_gita" else (8 if manual_mode else 8)
    effective_max_chars = max(max_chars, 18000) if manual_mode else max_chars
    for score, page_number, text in pages[:page_limit]:
        clean = re.sub(r"\s+", " ", text).strip()
        remaining = effective_max_chars - used
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
        "section_name": section_name or None,
        "evidence_type": "Hindi translation / explanatory text; distinguish Sanskrit verses from translator/editor commentary",
        "pages": excerpts,
        "note": "Cite PDF page numbers. Do not present translator/editor commentary as a verbatim statement of the deity or as an original Sanskrit verse.",
    }
