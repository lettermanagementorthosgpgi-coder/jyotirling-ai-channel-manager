# Jyotirling AI Channel Manager

A separate, approval-first toolkit for auditing and improving the **JYOTIRLING SHIVMATH BARAULI LUCKNOW** YouTube channel.

## Safety by design

- Phase 1 is **read-only**: it lists channel videos and gathers available analytics.
- It does not edit titles, descriptions, tags, thumbnails, playlists, or publish videos/Shorts.
- Any future write/publish capability must require a separate explicit approval step.
- Never commit OAuth tokens, client secrets, API keys, or downloaded private media.

## Phase 1: channel audit

### Requirements
- Python 3.10+
- YouTube Data API v3 enabled in a Google Cloud project
- YouTube Analytics API enabled in the same project
- OAuth Desktop App credentials saved locally as `client_secret.json`

### Setup
1. Create a Google Cloud project and enable YouTube Data API v3 and YouTube Analytics API.
2. Create OAuth credentials of type **Desktop app** and download the JSON file.
3. Save it locally as `client_secret.json` in this project folder. Do not upload it to GitHub.
4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Run:

   ```bash
   python main.py
   ```

On first run, a browser window will ask you to authorize read-only access to your YouTube channel. The local token is stored in `.secrets/token.json` and is excluded from Git.

## Reports

The audit creates timestamped CSV/JSON reports in `reports/`:
- Channel video inventory
- Available per-video performance metrics
- Basic attention flags for videos with impressions but low click-through rate, or views/watch-time patterns that merit review

Metrics availability depends on YouTube Analytics API permissions and reporting latency. The tool does not claim that a metric is available when the API does not return it.

## Roadmap

1. Read-only channel inventory and analytics audit
2. AI-assisted SEO/title/thumbnail recommendations (approval required)
3. Long-form video transcript analysis and 5–10 candidate Shorts per eligible video
4. Short-form rendering, review queue, and publication only after explicit approval

The existing `jyotirlingshivmathlive` scheduler is a separate project and must remain untouched.
