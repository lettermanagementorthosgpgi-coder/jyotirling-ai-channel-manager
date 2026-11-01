# Jyotirling AI Channel Manager

A separate, approval-first toolkit for auditing and improving the **JYOTIRLING SHIVMATH BARAULI LUCKNOW** YouTube channel.

## Safety by design

- Phase 1 is **read-only**: it lists channel videos and gathers available analytics.
- It does not edit titles, descriptions, tags, thumbnails, playlists, or publish videos/Shorts.
- Any future write/publish capability must require a separate explicit approval step.
- Never commit OAuth tokens, client secrets, API keys, or downloaded private media.
- GitHub Actions secrets are used for unattended read-only authentication.

## Phase 1: GitHub Actions audit

The workflow is in `.github/workflows/channel-audit.yml`. It can be started manually from **Actions → Read-only YouTube channel audit → Run workflow**, and is scheduled daily at 10:00 AM India time.

### Required repository Actions secrets

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`

Never put these values in repository files, commits, workflow YAML, issues, or chat messages.

The OAuth app must have YouTube Data API v3 and YouTube Analytics API enabled, with read-only scopes:
- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`

A one-time Google authorization is needed to obtain the refresh token. Do not create or paste a token into a tracked file.

## Reports

Each successful run creates a JSON audit report and stores it as a downloadable GitHub Actions artifact named `jyotirling-channel-audit` (retained for 30 days).

The report includes channel video inventory and available per-video lifetime statistics and last-90-days analytics. Metrics availability depends on YouTube Analytics API permissions and reporting latency.

## Roadmap

1. Read-only channel inventory and analytics audit
2. AI-assisted SEO/title/thumbnail recommendations (approval required)
3. Long-form video transcript analysis and 5–10 candidate Shorts per eligible video
4. Short-form rendering, review queue, and publication only after explicit approval

The existing `jyotirlingshivmathlive` scheduler is a separate project and must remain untouched.
