"""Retrieve owner-accessible YouTube captions first, with a public transcript fallback."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _write_transcript(path: Path, text: str) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"status": "empty_transcript"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned + "\\n", encoding="utf-8")
    return {"status": "available", "file": str(path), "characters": len(cleaned)}


def _clean_caption_text(raw: str) -> str:
    """Convert common SRT/VTT caption payloads to readable plain text."""
    text = raw.lstrip("\\ufeff")
    text = re.sub(r"^WEBVTT[^\\n]*\\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value == "WEBVTT":
            continue
        if re.fullmatch(r"\\d+", value):
            continue
        if "-->" in value:
            continue
        if value.startswith(("NOTE ", "Kind:", "Language:")):
            continue
        lines.append(value)
    # Keep meaningful line breaks but remove repeated adjacent caption fragments.
    compact = []
    for line in lines:
        if not compact or compact[-1] != line:
            compact.append(line)
    return "\\n".join(compact).strip()


def _download_owner_caption(youtube, video_id: str, output: Path) -> dict:
    """Use the OAuth-authorized YouTube Captions API; never use captions.insert/update."""
    response = youtube.captions().list(
        part="snippet", videoId=video_id
    ).execute()
    tracks = response.get("items", [])
    if not tracks:
        return {"status": "no_caption_tracks", "source": "youtube_captions_api"}

    # Prefer Hindi, then Sanskrit, Urdu, Bengali, and English. Prefer standard/manual
    # tracks over ASR when both are available for the same language.
    language_order = {"hi": 0, "sa": 1, "ur": 2, "bn": 3, "en": 4}
    def rank(track):
        snippet = track.get("snippet", {})
        lang = (snippet.get("language") or "").lower().split("-")[0]
        kind = (snippet.get("trackKind") or "").upper()
        return (language_order.get(lang, 99), 1 if kind == "ASR" else 0)

    candidates = sorted(
        [t for t in tracks if (t.get("snippet", {}).get("language") or "").lower().split("-")[0] in language_order],
        key=rank
    )
    if not candidates:
        return {
            "status": "no_matching_caption_language",
            "source": "youtube_captions_api",
            "available_languages": sorted({
                t.get("snippet", {}).get("language", "")
                for t in tracks if t.get("snippet", {}).get("language")
            })
        }

    errors = []
    for track in candidates:
        caption_id = track.get("id")
        if not caption_id:
            continue
        try:
            request = youtube.captions().download(id=caption_id, tfmt="srt")
            payload = request.execute()
            if isinstance(payload, bytes):
                raw = payload.decode("utf-8-sig", errors="replace")
            else:
                raw = str(payload or "")
            cleaned = _clean_caption_text(raw)
            saved = _write_transcript(output, cleaned)
            if saved["status"] == "available":
                snippet = track.get("snippet", {})
                saved.update({
                    "source": "youtube_captions_api",
                    "caption_id": caption_id,
                    "language": snippet.get("language"),
                    "track_kind": snippet.get("trackKind")
                })
                return saved
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}"[:350])
    return {
        "status": "caption_download_failed",
        "source": "youtube_captions_api",
        "errors": errors[:5]
    }


def _diagnose_transcript_error(exc: Exception) -> tuple[str, str]:
    detail = f"{type(exc).__name__}: {exc}"[:700]
    lowered = detail.lower()
    if "requestblocked" in lowered or "blocking requests from your ip" in lowered:
        return (
            "runner_ip_blocked",
            "YouTube blocked public transcript-library requests from this GitHub runner. "
            "The official OAuth captions API was also unavailable; check caption ownership, "
            "track availability, and the granted OAuth scopes."
        )
    if "transcriptsdisabled" in lowered or "transcripts disabled" in lowered:
        return "captions_disabled", "The video does not expose captions through the public transcript library."
    if "notranscriptfound" in lowered or "no transcript" in lowered:
        return "no_matching_transcript", "No public transcript was found in the requested languages."
    return "transcript_request_failed", detail


def retrieve_video_transcript(youtube, video_id: str, output_dir="transcripts") -> dict:
    """Try OAuth YouTube Captions API first, then public transcript-library fallback."""
    output = Path(output_dir) / f"{video_id}.txt"
    metadata_path = Path(output_dir) / f"{video_id}.json"
    attempts = []

    try:
        result = _download_owner_caption(youtube, video_id, output)
        if result.get("status") == "available":
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result
        attempts.append(result)
    except Exception as exc:
        attempts.append({
            "method": "youtube_captions_api",
            "status": "api_error",
            "error": f"{type(exc).__name__}: {exc}"[:500]
        })

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        fetched = YouTubeTranscriptApi().fetch(
            video_id, languages=["hi", "sa", "ur", "bn", "en"])
        segments = getattr(fetched, "snippets", fetched)
        transcript_text = "\\n".join(
            str(segment.get("text", "") if isinstance(segment, dict)
                else getattr(segment, "text", ""))
            for segment in segments
        )
        saved = _write_transcript(output, transcript_text)
        if saved["status"] == "available":
            saved.update({"source": "youtube_transcript_api_public_fallback",
                          "attempts": attempts})
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            return saved
    except Exception as exc:
        category, explanation = _diagnose_transcript_error(exc)
        attempts.append({
            "method": "youtube_transcript_api_public_fallback",
            "category": category,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "explanation": explanation
        })

    result = {
        "status": "unavailable",
        "source": None,
        "attempts": attempts,
        "message": "No transcript could be retrieved. Confirm that a caption track exists and is accessible to the channel OAuth account."
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def retrieve_queue_transcripts(youtube, videos, output_dir="transcripts") -> dict:
    results = {}
    for video in videos:
        video_id = video.get("video_id")
        if not video_id:
            continue
        existing = Path(output_dir) / f"{video_id}.txt"
        if existing.exists() and existing.stat().st_size:
            results[video_id] = {
                "status": "available",
                "source": "existing_transcript_file",
                "file": str(existing),
                "characters": existing.stat().st_size
            }
        else:
            results[video_id] = retrieve_video_transcript(youtube, video_id, output_dir)
    available = sum(1 for item in results.values() if item.get("status") == "available")
    return {
        "videos_checked": len(results),
        "transcripts_available": available,
        "results": results
    }
