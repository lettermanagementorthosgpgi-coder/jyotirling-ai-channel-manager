"""Retrieve an accessible public transcript without requesting YouTube write scopes."""
from __future__ import annotations

import json
from pathlib import Path


def _write_transcript(path: Path, text: str) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"status": "empty_transcript"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned + "\n", encoding="utf-8")
    return {"status": "available", "file": str(path), "characters": len(cleaned)}


def retrieve_video_transcript(youtube, video_id: str, output_dir="transcripts") -> dict:
    """Try the public transcript library only; never call YouTube captions download.

    The YouTube client parameter is retained for backwards compatibility. If public
    captions are unavailable or the runner is blocked, provide an approved transcript
    file separately. Metadata-only AI drafts must remain explicitly provisional.
    """
    del youtube
    output = Path(output_dir) / f"{video_id}.txt"
    metadata_path = Path(output_dir) / f"{video_id}.json"
    attempts = []

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        fetched = YouTubeTranscriptApi().fetch(
            video_id, languages=["hi", "en", "sa", "ur", "bn"])
        segments = getattr(fetched, "snippets", fetched)
        transcript_text = "\n".join(
            str(segment.get("text", "") if isinstance(segment, dict)
                else getattr(segment, "text", ""))
            for segment in segments
        )
        saved = _write_transcript(output, transcript_text)
        if saved["status"] == "available":
            saved.update({"source": "youtube_transcript_api_public_fallback",
                          "attempts": attempts})
            metadata_path.write_text(
                json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            return saved
    except Exception as exc:
        attempts.append({
            "method": "youtube_transcript_api_public_fallback",
            "error": f"{type(exc).__name__}: {exc}"[:400]
        })

    result = {
        "status": "unavailable",
        "source": None,
        "attempts": attempts,
        "message": (
            "Public transcript retrieval was unavailable. Supply an approved source "
            "transcript file to enable transcript-grounded preparation. No YouTube "
            "caption download or write-scope API was called."
        )
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
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
