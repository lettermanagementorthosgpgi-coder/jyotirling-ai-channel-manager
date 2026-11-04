"""Two-provider AI workflow: analysis, SEO drafting, cross-review and thumbnail art."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

from .ai_providers import available_providers, generate, generate_thumbnail_background
from .thumbnail_composer import compose_thumbnail

ROLES = [
    ("AI-1_data_analysis",
     "Evidence priority: read the full transcript when available. If transcript_available is false or transcript text is empty, switch to DESCRIPTION-BASED FALLBACK and carefully analyze the existing video description and title instead. Identify the actual topic, sequence of events, named people, reasons, quotations and shlokas only when explicitly supported by the transcript. Where useful, cite short exact transcript phrases as evidence. Do not claim the transcript is missing when transcript_available is true and transcript text is supplied. Do not invent metrics or spoken content."),
    ("AI-2_youtube_seo_and_thumbnail_brief",
     "Use the full transcript as primary evidence when available; otherwise use the existing video description and title as the fallback evidence, and label all conclusions provisional/description-based. Prepare YouTube SEO: 3 title options, a complete Hindi-first description accurately summarizing what is actually spoken, relevant tags, hashtags, a concise Hindi thumbnail headline, and a detailed creative visual concept. Design the thumbnail freely from the transcript when available, otherwise from the description and title; do not force a pre-existing programme template or fixed layout. Mandatory thumbnail text: place JYOTIRLING SHIVMATH BARAULI LUCKNOW at the top centre; include the host's supplied real photograph on one side unchanged; prominently include exactly one programme label, SHIV MAHA PURAN for Shiv Puran content or BHAGVADGITA for Gita content; show the chapter number/name and chapter title together. AI chooses all other wording, imagery, colours, composition and placement based on the transcript."),
    ("AI-3_cross_review",
     "Verify claims against the transcript when supplied; otherwise verify only against the existing title and description. State clearly whether the result is transcript-based or a provisional description-based fallback. Never claim a transcript was read when unavailable. Correct unsupported claims, policy risks, factual mistakes, keyword stuffing and weak packaging. Ensure the thumbnail concept grants creative freedom while retaining the mandatory channel header at top centre, unchanged real host photo on one side, correct programme label (SHIV MAHA PURAN or BHAGVADGITA), and chapter number/name together with chapter title. Return the final corrected package and a short change log.")
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
            "duration": video.get("duration"),
            "analytics": video.get("last_90_days_analytics"),
            "daily_analytics": video.get("daily_analytics", [])
        },
        "transcript_available": bool(transcript),
        "transcript": transcript or None,
        "previous_stage_outputs": previous,
        "thumbnail_brand_rules": [
            "YouTube thumbnail must be 16:9 and designed freely by AI from the full transcript for maximum relevance, clarity and click appeal.",
            "The exact channel header JYOTIRLING SHIVMATH BARAULI LUCKNOW must appear at the top centre.",
            "Include the user's supplied real photograph on one side, unchanged; never synthesize, redraw, retouch or alter the person's face.",
            "For Shiv Puran content, prominently show the exact programme label SHIV MAHA PURAN. For Bhagavad Gita content, prominently show BHAGVADGITA. Never use the wrong programme label.",
            "Show the chapter number/name together with the chapter title as one clearly associated information unit.",
            "AI has full creative freedom over all other wording, visual storytelling, deities/characters supported by the transcript, colours, typography, layout and placement.",
            "All text must be accurate to the transcript, concise, high-contrast and readable on mobile.",
            "Do not use a fixed bhajan, legacy master-frame or forced programme-specific layout for these scripture chapter thumbnails."
        ],
        "guardrails": [
            "Never invent transcript contents, quotations, shlokas, chapter names, people or events.",
            "If transcript is missing, clearly label content as provisional and metadata-only.",
            "Do not change or publish anything on YouTube. Produce recommendations only.",
            "Use natural Hindi/Hinglish appropriate to a devotional Hindi-speaking audience.",
            "Distinguish verified facts from suggestions."
        ]
    }
    return (
        "You are a specialist in a two-provider review pipeline for the JYOTIRLING SHIVMATH channel.\n"
        + role_instruction + "\nReturn a structured, practical response.\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )


def _thumbnail_prompt(video, final_package):
    title = video.get("source_title") or video.get("title") or "Devotional video"
    description = video.get("source_description") or video.get("description") or ""
    return (
        "Create a complete, original, high-quality devotional YouTube thumbnail design in 16:9. "
        "Use the evidence-grounded visual direction and headline below to choose the strongest scene. If no transcript is supplied, use the existing video description and title as fallback and still create a description-based thumbnail, without inventing details.  "
        "composition, colours, typography and text placement. This must look like a finished thumbnail, "
        "not a generic background. Mandatory: exact channel header JYOTIRLING SHIVMATH BARAULI LUCKNOW "
        "at the top centre; the programme label SHIV MAHA PURAN for Shiv Puran or BHAGVADGITA for Gita; "
        "and chapter number/name together with the chapter title. Leave the RIGHTMOST 28 percent clean and visually quiet for the user's "
        "real photograph to be placed unchanged by the compositor; do not invent or depict the host. "
        "All other design decisions are yours, grounded in the transcript when available, otherwise in the supplied video description and title. Never invent chapter details "
        "or add unrelated deities/characters. Source video title: " + title +
        ". Source description: " + description[:2500] +
        ". Transcript-based final SEO and thumbnail brief: " + final_package[:5000] +
        ". Render readable, correctly spelled Hindi/English text where possible, with strong mobile contrast."
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
                if now < fallback_time:
                    remaining = max(0, int((fallback_time - now).total_seconds() // 3600))
                    item["ai_preparation"] = {
                        "status": "waiting_for_transcript_or_primary_scripture_source",
                        "transcript_available": False,
                        "first_seen_at": first_seen_at,
                        "fallback_allowed_at": fallback_allowed_at,
                        "hours_until_description_fallback": remaining,
                        "primary_scripture_source_status": "not_yet_connected",
                        "note": "Description-based AI drafting is intentionally held until the full 48-hour retry window has elapsed."
                    }
                    result_items.append(item)
                    continue
                source_basis = "description_fallback_after_48_hours"

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
                    final_package = stages[ROLES[2][0]]["output"]
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
                                provider, _thumbnail_prompt(item, final_package))
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
                        video=item, final_package=stages[ROLES[2][0]]["output"])
                    thumbnail_result.update(composition)
                    thumbnail_result["status"] = "thumbnail_ready_for_user_review"
                    thumbnail_result["note"] = (
                        "Original portrait, header, author plaque and frame are embedded in "
                        "the bundled legacy master JPEG.")
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
