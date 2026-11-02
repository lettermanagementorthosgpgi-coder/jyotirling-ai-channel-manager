"""Retrieve captions for channel-owned videos with official and fallback methods."""
from __future__ import annotations

import json
from pathlib import Path


def _write_transcript(path: Path, text: str) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"status": "empty_transcript"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned + "\\n", encoding="utf-8")
    return {"status": "available", "file": str(path), "characters": len(cleaned)}


def retrieve_video_transcript(youtube, video_id: str, output_dir="transcripts") -> dict:
    """Try official owner-authorized captions first, then public transcript fallback.

    Does not download video/audio. Official captions require youtube.force-ssl
    OAuth and edit permission on the video. Fallback library availability varies.
    """
    output = Path(output_dir) / f"{video_id}.txt"
    metadata_path = Path(output_dir) / f"{video_id}.json"
    attempts = []

    # Official YouTube Data API: captions.list returns track metadata only;
    # captions.download retrieves the actual caption file.
    try:
        response = youtube.captions().list(part="id,snippet", videoId=video_id).execute()
        tracks = response.get("items", [])
        if not tracks:
            attempts.append({"method": "youtube_data_api", "status": "no_caption_tracks"})
        else:
            # Prefer Hindi, then original-language tracks, then any available track.
            tracks.sort(key=lambda item: (
                0 if item.get("snippet", {}).get("language") == "hi" else
                1 if item.get("snippet", {}).get("trackKind") == "standard" else 2))
            for track in tracks:
                try:
                    content = youtube.captions().download(
                        id=track["id"], tfmt="srt").execute()
                    if isinstance(content, bytes):
                        raw = content.decode("utf-8-sig", errors="replace")
                    else:
                        raw = str(content)
                    # Remove SRT sequence numbers and timecodes, retain spoken text.
                    import re
                    lines = []
                    for line in raw.splitlines():
                        value = line.strip()
                        if not value or value.isdigit() or "-->" in value:
                            continue
                        lines.append(value)
                    saved = _write_transcript(output, "\\n".join(lines))
                    if saved["status"] == "available":
                        saved.update({"source": "youtube_data_api",
                                      "language": track.get("snippet", {}).get("language"),
                                      "track_kind": track.get("snippet", {}).get("trackKind"),
                                      "attempts": attempts})
                        metadata_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
                        return saved
                except Exception as exc:
                    attempts.append({"method": "youtube_data_api_download",
                                     "track_id": track.get("id"),
                                     "error": f"{type(exc).__name__}: {exc}"[:400]})
    except Exception as exc:
        attempts.append({"method": "youtube_data_api_list",
                         "error": f"{type(exc).__name__}: {exc}"[:400]})

    # Best-effort public transcript fallback. This is not an official YouTube API
    # and may be blocked or unavailable for a particular video.
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["hi", "en", "sa", "ur", "bn"])
        segments = getattr(fetched, "snippets", fetched)
        text = "\\n".join(
            str(segment.get("text", "") if isinstance(segment, dict) else getattr(segment, "text", ""))
            for segment in segments
        )
        saved = _write_transcript(output, text)
        if saved["status"] == "available":
            saved.update({"source": "youtube_transcript_api_fallback",
                          "attempts": attempts})
            metadata_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            return saved
    except Exception as exc:
        attempts.append({"method": "youtube_transcript_api_fallback",
                         "error": f"{type(exc).__name__}: {exc}"[:400]})

    result = {"status": "unavailable", "source": None, "attempts": attempts,
              "message": "No downloadable caption track or accessible public transcript was found. Add a source transcript/audio file to enable local transcription in a future step."}
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
            results[video_id] = {"status": "available", "source": "existing_transcript_file",
                                 "file": str(existing), "characters": existing.stat().st_size}
        else:
            results[video_id] = retrieve_video_transcript(youtube, video_id, output_dir)
    available = sum(1 for item in results.values() if item.get("status") == "available")
    return {"videos_checked": len(results), "transcripts_available": available,
            "results": results}
