# Jyotirling AI Channel Manager

A separate, approval-first toolkit for auditing and improving the **JYOTIRLING SHIVMATH BARAULI LUCKNOW** YouTube channel.

## Safety by design

- Phase 1 is **read-only**: it lists channel videos and gathers available analytics.
- It does not edit titles, descriptions, tags, thumbnails, playlists, or publish videos/Shorts.
- Any future write/publish capability must require a separate explicit approval step.
- Never commit OAuth tokens, client secrets, API keys, or downloaded private media.
- GitHub Actions secrets are used for unattended read-only authentication.

## Phase 1: GitHub Actions audit

The workflow is in `.github/workflows/channel-audit.yml`. It can be started manually from **Actions → Read-only YouTube channel audit → Run workflow**, and is scheduled hourly (once per hour).

### Required repository Actions secrets

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`

Never put these values in repository files, commits, workflow YAML, issues, or chat messages.

The OAuth app must have YouTube Data API v3 and YouTube Analytics API enabled, with read-only scopes:
- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`
- `https://www.googleapis.com/auth/youtube.force-ssl` (required for caption-track listing and download)

A one-time Google authorization is needed to obtain the refresh token. Do not create or paste a token into a tracked file.

## Reports

Each successful run creates a JSON audit report and stores it as a downloadable GitHub Actions artifact named `jyotirling-channel-audit` (retained for 30 days).

The inventory reads up to `audit.max_videos_per_run` uploads (currently 5,000) by paging through the channel's uploads playlist. Per-video lifetime view/like/comment counts are included where the Data API returns them.

Per-video YouTube Analytics for the trailing 90-day reporting window is also paginated in batches of 200 rows until all available rows have been retrieved. The report records the number of Analytics pages fetched and the number of videos with Analytics rows. YouTube Analytics may omit videos with no reportable activity in that date range; therefore, a missing 90-day Analytics entry does not mean the video is absent from the inventory. Analytics availability also depends on API permissions and reporting latency.

This is still a read-only audit. No YouTube channel metadata, videos, thumbnails, playlists, or publishing settings are changed.


## New-upload preparation queue (from 2 November 2026)

- The audit runs hourly and includes every public upload published on or after **2 November 2026 (Asia/Kolkata)**, irrespective of topic.
- The existing historical review remains separately scoped to the selected 14 Bhagavad Gita videos; the new-upload queue is not limited to those chapters.
- Each new upload receives a preparation record with source metadata, thumbnail URLs, transcript-retrieval status, required SEO/thumbnail deliverables, and the OpenAI → Gemini → independent cross-review handoff ledger.
- The queue is a discovery and handoff record. OpenAI and Gemini provider keys must be configured before unattended AI drafting can run.
- The workflow remains read-only: it does not alter titles, descriptions, tags, thumbnails, or publish anything. All implementation remains pending the user's explicit approval.
- The report's queue is regenerated from the channel inventory each run, so videos uploaded earlier on the start date are still included in later runs.


## Two-provider AI preparation and thumbnail creation

The hourly workflow uses only the two API providers configured by the user:

- AI-1 analysis: OpenAI API (default text model: `gpt-6-luna`)
- AI-2 SEO and thumbnail brief: Google Gemini API (default text model: `gemini-3.8-flash`)
- AI-3 independent cross-review: the other configured provider, preferring OpenAI after Gemini and Gemini after OpenAI. If only one key is available, that provider can complete the stages.
- Thumbnail artwork: OpenAI Images API (default: `gpt-image-2.5-flare`) with Gemini image generation fallback (default: `gemini-3.1-flash-image`).

If a provider fails, the other configured provider is tried. Completed text stages are saved in SQLite and resumed on later runs. Image generation also falls back between OpenAI and Gemini. API image generation can incur separate usage charges.

### Required provider secrets

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

No Anthropic/Claude key is required or used by this workflow. Never paste keys into chat, source code, issues, or commits.

### Thumbnail branding asset

The master thumbnail `karmsanyasyog.jpeg` is bundled inside this repository at `assets/karmsanyasyog.jpeg`, copied from the existing `jyotirlingshivmathlive` repository. The composer follows the legacy `live_scheduler.py` layout: it preserves the master portrait, fixed header, author plaque and frame; Bhagavad Gita retains the master Krishna-Arjuna artwork, while Shiv Puran replaces only the original story-art window and updates the episode hook, chapter plaque and footer. No runtime dependency on the other repository and no separate author-photo upload are required. Generated thumbnails are saved as workflow artifacts for review; nothing is uploaded to or changed on YouTube automatically.

### Transcript grounding

