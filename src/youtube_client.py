"""YouTube API clients plus an explicitly gated, reversible-in-effect write smoke test."""
import os
from pathlib import Path
from google.auth.transport.requests import Request, AuthorizedSession
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def build_youtube_services(root: Path):
    client_id, client_secret, refresh_token = (
        os.getenv("YT_CLIENT_ID"), os.getenv("YT_CLIENT_SECRET"), os.getenv("YT_REFRESH_TOKEN"))
    if client_id and client_secret and refresh_token:
        creds = Credentials(token=None, refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token", client_id=client_id,
            client_secret=client_secret, scopes=SCOPES)
        creds.refresh(Request())
    else:
        token_path = root / ".secrets" / "token.json"
        if not token_path.exists():
            raise RuntimeError("Missing GitHub Actions OAuth secrets or local .secrets/token.json.")
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("Google OAuth credentials are not valid; check the configured YouTube grant.")
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    reporting = build("youtubereporting", "v1", credentials=creds, cache_discovery=False)
    return youtube, analytics, reporting, AuthorizedSession(creds)


def run_write_permission_smoke_test(youtube, video_id):
    """Write the selected public video's existing snippet unchanged, then verify it."""
    response = youtube.videos().list(
        part="snippet,status", id=video_id, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"Video {video_id} was not returned by YouTube.")
    video = items[0]
    if video.get("status", {}).get("privacyStatus") != "public":
        raise RuntimeError("Safety stop: the selected test video is not public.")
    old = video.get("snippet", {})
    required = ("title", "description", "categoryId")
    missing = [key for key in required if old.get(key) is None]
    if missing:
        raise RuntimeError("Safety stop: video snippet is missing required fields: " + ", ".join(missing))
    snippet = {key: old[key] for key in
               ("title", "description", "categoryId", "tags",
                "defaultLanguage", "defaultAudioLanguage") if key in old}
    updated = youtube.videos().update(
        part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    check = youtube.videos().list(
        part="snippet,status", id=video_id, maxResults=1).execute().get("items", [])
    if not check:
        raise RuntimeError("Write request returned, but the verification read-back found no video.")
    after = check[0].get("snippet", {})
    unchanged = all(after.get(key) == old.get(key) for key in
                    ("title", "description", "categoryId", "tags",
                     "defaultLanguage", "defaultAudioLanguage"))
    if not unchanged:
        raise RuntimeError("YouTube accepted the write request, but read-back metadata differs; inspect immediately.")
    return {
        "status": "write_succeeded_and_verified_unchanged",
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": old["title"],
        "updated_video_id": updated.get("id"),
        "metadata_unchanged_after_readback": True,
        "fields_submitted": list(snippet.keys()),
        "note": "A YouTube videos.update request succeeded; the same existing snippet was written and read back unchanged."
    }
