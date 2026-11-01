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


def _analytics_by_video(analytics, start_date: str, end_date: str) -> dict:
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "likes,comments,shares,subscribersGained,subscribersLost"
    )
    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=metrics,
            dimensions="video",
            sort="-views",
            maxResults=200,
        ).execute()
    except Exception as exc:
        return {"available": False, "reason": str(exc), "by_video": {}}

    headers = [h.get("name") for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])
    by_video = {}
    for row in rows:
        record = dict(zip(headers, row))
        video_id = record.pop("video", None)
        if video_id:
            by_video[video_id] = record
    return {"available": True, "by_video": by_video}


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

    ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in playlist_items
        if item.get("contentDetails", {}).get("videoId")
    ]

    video_details = []
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(batch),
            maxResults=50,
        ).execute()
        video_details.extend(response.get("items", []))

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
        "period": {"start": start.isoformat(), "end": today.isoformat()},
        "channel": {
            "id": channel.get("id"),
            "title": channel.get("snippet", {}).get("title"),
            "custom_url": channel.get("snippet", {}).get("customUrl"),
            "statistics": channel.get("statistics", {}),
        },
        "analytics_available": analytics_result["available"],
        "analytics_note": analytics_result.get("reason"),
        "videos": videos,
        "safety": {
            "read_only": True,
            "channel_changes_made": False,
            "uploads_made": False,
        },
    }
