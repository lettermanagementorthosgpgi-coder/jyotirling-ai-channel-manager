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
    """Return unique video IDs in playlist order and describe repeated entries."""
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
                "video_id": video_id, "title": snippet.get("title"),
                "playlist_item_id": item.get("id"),
                "position": snippet.get("position"),
                "published_at": snippet.get("publishedAt"),
            })
            continue
        seen_ids.add(video_id)
        unique_ids.append(video_id)
    return unique_ids, duplicate_entries


def _unique_video_details(video_details: list[dict]) -> tuple[list[dict], list[str]]:
    """Keep one API video resource per exact YouTube video ID."""
    unique_videos, seen_ids, duplicate_ids = [], set(), []
    for video in video_details:
        video_id = video.get("id")
        if not video_id or video_id in seen_ids:
            if video_id:
                duplicate_ids.append(video_id)
            continue
        seen_ids.add(video_id)
        unique_videos.append(video)
    return unique_videos, duplicate_ids


def _query_all_rows(analytics, start_date: str, end_date: str,
                    dimensions: str, metrics: str, sort: str = "-views",
                    page_size: int = 200) -> tuple[list[dict], int]:
    """Fetch all Analytics API pages and return rows as dictionaries."""
    start_index, pages_fetched, headers, output = 1, 0, None, []
    while True:
        response = analytics.reports().query(
            ids="channel==MINE", startDate=start_date, endDate=end_date,
            metrics=metrics, dimensions=dimensions, sort=sort,
            maxResults=page_size, startIndex=start_index,
        ).execute()
        pages_fetched += 1
        if headers is None:
            headers = [h.get("name") for h in response.get("columnHeaders", [])]
        rows = response.get("rows", [])
        output.extend(dict(zip(headers, row)) for row in rows)
        if len(rows) < page_size:
            break
        start_index += len(rows)
    return output, pages_fetched


def _analytics_by_video(analytics, start_date: str, end_date: str) -> dict:
    """Fetch all available per-video aggregate Analytics rows."""
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "likes,comments,shares,subscribersGained,subscribersLost,"
        "impressions,impressionClickThroughRate"
    )
    try:
        rows, pages = _query_all_rows(
            analytics, start_date, end_date, "video", metrics
        )
        by_video = {}
        for record in rows:
            video_id = record.pop("video", None)
            if video_id:
                by_video[video_id] = record
        return {
            "available": True, "by_video": by_video,
            "pages_fetched": pages, "videos_with_analytics": len(by_video),
        }
    except Exception as exc:
        return {
            "available": False, "reason": str(exc), "by_video": {},
            "pages_fetched": 0, "videos_with_analytics": 0,
        }


def _daily_analytics_by_video(analytics, start_date: str, end_date: str) -> dict:
    """Fetch daily video metrics so changes can be compared by date."""
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "likes,comments,shares,subscribersGained,impressions,"
        "impressionClickThroughRate"
    )
    try:
        rows, pages = _query_all_rows(
            analytics, start_date, end_date, "video,day", metrics
        )
        by_video = {}
        for record in rows:
            video_id = record.pop("video", None)
            day = record.pop("day", None)
            if video_id and day:
                by_video.setdefault(video_id, []).append({"date": day, **record})
        return {
            "available": True, "by_video": by_video,
            "pages_fetched": pages,
            "daily_rows": sum(len(items) for items in by_video.values()),
        }
    except Exception as exc:
        return {
            "available": False, "reason": str(exc), "by_video": {},
            "pages_fetched": 0, "daily_rows": 0,
        }


def run_channel_audit(youtube, analytics, max_videos: int = 5000,
                      include_unlisted: bool = False,
                      daily_analytics_days: int = 30) -> dict:
    channel_response = youtube.channels().list(
        part="snippet,contentDetails,statistics", mine=True,
    ).execute()
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel was returned for the authorized account.")

    channel = channels[0]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    playlist_items = _paged_request(
        youtube.playlistItems(), "list", part="snippet,contentDetails",
        playlistId=uploads_playlist, maxResults=50,
    )[:max_videos]
    ids, duplicate_playlist_entries = _unique_playlist_video_ids(playlist_items)

    video_details = []
    for offset in range(0, len(ids), 50):
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(ids[offset:offset + 50]), maxResults=50,
        ).execute()
        video_details.extend(response.get("items", []))
    video_details, duplicate_video_resource_ids = _unique_video_details(video_details)

    today = date.today()
    start = today - timedelta(days=90)
    analytics_result = _analytics_by_video(analytics, start.isoformat(), today.isoformat())
    daily_start = today - timedelta(days=daily_analytics_days)
    daily_result = _daily_analytics_by_video(
        analytics, daily_start.isoformat(), today.isoformat()
    )
    analytics_map = analytics_result["by_video"]
    daily_map = daily_result["by_video"]

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
        thumbnails = snippet.get("thumbnails", {})
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "privacy_status": privacy,
            "duration": content.get("duration"),
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId"),
            "default_language": snippet.get("defaultLanguage"),
            "default_audio_language": snippet.get("defaultAudioLanguage"),
            "thumbnail_urls": {
                key: value.get("url")
                for key, value in thumbnails.items() if value.get("url")
            },
            "lifetime_statistics": {
                key: stats.get(key)
                for key in ("viewCount", "likeCount", "commentCount")
            },
            "last_90_days_analytics": analytics_map.get(video_id),
            "daily_analytics": daily_map.get(video_id, []),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return {
        "report_type": "read_only_channel_audit",
        "report_schema_version": 3,
        "period": {"start": start.isoformat(), "end": today.isoformat()},
        "daily_analytics_period": {
            "start": daily_start.isoformat(), "end": today.isoformat(),
            "days_requested": daily_analytics_days,
        },
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
        "daily_analytics_available": daily_result["available"],
        "daily_analytics_note": daily_result.get("reason"),
        "daily_analytics_pages_fetched": daily_result["pages_fetched"],
        "daily_analytics_rows": daily_result["daily_rows"],
        "playlist_items_scanned": len(playlist_items),
        "unique_video_ids": len(ids),
        "inventory_video_count": len(videos),
        "duplicate_uploads_playlist_entry_count": len(duplicate_playlist_entries),
        "duplicate_uploads_playlist_entries": duplicate_playlist_entries,
        "duplicate_uploads_playlist_entries_note": (
            "Repeated references in the channel uploads playlist. They are not "
            "additional uploaded videos and must not be treated as videos to delete."
        ),
        "duplicate_playlist_entries_count": len(duplicate_playlist_entries),
        "duplicate_playlist_entries": duplicate_playlist_entries,
        "duplicate_video_resource_ids_suppressed": duplicate_video_resource_ids,
        "videos": videos,
        "safety": {
            "read_only": True, "channel_changes_made": False, "uploads_made": False,
        },
    }
