"""Read-only OAuth clients for YouTube APIs."""
import os
from pathlib import Path
from google.auth.transport.requests import Request, AuthorizedSession
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


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
        if creds.expired and creds.refresh_token: creds.refresh(Request())
    if not creds.valid: raise RuntimeError("Google OAuth credentials are not valid; re-authorize.")
    youtube = build("youtube","v3",credentials=creds,cache_discovery=False)
    analytics = build("youtubeAnalytics","v2",credentials=creds,cache_discovery=False)
    reporting = build("youtubereporting","v1",credentials=creds,cache_discovery=False)
    return youtube, analytics, reporting, AuthorizedSession(creds)
