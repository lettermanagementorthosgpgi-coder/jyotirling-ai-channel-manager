"""Read-only channel inventory and analytics collection."""
from __future__ import annotations

from datetime import date, timedelta


def _paged_request(service, method: str, **kwargs):
    items = []
    token = None
    while True:
        response = getattr(service, method)(**kwargs, pageToken=token).execute()
        items.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            break
    return items


def _unique_playlist_video_ids(playlist_items: list[dict]) -> tuple[list[str], list[dict]]:
    """Return unique video IDs in playlist order and describe repeated entries.

    Titles are deliberately not used as identifiers: two videos with the same
    title but different YouTube video IDs remain separate inventory records.
    """
    unique_ids = []
    seen_ids = set()
    duplicate_entries = []

    for item in playlist_items:
        video_id = item.get("contentDetails", {}).get("videoId")
        if not video_id:
            continue
        if video_id in seen_ids:
            snippet = item.get("snippet", {})
            duplicate_entries.append({
                "video_id": video_id,
                "title": snippet.get("title"),
                "playlist_item_id": item.get("id"),
                "position": snippet.get("position"),
                "published_at": snippet.get("publishedAt"),
            })
            continue
        seen_ids.add(video_id)
        unique_ids.append(video_id)

    return unique_ids, duplicate_entries


def _unique_video_details(video_details: list[dict]) -> tuple[list[dict], list[str]]:
    """Keep one API video resource per exact YouTube video ID.

    Repeated playlist-item references are diagnostics, not extra uploaded
    videos. This second guard also prevents duplicate inventory rows if an API
    response or a future code path supplies repeated video resources.
    """
    unique_videos = []
    seen_ids = set()
    duplicate_ids = []
    for video in video_details:
        video_id = video.get("id")
        if not video_id or video_id in seen_ids:
            if video_id:
                duplicate_ids.append(video_id)
            continue
        seen_ids.add(video_id)
        unique_videos.append(video)
    return unique_videos, duplicate_ids


def _analytics_by_video(analytics, start_date: str, end_date: str) -> dict:
    """Fetch every available per-video Analytics row, not just the first 200."""
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "likes,comments,shares,subscribersGained,subscribersLost"
    )
    page_size = 200
    start_index = 1
    pages_fetched = 0
    headers = None
    by_video = {}

    try:
        while True:
            response = analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics=metrics,
                dimensions="video",
                sort="-views",
                maxResults=page_size,
                startIndex=start_index,
            ).execute()
            pages_fetched += 1

            if headers is None:
                headers = [
                    header.get("name")
                    for header in response.get("columnHeaders", [])
                ]

            rows = response.get("rows", [])
            for row in rows:
                record = dict(zip(headers, row))
                video_id = record.pop("video", None)
                if video_id:
                    by_video[video_id] = record

            # Analytics API uses one-based startIndex pagination. A short page
            # means there are no more rows; an exact 200-row page is followed
            # by another request to check for remaining results.
            if len(rows) < page_size:
                break
            start_index += len(rows)

    except Exception as exc:
        # Do not present an incomplete multi-page result as a complete report.
        return {
            "available": False,
            "reason": str(exc),
            "by_video": {},
            "pages_fetched": pages_fetched,
            "videos_with_analytics": 0,
        }

    return {
        "available": True,
        "by_video": by_video,
        "pages_fetched": pages_fetched,
        "videos_with_analytics": len(by_video),
    }


def run_channel_audit(youtube, analytics, max_videos: int = 5000,
                      include_unlisted: bool = False) -> dict:
    channel_response = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True,
    ).execute()
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel was returned for the authorized account.")

    channel = channels[0]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    playlist_items = _paged_request(
        youtube.playlistItems(),
        "list",
        part="snippet,contentDetails",
        playlistId=uploads_playlist,
        maxResults=50,
    )[:max_videos]

    ids, duplicate_playlist_entries = _unique_playlist_video_ids(playlist_items)

    video_details = []
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(batch),
            maxResults=50,
        ).execute()
        video_details.extend(response.get("items", []))

    # Defensive de-duplication at the final inventory boundary. Playlist item
    # IDs and video IDs are different concepts; only video IDs define videos.
    video_details, duplicate_video_resource_ids = _unique_video_details(video_details)

    today = date.today()
    start = today - timedelta(days=90)
    analytics_result = _analytics_by_video(
        analytics, start.isoformat(), today.isoformat()
    )
    analytics_map = analytics_result["by_video"]

    videos = []
    for video in video_details:
        status = video.get("status", {})
        privacy = status.get("privacyStatus", "unknown")
        if privacy != "public" and not include_unlisted:
            continue
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        content = video.get("contentDetails", {})
        video_id = video.get("id")
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "privacy_status": privacy,
            "duration": content.get("duration"),
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId"),
            "lifetime_statistics": {
                key: stats.get(key)
                for key in ("viewCount", "likeCount", "commentCount")
            },
            "last_90_days_analytics": analytics_map.get(video_id),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return {
        "report_type": "read_only_channel_audit",
        "report_schema_version": 2,
        "period": {"start": start.isoformat(), "end": today.isoformat()},
        "channel": {
            "id": channel.get("id"),
            "title": channel.get("snippet", {}).get("title"),
            "custom_url": channel.get("snippet", {}).get("customUrl"),
            "statistics": channel.get("statistics", {}),
        },
        "analytics_available": analytics_result["available"],
        "analytics_note": analytics_result.get("reason"),
        "analytics_pages_fetched": analytics_result["pages_fetched"],
        "videos_with_90_day_analytics": analytics_result["videos_with_analytics"],
        "playlist_items_scanned": len(playlist_items),
        "unique_video_ids": len(videos),
        "inventory_video_count": len(videos),
        # These count repeated playlist-item references, not duplicate videos.
        "duplicate_uploads_playlist_entry_count": len(duplicate_playlist_entries),
        "duplicate_uploads_playlist_entries": duplicate_playlist_entries,
        "duplicate_uploads_playlist_entries_note": (
            "Repeated references in the channel uploads playlist. They are not "
            "additional uploaded videos and must not be treated as videos to delete."
        ),
        # Retain legacy field names for consumers of earlier report versions.
        "duplicate_playlist_entries_count": len(duplicate_playlist_entries),
        "duplicate_playlist_entries": duplicate_playlist_entries,
        "duplicate_video_resource_ids_suppressed": duplicate_video_resource_ids,
        "videos": videos,
        "safety": {
            "read_only": True,
            "channel_changes_made": False,
            "uploads_made": False,
        },
    }
