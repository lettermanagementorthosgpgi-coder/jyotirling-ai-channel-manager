"""Three-role AI preparation workflow with retry rotation and SQLite resume state."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .ai_providers import available_providers, generate

ROLES = [
    ("AI-1_data_analysis", "Analyze the supplied video metadata and performance data. Identify the actual topic only when supported by the transcript or description. Do not invent metrics or content."),
    ("AI-2_youtube_seo", "Prepare YouTube SEO: 3 title options, a complete Hindi-first description, relevant tags, hashtags, and a thumbnail concept with concise Hindi thumbnail text. Follow YouTube policy; do not keyword-stuff."),
    ("AI-3_independent_review", "Independently review the preceding analysis and SEO package. Correct unsupported claims, policy risks, keyword stuffing, factual mistakes and weak packaging. Return a final corrected package and a short change log.")
]


def _prompt(role_instruction, video, previous, transcript):
    evidence = {
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
        "guardrails": [
            "Never invent transcript contents, quotations, shlokas, chapter names, people or events.",
            "If transcript is missing, clearly label content as provisional and metadata-only.",
            "Keep the speaker name exactly as Mahant Rajesh Kumar Tiwari Ranjan when relevant.",
            "Do not change or publish anything on YouTube. Produce recommendations only.",
            "Use natural Hindi/Hinglish appropriate to a devotional Hindi-speaking audience.",
            "Distinguish verified facts from suggestions."
        ]
    }
    return (
        "You are one specialist in a three-AI review pipeline for the JYOTIRLING SHIVMATH "
        "BARAULI LUCKNOW YouTube channel.\n"
        + role_instruction + "\nReturn a structured, practical response.\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )


def run_ai_preparation(queue, state_path, transcript_dir="transcripts"):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_dir = Path(transcript_dir)
    providers = available_providers()
    result_items = []

    with sqlite3.connect(state_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS preparations (
            video_id TEXT PRIMARY KEY, stages_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

        for item in queue.get("items", []):
            vid = item.get("video_id")
            if not vid: continue
            transcript_file = transcript_dir / f"{vid}.txt"
            transcript = transcript_file.read_text(encoding="utf-8") if transcript_file.exists() else None

            row = db.execute("SELECT stages_json FROM preparations WHERE video_id=?", (vid,)).fetchone()
            stages = json.loads(row[0]) if row else {}
            errors = []
            if not providers:
                item["ai_preparation"] = {
                    "status": "blocked_missing_api_keys",
                    "message": "Add one or more provider API keys as GitHub Actions secrets.",
                    "provider_attempts": [], "transcript_available": bool(transcript)
                }
                result_items.append(item)
                continue

            for index, (role, instruction) in enumerate(ROLES):
                if role in stages and stages[role].get("output"):
                    continue
                preferred = ["openai", "gemini", "anthropic"][index]
                order = [preferred] + [p for p in providers if p != preferred]
                if preferred not in providers:
                    order = providers[:]
                previous = {k: v.get("output", "") for k, v in stages.items()}
                succeeded = False
                for provider in order:
                    if provider not in providers: continue
                    try:
                        output, model = generate(provider, _prompt(instruction, item, previous, transcript))
                        stages[role] = {"provider": provider, "model": model, "output": output}
                        db.execute("""INSERT INTO preparations(video_id, stages_json, updated_at)
                            VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(video_id) DO UPDATE SET
                            stages_json=excluded.stages_json, updated_at=CURRENT_TIMESTAMP""",
                            (vid, json.dumps(stages, ensure_ascii=False)))
                        db.commit()
                        succeeded = True
                        break
                    except Exception as exc:
                        errors.append({"role": role, "provider": provider, "error": str(exc)[:500]})
                if not succeeded:
                    break

            complete = all(role in stages and stages[role].get("output") for role, _ in ROLES)
            item["ai_preparation"] = {
                "status": "ready_for_user_review" if complete else "pending_provider_or_retry",
                "stages": stages,
                "provider_attempts": errors,
                "transcript_available": bool(transcript),
                "grounding": "transcript_and_metadata" if transcript else "metadata_only_provisional"
            }
            result_items.append(item)

    return {
        "providers_configured": providers,
        "videos_processed_or_pending": len(result_items),
        "items": result_items,
        "note": "AI output is a draft for human review. No YouTube changes are performed."
    }
