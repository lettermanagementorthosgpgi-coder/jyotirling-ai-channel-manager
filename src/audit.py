"""Read-only channel inventory, analytics and thumbnail reach collection."""
from __future__ import annotations
import csv, io
from datetime import date, timedelta


def _paged_request(service, method: str, **kwargs):
    items, token = [], None
    while True:
        response = getattr(service, method)(**kwargs, pageToken=token).execute()
        items.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token: break
    return items


def _unique_playlist_video_ids(items):
    ids, seen, duplicates = [], set(), []
    for item in items:
        vid = item.get("contentDetails", {}).get("videoId")
        if not vid: continue
        if vid in seen:
            sn = item.get("snippet", {})
            duplicates.append({"video_id":vid,"title":sn.get("title"),
                "playlist_item_id":item.get("id"),"position":sn.get("position"),
                "published_at":sn.get("publishedAt")})
        else:
            seen.add(vid); ids.append(vid)
    return ids, duplicates


def _unique_video_details(items):
    out, seen, duplicates = [], set(), []
    for video in items:
        vid = video.get("id")
        if not vid or vid in seen:
            if vid: duplicates.append(vid)
        else:
            seen.add(vid); out.append(video)
    return out, duplicates


def _query_all_rows(analytics, start, end, dimensions, metrics, sort="-views", page_size=200):
    rows_out, page, headers, pages = [], 1, None, 0
    while True:
        result = analytics.reports().query(ids="channel==MINE", startDate=start,
            endDate=end, metrics=metrics, dimensions=dimensions, sort=sort,
            maxResults=page_size, startIndex=page).execute()
        pages += 1
        if headers is None: headers = [h.get("name") for h in result.get("columnHeaders", [])]
        rows = result.get("rows", [])
        rows_out.extend(dict(zip(headers, row)) for row in rows)
        if len(rows) < page_size: break
        page += len(rows)
    return rows_out, pages


def _analytics_by_video(analytics, start, end):
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
               "likes,comments,shares,subscribersGained,subscribersLost")
    try:
        rows, pages = _query_all_rows(analytics, start, end, "video", metrics)
        data = {}
        for row in rows:
            vid = row.pop("video", None)
            if vid: data[vid] = row
        return {"available":True,"by_video":data,"pages_fetched":pages,
                "videos_with_analytics":len(data)}
    except Exception as exc:
        return {"available":False,"reason":str(exc),"by_video":{},
                "pages_fetched":0,"videos_with_analytics":0}


def _daily_analytics_by_video(analytics, start, end):
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
               "likes,comments,shares,subscribersGained")
    try:
        rows, pages = _query_all_rows(analytics, start, end, "video,day", metrics)
        data = {}
        for row in rows:
            vid, day = row.pop("video", None), row.pop("day", None)
            if vid and day: data.setdefault(vid, []).append({"date":day, **row})
        return {"available":True,"by_video":data,"pages_fetched":pages,
                "daily_rows":sum(len(v) for v in data.values())}
    except Exception as exc:
        return {"available":False,"reason":str(exc),"by_video":{},
                "pages_fetched":0,"daily_rows":0}


def _number(value):
    try:
        n = float(value)
        return int(n) if n.is_integer() else n
    except (TypeError, ValueError):
        return None


def _parse_reach_csv(csv_text, start_date):
    data = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        day, vid = row.get("date"), row.get("video_id")
        if day and vid and day >= start_date:
            data.setdefault(vid, []).append({"date":day,
                "thumbnail_impressions":_number(row.get("video_thumbnail_impressions")),
                "thumbnail_impressions_ctr":_number(row.get("video_thumbnail_impressions_ctr"))})
    return data


def _daily_thumbnail_reach(reporting, session, start_date):
    if reporting is None or session is None:
        return {"available":False,"reason":"Reporting API client unavailable.",
                "by_video":{},"reports_read":0,"job_created":False}
    try:
        jobs = _paged_request(reporting.jobs(), "list")
        job = next((j for j in jobs if j.get("reportTypeId")=="channel_reach_basic_a1"), None)
        created = False
        if job is None:
            job = reporting.jobs().create(body={"reportTypeId":"channel_reach_basic_a1",
                "name":"Jyotirling Shivmath daily thumbnail reach"}).execute()
            created = True
        reports = _paged_request(reporting.jobs(), "reports", jobId=job["id"])
        data, count = {}, 0
        for report in reports:
            url = report.get("downloadUrl")
            if not url: continue
            response = session.get(url); response.raise_for_status()
            parsed = _parse_reach_csv(response.text, start_date)
            for vid, rows in parsed.items(): data.setdefault(vid, []).extend(rows)
            count += 1
        for rows in data.values(): rows.sort(key=lambda r:r["date"])
        return {"available":True,"by_video":data,"reports_read":count,
                "job_created":created,"report_type_id":"channel_reach_basic_a1"}
    except Exception as exc:
        return {"available":False,"reason":str(exc),"by_video":{},
                "reports_read":0,"job_created":False}


