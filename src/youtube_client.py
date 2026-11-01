"""Read-only OAuth clients for local runs and GitHub Actions."""
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def build_youtube_services(root: Path):
    """Build API clients using Actions secrets, or a local token file.

    GitHub Actions requires YT_CLIENT_ID, YT_CLIENT_SECRET and
    YT_REFRESH_TOKEN repository Actions secrets. No secret is stored in Git.
    """
    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    refresh_token = os.getenv("YT_REFRESH_TOKEN")

    if client_id and client_secret and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
    else:
        secrets_dir = root / ".secrets"
        token_path = secrets_dir / "token.json"
        if not token_path.exists():
            raise RuntimeError(
                "Missing GitHub Actions secrets (YT_CLIENT_ID, "
                "YT_CLIENT_SECRET, YT_REFRESH_TOKEN) or local .secrets/token.json."
            )
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

    if not creds.valid:
        raise RuntimeError("Google OAuth credentials are not valid; re-authorize.")

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return youtube, analytics