If a verified transcript is available, place it in `transcripts/<VIDEO_ID>.txt` in the runner's workspace before processing. When no transcript is available, the AI must mark its package as **metadata-only / provisional** and must not invent what was spoken. The hourly workflow now attempts transcript retrieval automatically. It first tries the public `youtube-transcript-api` route, which does not consume YouTube Data API quota. If that fails, it checks the official YouTube captions API no more than once per 24 hours per video. This throttle is important because Google's current quota table assigns 50 units to `captions.list` and 200 units to `captions.download`; repeating those requests hourly can consume quota rapidly. Public transcript discovery is still retried on each scheduled run. The official route requires the `youtube.force-ssl` OAuth scope and the authenticated account must have edit permission on the video. If neither route works, the report records each retrieval error and the AI remains metadata-only / provisional. To activate the official route, re-authorize the Google OAuth app and replace `YT_REFRESH_TOKEN` in GitHub Actions secrets with a token granted the new scope. Existing local `.secrets/token.json` must also be re-authorized. No video/audio is downloaded and no YouTube content is changed.

AI outputs are drafts for the user's review. No title, description, tag, thumbnail, upload, or publication is changed automatically.

## Approved Shorts Manager requirements

The planned Shorts Manager must:

- Inspect both existing/older channel uploads and newly uploaded videos.
- Select every eligible long-form video whose duration is **greater than 10 minutes**.
- Prepare **5–10 candidate Shorts per eligible source video**, subject to meaningful content and source length; never pad clips with repetitive or low-value material just to hit a quota.
- Use **mixed clip durations**, choosing the length that best preserves the teaching, story, shloka, or devotional moment. Produce vertical 9:16 edits with readable Hindi captions and suitable opening hooks.
- Prepare an individual review item for every Short, including source-video link and timecodes, rendered preview, proposed title, description, hashtags, and any rights/content checks.
- Require the user's explicit approval for **each individual Short** before uploading and publishing it to YouTube. No automatic upload or publication is permitted.
- Track each candidate's state (for example: Draft, Pending Approval, Approved, Uploaded/Published, Rejected) and avoid duplicate extraction or repeat publishing.




## Quota-conscious daily scan and performance tracking

- Scheduled runs do not perform a full channel-wide video-details read. After the one-time inventory bootstrap, the cached uploads inventory is checked newest-first and scanning stops at the first known upload. Only videos published in the exact rolling last 48 hours and videos published on the single local date exactly 90 days before today are refreshed from `videos.list`. Manual From/To runs refresh only public videos whose local publication date is within that inclusive range.
- YouTube Analytics queries are server-filtered to the selected video IDs; no channel-wide daily totals or full-channel thumbnail reach report downloads are requested in the scheduled targeted scan.
- Scheduled hourly runs do not upload daily report artifacts. A report artifact is attached only to a manually dispatched run. The local JSON report includes each selected video's performance metrics.
- A SQLite SEO performance baseline helper records lifetime views/likes/comments immediately after a future SEO change is successfully verified. Later targeted reviews can report observed changes from that baseline and subscribers gained since the recorded SEO-change date. It does not attribute growth causally to SEO. Historical SEO changes that have no saved baseline cannot be reconstructed exactly from current counts.
- The repository currently generates review drafts; automatic SEO metadata changes to YouTube are not yet implemented. The baseline helper must be called only after a future write has been verified. Gmail email/PDF delivery is also not implemented yet.

## Manual date-range selection and transcript retry window

- The manual workflow dispatch now accepts inclusive `from_date` and `to_date` inputs in `YYYY-MM-DD` format. When both are supplied, only public uploads whose local publication date falls inside that range are placed in the preparation queue; otherwise the normal new-upload scope is used.
- When a new video has no transcript, AI drafting is held for a full 48 hours instead of immediately using the description. The first-seen time and fallback-eligible time are stored in the persistent SQLite preparation state. Public transcript discovery is retried each hourly run. The current implementation reports that primary-scripture-source lookup is not yet connected; it does not pretend that a scripture source was found. After the 48-hour window, the existing description/title may be used as a clearly labelled fallback.
- Manual date-range selection currently scopes the preparation queue and creates draft recommendations only. Direct YouTube metadata/thumbnail updates and Gmail HTML/PDF reports remain separate implementation tasks; no such changes are performed by this workflow today.

## Quota protection

- The channel inventory is persisted in the GitHub Actions cache. Hourly runs stop scanning the newest-first uploads playlist when they encounter the first already-known video, and fetch full video details only for newly discovered IDs. The first successful run builds the initial inventory; subsequent runs should normally use one uploads-playlist page plus the channel lookup.
- The channel audit no longer runs on every code push. It remains available through manual dispatch and the hourly schedule; the unit-test workflow continues to run on code pushes.
- Transcript retrieval tries the public transcript source first and rate-limits the quota-expensive official captions API to one check per video per 24 hours.

## Roadmap

1. Read-only channel inventory and paginated analytics audit
2. AI-assisted SEO/title/thumbnail recommendations (approval required)
3. Long-form transcript analysis and the approved Shorts Manager described above
4. Short-form rendering, individual approval queue, and upload/publication only after explicit approval

The existing `jyotirlingshivmathlive` scheduler is a separate project and must remain untouched.
