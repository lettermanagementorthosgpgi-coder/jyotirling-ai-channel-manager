"""OAuth clients with read-only scopes only."""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def build_youtube_services(root: Path):
    secrets_dir = root / ".secrets"
    secrets_dir.mkdir(exist_ok=True)
    token_path = secrets_dir / "token.json"
    client_secret = root / "client_secret.json"

    if not client_secret.exists():
        raise FileNotFoundError(
            "client_secret.json is missing. Add your Google OAuth Desktop App "
            "credentials locally; never commit this file to GitHub."
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return youtube, analytics
