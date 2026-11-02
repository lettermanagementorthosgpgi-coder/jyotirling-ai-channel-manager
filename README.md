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

The inventory reads up to `audit.max_videos_per_run` uploads (currently 5,000) by paging through the channel's uploads playlist. Per-video lifetime view/like/comment counts are included where the Data API returns them.

Per-video YouTube Analytics for the trailing 90-day reporting window is also paginated in batches of 200 rows until all available rows have been retrieved. The report records the number of Analytics pages fetched and the number of videos with Analytics rows. YouTube Analytics may omit videos with no reportable activity in that date range; therefore, a missing 90-day Analytics entry does not mean the video is absent from the inventory. Analytics availability also depends on API permissions and reporting latency.

This is still a read-only audit. No YouTube channel metadata, videos, thumbnails, playlists, or publishing settings are changed.


## New-upload preparation queue (from 2 November 2026)

- The audit runs hourly and includes every public upload published on or after **2 November 2026 (Asia/Kolkata)**, irrespective of topic.
- The existing historical review remains separately scoped to the selected 14 Bhagavad Gita videos; the new-upload queue is not limited to those chapters.
- Each new upload receives a preparation record with source metadata, thumbnail URLs, transcript-retrieval status, required SEO/thumbnail deliverables, and the AI-1 → AI-2 → AI-3 review rotation/handoff ledger.
- The queue is a discovery and handoff record, not a claim that three external AI services have already processed the video. AI provider connections and transcript access must be configured before unattended AI drafting can run.
- The workflow remains read-only: it does not alter titles, descriptions, tags, thumbnails, or publish anything. All implementation remains pending the user's explicit approval.
- The report's queue is regenerated from the channel inventory each run, so videos uploaded earlier on the start date are still included in later runs.


## Three-provider AI preparation

The hourly workflow can call three model APIs from the server side:

- AI-1 data analysis: OpenAI API (default model: `gpt-6-luna`)
- AI-2 YouTube SEO drafting: Google Gemini API (default model: `gemini-3.8-flash`)
- AI-3 independent review: Anthropic Claude API (default model: `claude-sonnet-5-5`)

Each role has a fallback rotation through the other configured providers if its preferred provider fails. Successful stages are saved in a SQLite preparation ledger, cached between scheduled workflow runs, and resumed rather than needlessly repeated. If no key is configured, the item remains blocked/pending; it is never marked complete.

### Required provider secrets

Add whichever provider keys you want to use under **Settings → Secrets and variables → Actions → New repository secret**:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`

You can configure one, two, or all three. For the full three-AI review and fallback rotation, configure all three. Each API is billed by its provider according to the account's plan and usage; this repository does not include API credits. Never paste keys into chat, source code, issues, or commits.

### Transcript grounding

If a verified transcript is available, place it in `transcripts/<VIDEO_ID>.txt` in the runner's workspace before processing. When no transcript is available, the AI must mark its package as **metadata-only / provisional** and must not invent what was spoken. The current audit does not have permission to download captions automatically. Transcript access is a separate integration requirement.

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

## Roadmap

1. Read-only channel inventory and paginated analytics audit
2. AI-assisted SEO/title/thumbnail recommendations (approval required)
3. Long-form transcript analysis and the approved Shorts Manager described above
4. Short-form rendering, individual approval queue, and upload/publication only after explicit approval

The existing `jyotirlingshivmathlive` scheduler is a separate project and must remain untouched.
