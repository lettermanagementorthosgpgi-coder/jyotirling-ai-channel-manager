"""Two-provider AI workflow: analysis, SEO drafting, cross-review and thumbnail art."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

from .ai_providers import available_providers, generate, generate_thumbnail_background
from .thumbnail_composer import compose_thumbnail
from .scripture_sources import find_primary_scripture_source

ROLES = [
    ("AI-1_data_analysis",
     "Evidence priority: use the full transcript first when supplied. If no transcript is supplied, inspect primary_scripture_source. When its status is matched, use only its page-numbered excerpts as primary-scripture evidence, clearly label the result scripture-reference-based (Hindi translation/explanatory text), and cite the PDF page numbers. Distinguish original Sanskrit verses from Hindi translation and editor/commentary; never attribute commentary as verbatim divine speech. Use title/description only for identifying the chapter/topic, not as a substitute for scripture evidence. If no transcript and no matched scripture source, do not draft until the 48-hour wait has elapsed; only then use title/description and label the result description-based. Never invent metrics or spoken content."),
    ("AI-2_youtube_seo_and_thumbnail_brief",
     "Use the full transcript as primary evidence when available. If absent, use a matched primary_scripture_source pack as the evidence base, cite its PDF pages, and clearly label claims as based on Hindi scripture translation/explanatory text rather than a transcript. Use the title/description only to identify the likely chapter/topic. If neither transcript nor matched scripture source is available, this stage should only run after the 48-hour wait and must be labelled description-based. Prepare YouTube SEO: 3 title options, a complete Hindi-first description accurately summarizing the source, relevant tags, hashtags, a concise Hindi thumbnail headline and a chapter-grounded visual concept. The thumbnail uses a FIXED layout: original supplied author photo always on the LEFT, unflipped and unretouched; TOP-MIDDLE ornamental designer plaque with two Hindi lines exactly 'ज्योतिर्लिंग शिवमठ' and 'बरौली, लखनऊ'; BOTTOM-MIDDLE ornamental designer plaque with exactly one Hindi book label, 'शिव महापुराण' for Shiv Puran or 'भगवद्गीता' for Bhagavad Gita; verified chapter number/name immediately ABOVE the bottom plaque; the main chapter-specific subject headline is large and directly over the background artwork, in the centre/right, with bright contrasting Hindi lettering, dark outline and localized shadow. Do not use English branding, a large dark central panel, or a full-frame dark overlay. Keep the background image bright and visible. Only the background scene, headline, chapter text and relevant book label vary; all fixed positions and branding remain unchanged."),
    ("AI-3_cross_review",
     "Verify claims against the transcript when supplied; otherwise verify against the matched primary_scripture_source excerpts and cite their PDF pages. Distinguish Sanskrit verses, Hindi translation, and commentary; never attribute commentary to a deity as verbatim speech. If neither source exists after the 48-hour wait, verify only against title/description and label the result description-based. State clearly which evidence basis was used. Never claim a transcript was read when unavailable. Correct unsupported claims, policy risks, factual mistakes, keyword stuffing and weak packaging. Verify that the thumbnail follows the fixed Hindi design exactly: unchanged original author photo LEFT; top-middle two-line ornamental plaque 'ज्योतिर्लिंग शिवमठ' / 'बरौली, लखनऊ'; bottom-middle ornamental plaque with 'शिव महापुराण' or 'भगवद्गीता'; verified chapter line just above the bottom plaque; large chapter-specific Hindi subject over the bright background, centre/right, using high-contrast text with localized outline/shadow. Reject English branding, a right-side portrait, oversized dark panels, or an overall darkened background. Return the final corrected package and a short change log.")
]


def _safe_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "video"))
    return cleaned[:100] or "video"


def _prompt(role_instruction, video, previous, transcript):
    evidence = {
        "channel": "JYOTIRLING SHIVMATH BARAULI LUCKNOW",
        "speaker": "Mahant Rajesh Kumar Tiwari Ranjan",
        "video": {
            "video_id": video.get("video_id"),
            "url": video.get("url"),
            "published_at": video.get("published_at"),
            "existing_title": video.get("source_title") or video.get("title"),
            "existing_description": video.get("source_description") or video.get("description"),
            "existing_tags": video.get("source_tags") or video.get("tags", []),
            "programme": video.get("programme"),
            "programme_slot": video.get("programme_slot"),
            "manual_book_mode": bool(video.get("manual_book_mode")),
            "programme_feed": video.get("programme_feed"),
            "chapter_number": video.get("chapter_number"),
            "chapter_title": video.get("chapter_title"),
            "khanda_name": video.get("khanda_name"),
            "duration": video.get("duration"),
            "analytics": video.get("last_90_days_analytics"),
            "daily_analytics": video.get("daily_analytics", [])
        },
        "transcript_available": bool(transcript),
        "transcript": transcript or None,
        "primary_scripture_source": video.get("primary_scripture_source"),
        "previous_stage_outputs": previous,
        "thumbnail_brand_rules": [
            "FIXED 16:9 MASTER LAYOUT; do not redesign or move permanent elements.",
            "Original supplied author photograph is always on the LEFT, same orientation, unchanged and unretouched.",
            "TOP-MIDDLE ornamental designer plaque: line 1 exactly 'ज्योतिर्लिंग शिवमठ'; line 2 exactly 'बरौली, लखनऊ'. Both lines in Hindi.",
            "BOTTOM-MIDDLE ornamental designer plaque: exactly 'शिव महापुराण' for Shiv Puran or 'भगवद्गीता' for Bhagavad Gita.",
            "Place the verified chapter number and chapter title immediately ABOVE the bottom book plaque.",
            "Place the main chapter-specific Hindi subject headline large over the background artwork in the centre/right, with bright high-contrast lettering, a dark outline and localized shadow only.",
            "Keep the original background bright and visible; never put a large dark panel behind the headline or darken the whole image.",
            "Only chapter-specific background artwork, headline and verified chapter text vary. All text must be accurate and mobile-readable."
        ],
        "guardrails": [
            "Never invent transcript contents, quotations, shlokas, chapter names, people or events.",
            "For manual_book_mode, read the matched original PDF chapter excerpts and identify the chapter's printed heading/title from that source. If the exact printed title is not present, explicitly say it could not be verified; never manufacture a title.",
            "If transcript is missing but primary_scripture_source.status is matched, ground the draft in its page-cited excerpts and label it scripture-reference-based; do not call it transcript-based or metadata-only.",
            "If neither transcript nor a matched scripture source is available, description/title may be used only after the 48-hour wait and must be labelled description-based.",
            "Do not change or publish anything on YouTube. Produce recommendations only.",
            "Use natural Hindi/Hinglish appropriate to a devotional Hindi-speaking audience.",
            "Distinguish verified facts from suggestions."
        ]
    }
    return (
        "You are a specialist in a two-provider review pipeline for the JYOTIRLING SHIVMATH channel.\n"
        "Evidence hierarchy: user transcript first; otherwise use a matched primary scripture source pack with PDF page references; only after the 48-hour wait may description/title be used. When a scripture pack is matched, use its page-cited excerpts as evidence even though transcript_available is false. Distinguish Sanskrit verses from Hindi translation and commentary; never attribute commentary to the deity as verbatim speech.\n"
        + role_instruction + "\nReturn a structured, practical response.\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )


def _thumbnail_prompt(video, final_package):
    title = video.get("source_title") or video.get("title") or "Devotional video"
    description = video.get("source_description") or video.get("description") or ""
    programme = video.get("programme")
    chapter_title = video.get("chapter_title") or ""
    chapter_number = video.get("chapter_number") or ""
    section = video.get("khanda_name") or video.get("programme_feed", {}).get("section_name") or ""
    if programme == "bhagavad_gita":
        scene_direction = (
            "Create a respectful, cinematic Bhagavad Gita scene specifically grounded in the supplied chapter title "
            "and evidence brief. Krishna and Arjuna may appear only when relevant to the chapter. Do not assume "
            "that every chapter is about faith or the same episode. No Shiva, trident or unrelated deities."
        )
    else:
        scene_direction = (
            "Create a respectful, cinematic Shiv Mahapuran scene specifically grounded in the supplied khanda, "
            "chapter title and evidence brief. Depict the exact episode or figures supported by that chapter; "
            "do not reuse a generic Shiva-Parvati scene when the chapter describes a different event."
        )
    return (
        "Create ONLY original devotional background artwork for a finished 16:9 YouTube thumbnail. "
        + scene_direction +
        " Absolutely no words, letters, numbers, logos, watermarks, banners, labels or captions. "
        "Do not depict the channel host or any portrait; the original host photo will be composited separately "
        "on the LEFT. Keep the LEFT 22 percent relatively calm for that portrait, but do not make it a dark blank "
        "strip. Keep the CENTRE and RIGHT visually rich and chapter-specific, with clear visual space for large "
        "Hindi headline lettering to be composited over the artwork. Keep the TOP-MIDDLE and BOTTOM-MIDDLE "
        "reasonably uncluttered for small ornamental branding plaques. Do not darken the entire scene; use vivid, "
        "natural devotional lighting and a bright, detailed background. No typography panels are to be generated. "
        "Chapter/programme context: " + str(programme) + "; " + str(section) + "; chapter " +
        str(chapter_number) + " — " + chapter_title +
        ". Video title: " + title +
        ". Source description: " + description[:1800] +
        ". AI-reviewed scripture-grounded visual brief: " + final_package[:6500]
    )


def run_ai_preparation(queue, state_path, transcript_dir="transcripts",
                       thumbnail_dir="thumbnails", force_reprocess_video_ids=None):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_dir = Path(transcript_dir)
    thumbnail_dir = Path(thumbnail_dir)
    providers = available_providers()
    result_items = []
    force_reprocess_video_ids = set(force_reprocess_video_ids or [])

    with sqlite3.connect(state_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS preparations_v2 (
            video_id TEXT PRIMARY KEY, stages_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS source_retry (
            video_id TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL,
            last_attempt_at TEXT NOT NULL, fallback_allowed_at TEXT NOT NULL)""")

        for item in queue.get("items", []):
            vid = item.get("video_id")
            if not vid:
                continue
            transcript_file = transcript_dir / f"{_safe_id(vid)}.txt"
            transcript = transcript_file.read_text(encoding="utf-8") if transcript_file.exists() else None
            row = db.execute("SELECT stages_json FROM preparations_v2 WHERE video_id=?", (vid,)).fetchone()
            stages = json.loads(row[0]) if row else {}
            if vid in force_reprocess_video_ids:
                # Discard stale drafts so every AI stage receives the current source material.
                stages = {}
                db.execute("DELETE FROM preparations_v2 WHERE video_id=?", (vid,))
                db.commit()

            source_basis = "transcript"
            if transcript:
                db.execute("DELETE FROM source_retry WHERE video_id=?", (vid,))
            else:
                scripture_source = find_primary_scripture_source(item)
                item["primary_scripture_source"] = scripture_source
                now = datetime.now(timezone.utc)
                retry_row = db.execute(
                    "SELECT first_seen_at, fallback_allowed_at FROM source_retry WHERE video_id=?",
                    (vid,)).fetchone()
                if retry_row:
                    first_seen_at, fallback_allowed_at = retry_row
                    fallback_time = datetime.fromisoformat(fallback_allowed_at)
                else:
                    first_seen_at = now.isoformat()
                    fallback_time = now + timedelta(hours=48)
                    fallback_allowed_at = fallback_time.isoformat()
                db.execute("""INSERT INTO source_retry(
                    video_id, first_seen_at, last_attempt_at, fallback_allowed_at)
                    VALUES(?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at""",
                    (vid, first_seen_at, now.isoformat(), fallback_allowed_at))
                db.commit()
                if scripture_source.get("status") != "matched" and item.get("manual_book_mode"):
                    item["ai_preparation"] = {
                        "status": "manual_book_source_not_matched_needs_source_check",
                        "transcript_available": False,
                        "primary_scripture_source_status": scripture_source.get("status"),
                        "primary_scripture_source": scripture_source,
                        "note": "Manual book mode will not fall back to guessed chapter content. Verify the requested chapter in the provisioned original PDF before generating metadata or a thumbnail."
                    }
                    result_items.append(item)
                    continue
                if now < fallback_time and scripture_source.get("status") != "matched":
                    remaining = max(0, int((fallback_time - now).total_seconds() // 3600))
                    item["ai_preparation"] = {
                        "status": "waiting_for_transcript_or_primary_scripture_source",
                        "transcript_available": False,
                        "first_seen_at": first_seen_at,
                        "fallback_allowed_at": fallback_allowed_at,
                        "hours_until_description_fallback": remaining,
                        "primary_scripture_source_status": scripture_source.get("status"),
                        "primary_scripture_source": scripture_source,
                        "note": "Description-based AI drafting is intentionally held until the full 48-hour retry window has elapsed."
                    }
                    result_items.append(item)
                    continue
                source_basis = ("primary_scripture" if scripture_source.get("status") == "matched" else "description_fallback_after_48_hours")

            errors = []
            if not providers:
                item["ai_preparation"] = {
                    "status": "blocked_missing_api_keys",
                    "message": "Add OPENAI_API_KEY and/or GEMINI_API_KEY as GitHub Actions secrets.",
                    "provider_attempts": [], "transcript_available": bool(transcript)
                }
                result_items.append(item)
                continue

            stop_queue = False
            for index, (role, instruction) in enumerate(ROLES):
                if role in stages and stages[role].get("output"):
                    continue
                if index == 0:
                    preferred = "openai"
                elif index == 1:
                    preferred = "gemini"
                else:
                    # AI-3 is Cloudflare Workers AI: an independent third-provider cross-review.
                    preferred = "cloudflare"
                order = ([preferred] if preferred in providers else []) + [
                    p for p in providers if p != preferred
                ]
                previous = {k: v.get("output", "") for k, v in stages.items()}
                succeeded = False
                for provider in order:
                    try:
                        output, model = generate(
                            provider, _prompt(instruction, item, previous, transcript))
                        stages[role] = {"provider": provider, "model": model, "output": output}
                        db.execute("""INSERT INTO preparations_v2(video_id, stages_json, updated_at)
                            VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET
                            stages_json=excluded.stages_json, updated_at=CURRENT_TIMESTAMP""",
                            (vid, json.dumps(stages, ensure_ascii=False)))
                        db.commit()
                        succeeded = True
                        break
                    except Exception as exc:
                        errors.append({"role": role, "provider": provider,
                                       "error": f"{type(exc).__name__}: {exc}"[:500]})
                if not succeeded:
                    # Do not advance to another stage or video until this stage succeeds.
                    stop_queue = True
                    break

            complete = all(role in stages and stages[role].get("output") for role, _ in ROLES)
            thumbnail_result = {"status": "not_attempted"}
            if complete:
                thumbnail_dir.mkdir(parents=True, exist_ok=True)
                image_path = thumbnail_dir / f"{_safe_id(vid)}_background.png"
                if image_path.exists() and image_path.stat().st_size > 0:
                    thumbnail_result = {"status": "background_ready", "file": str(image_path)}
                else:
                    final_package = stages[ROLES[1][0]]["output"]
                    cross_review = stages[ROLES[2][0]]["output"]
                    thumbnail_brief = final_package + "\n\nCross-review corrections:\n" + cross_review
                    # Cloudflare FLUX is the primary thumbnail-background generator.
                    # Keep other configured image providers as fallbacks.
                    image_order = (["cloudflare"] if "cloudflare" in providers else []) + [
                        p for p in providers if p != "cloudflare"
                    ]
                    image_errors = []
                    image_attempts = []
                    for provider in image_order:
                        try:
                            image_bytes, image_model = generate_thumbnail_background(
                                provider, _thumbnail_prompt(item, thumbnail_brief))
                            if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                                raise ValueError("Image provider did not return a PNG file")
                            image_path.write_bytes(image_bytes)
                            image_attempts.append({
                                "provider": provider, "model": image_model,
                                "status": "success"
                            })
                            thumbnail_result = {
                                "status": "background_ready_needs_brand_composition",
                                "file": str(image_path),
                                "provider": provider,
                                "model": image_model,
                                "provider_attempts": image_attempts,
                                "fallback_errors": image_errors,
                                "note": "AI-generated background; original author photo and channel branding are composited separately."
                            }
                            break
                        except Exception as exc:
                            failure = {"provider": provider, "status": "failed",
                                        "error": f"{type(exc).__name__}: {exc}"[:500]}
                            image_errors.append(failure)
                            image_attempts.append(failure)
                    if thumbnail_result["status"] == "not_attempted":
                        thumbnail_result = {"status": "image_generation_pending",
                                             "provider_attempts": image_attempts}

            if thumbnail_result.get("file") and Path(thumbnail_result["file"]).exists():
                try:
                    composed_path = thumbnail_dir / f"{_safe_id(vid)}_thumbnail.png"
                    composition = compose_thumbnail(
                        thumbnail_result["file"], composed_path,
                        item.get("source_title") or item.get("title") or "विशेष आध्यात्मिक प्रवचन",
                        video=item, final_package=stages[ROLES[1][0]]["output"])
                    thumbnail_result.update(composition)
                    thumbnail_result["status"] = "thumbnail_ready_for_user_review"
                    thumbnail_result["note"] = (
                        "The exact channel header, programme label, chapter text, headline and "
                        "supplied original portrait are composed separately for human review.")
                except Exception as exc:
                    thumbnail_result = {
                        "status": "background_ready_composition_failed",
                        "background_file": thumbnail_result.get("file"),
                        "composition_error": f"{type(exc).__name__}: {exc}"[:500]
                    }

            if thumbnail_result.get("provider"):
                thumbnail_result["image_generation"] = {
                    "provider": thumbnail_result.get("provider"),
                    "model": thumbnail_result.get("model"),
                    "attempts": thumbnail_result.get("provider_attempts", []),
                    "fallback_errors": thumbnail_result.get("fallback_errors", [])
                }
            item["ai_preparation"] = {
                "status": "ready_for_user_review" if complete else "pending_provider_or_retry",
                "stages": stages,
                "provider_attempts": errors,
                "transcript_available": bool(transcript),
                "grounding": "transcript_and_metadata" if transcript else source_basis,
                "thumbnail": thumbnail_result
            }
            result_items.append(item)
            if stop_queue:
                # Leave later queue items untouched; the next run resumes this video/stage.
                break

    return {
        "providers_configured": providers,
        "videos_processed_or_pending": len(result_items),
        "items": result_items,
        "note": "AI outputs and thumbnail backgrounds are drafts for human review. No YouTube changes are performed."
    }