def run_channel_audit(youtube, analytics, max_videos=5000, include_unlisted=False,
                      daily_analytics_days=30, reporting=None, reporting_session=None):
    channel_response = youtube.channels().list(
        part="snippet,contentDetails,statistics", mine=True).execute()
    channels = channel_response.get("items", [])
    if not channels: raise RuntimeError("No YouTube channel was returned for the authorized account.")
    channel = channels[0]
    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    playlist_items = _paged_request(youtube.playlistItems(), "list",
        part="snippet,contentDetails", playlistId=playlist, maxResults=50)[:max_videos]
    ids, duplicate_entries = _unique_playlist_video_ids(playlist_items)
    details = []
    for offset in range(0, len(ids), 50):
        result = youtube.videos().list(part="snippet,contentDetails,statistics,status",
            id=",".join(ids[offset:offset+50]), maxResults=50).execute()
        details.extend(result.get("items", []))
    details, duplicate_resources = _unique_video_details(details)

    today = date.today()
    start = today - timedelta(days=90)
    aggregate = _analytics_by_video(analytics, start.isoformat(), today.isoformat())
    daily_start = today - timedelta(days=daily_analytics_days)
    daily = _daily_analytics_by_video(analytics, daily_start.isoformat(), today.isoformat())
    reach = _daily_thumbnail_reach(reporting, reporting_session, daily_start.isoformat())

    videos = []
    for video in details:
        privacy = video.get("status", {}).get("privacyStatus", "unknown")
        if privacy != "public" and not include_unlisted: continue
        sn, stats = video.get("snippet", {}), video.get("statistics", {})
        content, vid = video.get("contentDetails", {}), video.get("id")
        thumbs = sn.get("thumbnails", {})
        daily_map = {r["date"]:r for r in daily["by_video"].get(vid, [])}
        for r in reach["by_video"].get(vid, []):
            daily_map.setdefault(r["date"], {"date":r["date"]}).update(
                {k:v for k,v in r.items() if k!="date"})
        videos.append({"video_id":vid,"title":sn.get("title"),
            "description":sn.get("description"),"published_at":sn.get("publishedAt"),
            "privacy_status":privacy,"duration":content.get("duration"),
            "tags":sn.get("tags",[]),"category_id":sn.get("categoryId"),
            "default_language":sn.get("defaultLanguage"),
            "default_audio_language":sn.get("defaultAudioLanguage"),
            "thumbnail_urls":{k:v.get("url") for k,v in thumbs.items() if v.get("url")},
            "lifetime_statistics":{k:stats.get(k) for k in ("viewCount","likeCount","commentCount")},
            "last_90_days_analytics":aggregate["by_video"].get(vid),
            "daily_analytics":[daily_map[k] for k in sorted(daily_map)],
            "url":f"https://www.youtube.com/watch?v={vid}"})
    return {"report_type":"read_only_channel_audit","report_schema_version":4,
        "period":{"start":start.isoformat(),"end":today.isoformat()},
        "daily_analytics_period":{"start":daily_start.isoformat(),"end":today.isoformat(),
            "days_requested":daily_analytics_days},
        "channel":{"id":channel.get("id"),"title":channel.get("snippet",{}).get("title"),
            "custom_url":channel.get("snippet",{}).get("customUrl"),
            "statistics":channel.get("statistics",{})},
        "analytics_available":aggregate["available"],"analytics_note":aggregate.get("reason"),
        "analytics_pages_fetched":aggregate["pages_fetched"],
        "videos_with_90_day_analytics":aggregate["videos_with_analytics"],
        "daily_analytics_available":daily["available"],"daily_analytics_note":daily.get("reason"),
        "daily_analytics_pages_fetched":daily["pages_fetched"],"daily_analytics_rows":daily["daily_rows"],
        "thumbnail_reach_available":reach["available"],"thumbnail_reach_note":reach.get("reason"),
        "thumbnail_reach_reports_read":reach["reports_read"],
        "thumbnail_reach_job_created":reach["job_created"],
        "thumbnail_reach_report_type_id":reach.get("report_type_id"),
        "playlist_items_scanned":len(playlist_items),"unique_video_ids":len(ids),
        "inventory_video_count":len(videos),
        "duplicate_uploads_playlist_entry_count":len(duplicate_entries),
        "duplicate_uploads_playlist_entries":duplicate_entries,
        "duplicate_uploads_playlist_entries_note":"Repeated uploads-playlist references are not additional videos.",
        "duplicate_playlist_entries_count":len(duplicate_entries),
        "duplicate_playlist_entries":duplicate_entries,
        "duplicate_video_resource_ids_suppressed":duplicate_resources,"videos":videos,
        "safety":{"read_only":True,"channel_changes_made":False,"uploads_made":False}}
