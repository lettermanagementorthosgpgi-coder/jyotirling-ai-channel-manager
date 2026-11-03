"""Two-provider AI workflow: analysis, SEO drafting, cross-review and thumbnail art."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .ai_providers import available_providers, generate, generate_thumbnail_background
from .thumbnail_composer import compose_thumbnail

ROLES = [
    ("AI-1_data_analysis",
     "Analyze the supplied video metadata and performance data. Identify the actual topic only when supported by transcript or description. Do not invent metrics or spoken content."),
    ("AI-2_youtube_seo_and_thumbnail_brief",
     "Prepare YouTube SEO: 3 title options, a complete Hindi-first description, relevant tags, hashtags, a concise Hindi thumbnail headline, and a detailed visual concept. Respect the channel's fixed brand rules."),
    ("AI-3_cross_review",
     "Independently review the analysis and SEO package. Correct unsupported claims, policy risks, factual mistakes, keyword stuffing and weak packaging. Return the final corrected package and a short change log.")
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
            "YouTube thumbnail aspect ratio must be 16:9.",
            "Keep the channel header exactly: JYOTIRLING SHIVMATH BARAULI LUCKNOW.",
            "Speaker name is exactly: Mahant Rajesh Kumar Tiwari Ranjan.",
            "Keep the user's real photograph unchanged; never synthesize or alter the person's face.",
            "For Bhagavad Gita videos retain the established fixed template; update only chapter/topic text and relevant background.",
            "For Shiv Puran videos retain the established fixed layout and select a chapter-relevant devotional background.",
            "Keep Hindi topic text short, large, centered and mobile-readable."
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
        "Create ONLY the cinematic devotional background artwork for a YouTube thumbnail. "
        "Landscape 16:9 composition. Do not render any words, letters, numbers, logos, watermarks, "
        "borders, banners, captions, or human portraits. Keep clean negative space in the central "
        "area for later Hindi typography and reserve a calm area near one edge for a real author "
        "photo to be composited separately. Respect Hindu devotional iconography; do not add "
        "unrequested deities or extra characters. The source video title is: " + title +
        ". Source description: " + description[:2500] +
        ". Approved visual direction and Hindi headline from the SEO/review stages: " +
        final_package[:5000] +
        ". Produce a respectful, high-quality, luminous devotional scene suitable for a Hindi "
        "spiritual YouTube channel. This is background art only, not a finished branded thumbnail."
    )


def run_ai_preparation(queue, state_path, transcript_dir="transcripts",
                       thumbnail_dir="thumbnails"):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_dir = Path(transcript_dir)
    thumbnail_dir = Path(thumbnail_dir)
    providers = available_providers()
    result_items = []

    with sqlite3.connect(state_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS preparations_v2 (
            video_id TEXT PRIMARY KEY, stages_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

        for item in queue.get("items", []):
            vid = item.get("video_id")
            if not vid:
                continue
            transcript_file = transcript_dir / f"{_safe_id(vid)}.txt"
            transcript = transcript_file.read_text(encoding="utf-8") if transcript_file.exists() else None
            row = db.execute("SELECT stages_json FROM preparations_v2 WHERE video_id=?", (vid,)).fetchone()
            stages = json.loads(row[0]) if row else {}
            errors = []
            if not providers:
                item["ai_preparation"] = {
                    "status": "blocked_missing_api_keys",
                    "message": "Add OPENAI_API_KEY and/or GEMINI_API_KEY as GitHub Actions secrets.",
                    "provider_attempts": [], "transcript_available": bool(transcript)
                }
                result_items.append(item)
                continue

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
                    preferred_image_provider = stages[ROLES[2][0]]["provider"]
                    image_order = ([preferred_image_provider] if preferred_image_provider in providers else []) + [
                        p for p in providers if p != preferred_image_provider
                    ]
                    image_errors = []
                    for provider in image_order:
                        try:
                            image_bytes, image_model = generate_thumbnail_background(
                                provider, _thumbnail_prompt(item, final_package))
                            if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                                raise ValueError("Image provider did not return a PNG file")
                            image_path.write_bytes(image_bytes)
                            thumbnail_result = {
                                "status": "background_ready_needs_brand_composition",
                                "file": str(image_path),
                                "provider": provider,
                                "model": image_model,
                                "note": "Background artwork only. The fixed channel branding and original author photo still need to be composited."
                            }
                            break
                        except Exception as exc:
                            image_errors.append({"provider": provider,
                                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
                    if thumbnail_result["status"] == "not_attempted":
                        thumbnail_result = {"status": "image_generation_pending",
                                             "provider_attempts": image_errors}

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

            item["ai_preparation"] = {
                "status": "ready_for_user_review" if complete else "pending_provider_or_retry",
                "stages": stages,
                "provider_attempts": errors,
                "transcript_available": bool(transcript),
                "grounding": "transcript_and_metadata" if transcript else "metadata_only_provisional",
                "thumbnail": thumbnail_result
            }
            result_items.append(item)

    return {
        "providers_configured": providers,
        "videos_processed_or_pending": len(result_items),
        "items": result_items,
        "note": "AI outputs and thumbnail backgrounds are drafts for human review. No YouTube changes are performed."
    }
