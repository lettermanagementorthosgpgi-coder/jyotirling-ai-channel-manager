"""One-time local OAuth authorization for the Jyotirling AI Channel Manager.

Run locally after downloading the OAuth Desktop client JSON from Google Cloud.
Secrets are written only under .secrets/ (git-ignored).
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / ".secrets"
CLIENT_FILE = SECRETS / "client_secret.json"
TOKEN_FILE = SECRETS / "token.json"
REFRESH_FILE = SECRETS / "refresh_token.txt"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main():
    if not CLIENT_FILE.exists():
        raise SystemExit(
            f"Missing {CLIENT_FILE}. Download the OAuth Desktop app JSON "
            "from Google Cloud Console and save it at this exact path."
        )

    SECRETS.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Open this URL in your browser: {url}",
        success_message="Google authorization completed. You may close this tab.",
    )

    if not credentials.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token. Revoke this app's prior grant "
            "in your Google Account permissions, then run this script again."
        )

    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    REFRESH_FILE.write_text(credentials.refresh_token, encoding="utf-8")
    REFRESH_FILE.chmod(0o600)

    print("Authorization successful.")
    print(f"Local token file: {TOKEN_FILE}")
    print(f"Refresh token file: {REFRESH_FILE}")
    print("Copy the contents of refresh_token.txt into the NEW repository secret "
          "YT_REFRESH_TOKEN. Never paste the token into chat or commit it.")


if __name__ == "__main__":
    main()
