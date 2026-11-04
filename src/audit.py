"""Read-only channel inventory, analytics and thumbnail reach collection."""
from __future__ import annotations
import csv, io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _paged_request(service, method: str, collection_key="items", **kwargs):
    """Read every page from APIs whose collection field may not be named items."""
    items, token = [], None
    while True:
        response = getattr(service, method)(**kwargs, pageToken=token).execute()
        items.extend(response.get(collection_key, []))
        token = response.get("nextPageToken")
        if not token:
            break
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


def _query_all_rows(analytics, start, end, dimensions, metrics, sort="-views", page_size=200, filters=None):
    rows_out, page, headers, pages = [], 1, None, 0
    while True:
        result = analytics.reports().query(ids="channel==MINE", startDate=start,
            endDate=end, metrics=metrics, dimensions=dimensions, sort=sort,
            filters=filters, maxResults=page_size, startIndex=page).execute()
        pages += 1
        if headers is None: headers = [h.get("name") for h in result.get("columnHeaders", [])]
        rows = result.get("rows", [])
        rows_out.extend(dict(zip(headers, row)) for row in rows)
        if len(rows) < page_size: break
        page += len(rows)
    return rows_out, pages


def _analytics_by_video(analytics, start, end, video_ids=None):
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
               "likes,comments,shares,subscribersGained,subscribersLost")
    try:
        if video_ids is not None and not video_ids:
            return {"available":True,"by_video":{},"pages_fetched":0,"videos_with_analytics":0}
        rows, pages = _query_all_rows(analytics, start, end, "video", metrics,
                                      filters="video==" + ",".join(video_ids) if video_ids else None)
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
    """Fetch supported channel-level daily totals.

    YouTube Analytics rejects the video,day dimension combination for this
    query. The day dimension is requested alone, so these figures are channel
    totals and are deliberately not attributed to individual videos.
    """
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
               "likes,comments,shares,subscribersGained")
    try:
        rows, pages = _query_all_rows(analytics, start, end, "day", metrics)
        by_day = {row["day"]: {k: v for k, v in row.items() if k != "day"}
                  for row in rows if row.get("day")}
        return {"available":True,"by_day":by_day,"pages_fetched":pages,
                "daily_rows":len(by_day),"scope":"channel"}
    except Exception as exc:
        return {"available":False,"reason":str(exc),"by_day":{},
                "pages_fetched":0,"daily_rows":0,"scope":"channel"}


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
        # Reporting API uses "jobs" and "reports" collection keys, not "items".
        jobs = _paged_request(reporting.jobs(), "list", collection_key="jobs")
        job = next((j for j in jobs if j.get("reportTypeId")=="channel_reach_basic_a1"), None)
        created = False
        if job is None:
            try:
                job = reporting.jobs().create(body={"reportTypeId":"channel_reach_basic_a1",
                    "name":"Jyotirling Shivmath daily thumbnail reach"}).execute()
                created = True
            except Exception as create_error:
                # A previously-created job can exist even if a list response was
                # empty or delayed. Re-list before reporting a creation failure.
                jobs = _paged_request(reporting.jobs(), "list", collection_key="jobs")
                job = next((j for j in jobs if j.get("reportTypeId")=="channel_reach_basic_a1"), None)
                if job is None:
                    raise create_error
        reports = _paged_request(reporting.jobs(), "reports",
                                 collection_key="reports", jobId=job["id"])
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


def _read_inventory_cache(cache_path, channel_id, playlist_id):
    """Load the last complete inventory snapshot, if it belongs to this channel."""
    if not cache_path:
        return {}
    from pathlib import Path
    import json
    path = Path(cache_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (payload.get("schema_version") != 1 or
                payload.get("channel_id") != channel_id or
                payload.get("uploads_playlist_id") != playlist_id):
            return {}
        return payload.get("videos_by_id", {})
    except (OSError, ValueError, TypeError):
        return {}


def _write_inventory_cache(cache_path, channel_id, playlist_id, videos_by_id):
    """Persist the inventory so hourly runs do not rescan all historical uploads."""
    if not cache_path:
        return
    from pathlib import Path
    import json, os
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps({
        "schema_version": 1,
        "channel_id": channel_id,
        "uploads_playlist_id": playlist_id,
        "videos_by_id": videos_by_id
    }, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _fetch_video_details(youtube, video_ids):
    details = []
    for offset in range(0, len(video_ids), 50):
        result = youtube.videos().list(part="snippet,contentDetails,statistics,status,liveStreamingDetails",
            id=",".join(video_ids[offset:offset+50]), maxResults=50).execute()
        details.extend(result.get("items", []))
    return details


def _incremental_inventory(youtube, playlist_id, cached_by_id, max_videos):
    """Scan newest-first until the first known upload; fetch details only for new IDs."""
    new_playlist_items, new_ids, seen = [], [], set()
    token, scanned, found_known = None, 0, False
    while scanned < max_videos:
        page = youtube.playlistItems().list(part="snippet,contentDetails",
            playlistId=playlist_id, maxResults=50, pageToken=token).execute()
        items = page.get("items", [])
        scanned += len(items)
        for item in items:
            video_id = item.get("contentDetails", {}).get("videoId")
            if not video_id:
                continue
            if video_id in cached_by_id:
                found_known = True
                break
            if video_id not in seen:
                seen.add(video_id)
                new_ids.append(video_id)
                new_playlist_items.append(item)
        if found_known or not page.get("nextPageToken") or not items:
            break
        token = page.get("nextPageToken")

    # If a cache exists but no known item was encountered, continue scanning the
    # complete playlist up to the configured cap; this also repairs stale caches.
    ids, duplicate_entries = _unique_playlist_video_ids(new_playlist_items)
    new_details = _fetch_video_details(youtube, ids)
    updated = dict(cached_by_id)
    for item in new_details:
        if item.get("id"):
            updated[item["id"]] = item
    return updated, scanned, duplicate_entries, len(ids)


def run_channel_audit(youtube, analytics, max_videos=5000, include_unlisted=False,
                      daily_analytics_days=30, reporting=None, reporting_session=None,
                      inventory_cache_path=None, manual_from_date=None,
                      manual_to_date=None, timezone="Asia/Kolkata"):
    channel_response = youtube.channels().list(
        part="snippet,contentDetails,statistics", mine=True).execute()
    channels = channel_response.get("items", [])
    if not channels: raise RuntimeError("No YouTube channel was returned for the authorized account.")
    channel = channels[0]
    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    channel_id = channel.get("id", "")
    cached_by_id = _read_inventory_cache(inventory_cache_path, channel_id, playlist)

    if cached_by_id:
        videos_by_id, playlist_scanned, duplicate_entries, newly_found = _incremental_inventory(
            youtube, playlist, cached_by_id, max_videos)
    else:
        playlist_items = _paged_request(youtube.playlistItems(), "list",
            part="snippet,contentDetails", playlistId=playlist, maxResults=50)[:max_videos]
        ids, duplicate_entries = _unique_playlist_video_ids(playlist_items)
        initial_details = _fetch_video_details(youtube, ids)
        videos_by_id = {v["id"]: v for v in initial_details if v.get("id")}
        playlist_scanned, newly_found = len(playlist_items), len(ids)

    _write_inventory_cache(inventory_cache_path, channel_id, playlist, videos_by_id)
    details, duplicate_resources = _unique_video_details(list(videos_by_id.values()))
    ids = list(videos_by_id.keys())

    tz = ZoneInfo(timezone)
    now_local = datetime.now(tz)
    today_local = now_local.date()
    rolling_48h_cutoff = now_local - timedelta(hours=48)
    review_date = today_local - timedelta(days=90)
    manual_mode = bool(manual_from_date or manual_to_date)
    if manual_mode and (not manual_from_date or not manual_to_date):
        raise ValueError("Both manual_from_date and manual_to_date are required.")
    manual_start = date.fromisoformat(manual_from_date) if manual_from_date else None
    manual_end = date.fromisoformat(manual_to_date) if manual_to_date else None
    if manual_mode and manual_end < manual_start:
        raise ValueError("manual_to_date must be on or after manual_from_date.")

    videos = []
    for video in details:
        privacy = video.get("status", {}).get("privacyStatus", "unknown")
        if privacy != "public" and not include_unlisted: continue
        sn, stats = video.get("snippet", {}), video.get("statistics", {})
        content, vid = video.get("contentDetails", {}), video.get("id")
        published_raw = sn.get("publishedAt")
        if not published_raw:
            continue
        try:
            published_local_dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00")).astimezone(tz)
            published_local = published_local_dt.date()
        except (TypeError, ValueError):
            continue
        if manual_mode:
            if not (manual_start <= published_local <= manual_end):
                continue
        elif not (published_local_dt >= rolling_48h_cutoff or published_local == review_date):
            continue
        thumbs = sn.get("thumbnails", {})
        videos.append({"video_id":vid,"title":sn.get("title"),
            "description":sn.get("description"),"published_at":sn.get("publishedAt"),
            "stream_started_at":video.get("liveStreamingDetails", {}).get("actualStartTime"),
            "stream_ended_at":video.get("liveStreamingDetails", {}).get("actualEndTime"),
            "scheduled_start_time":video.get("liveStreamingDetails", {}).get("scheduledStartTime"),
            "live_broadcast_content":sn.get("liveBroadcastContent"),
            "privacy_status":privacy,"duration":content.get("duration"),
            "tags":sn.get("tags",[]),"category_id":sn.get("categoryId"),
            "default_language":sn.get("defaultLanguage"),
            "default_audio_language":sn.get("defaultAudioLanguage"),
            "thumbnail_urls":{k:v.get("url") for k,v in thumbs.items() if v.get("url")},
            "lifetime_statistics":{k:stats.get(k) for k in ("viewCount","likeCount","commentCount")},
            "last_90_days_analytics":None,
            "daily_analytics":[],
            "url":f"https://www.youtube.com/watch?v={vid}"})
    target_ids = [v["video_id"] for v in videos]
    # Refresh current metadata/statistics only for the selected date cohorts.
    # The 730-video inventory remains cached; this request is limited to the few
    # selected IDs (at most 50 IDs per videos.list call).
    fresh_target_details = _fetch_video_details(youtube, target_ids)
    fresh_by_id = {v.get("id"): v for v in fresh_target_details if v.get("id")}
    for video in videos:
        fresh = fresh_by_id.get(video["video_id"])
        if not fresh:
            continue
        sn, stats = fresh.get("snippet", {}), fresh.get("statistics", {})
        thumbs = sn.get("thumbnails", {})
        video.update({
            "title": sn.get("title"),
            "description": sn.get("description"),
            "tags": sn.get("tags", []),
            "thumbnail_urls": {k: v.get("url") for k, v in thumbs.items() if v.get("url")},
            "lifetime_statistics": {k: stats.get(k) for k in ("viewCount", "likeCount", "commentCount")},
            "stream_started_at": fresh.get("liveStreamingDetails", {}).get("actualStartTime"),
            "stream_ended_at": fresh.get("liveStreamingDetails", {}).get("actualEndTime"),
            "scheduled_start_time": fresh.get("liveStreamingDetails", {}).get("scheduledStartTime"),
            "live_broadcast_content": sn.get("liveBroadcastContent")
        })
    analytics_start = manual_start if manual_mode else review_date
    analytics_end = manual_end if manual_mode else today_local
    aggregate = _analytics_by_video(analytics, analytics_start.isoformat(),
                                    analytics_end.isoformat(), target_ids)
    for video in videos:
        video["last_90_days_analytics"] = aggregate["by_video"].get(video["video_id"])

    daily = {"available":False,"reason":"Daily channel-wide analytics disabled to conserve requests.",
             "by_day":{},"pages_fetched":0,"daily_rows":0,"scope":"disabled"}
    reach = {"available":False,"reason":"Thumbnail reach report downloads disabled in targeted scan.",
             "by_video":{},"reports_read":0,"job_created":False}

    return {"report_type":"read_only_channel_audit","report_schema_version":5,
        "period":{"start":analytics_start.isoformat(),"end":analytics_end.isoformat()},
        "daily_analytics_period":{"start":analytics_start.isoformat(),"end":analytics_end.isoformat(),
            "days_requested":(analytics_end-analytics_start).days+1},
        "scan_scope":{"mode":"manual_date_range" if manual_mode else "daily_targeted",
            "manual_from_date":manual_from_date,"manual_to_date":manual_to_date,
            "rolling_48_hours_since":None if manual_mode else rolling_48h_cutoff.isoformat(),
            "rolling_review_date":None if manual_mode else review_date.isoformat(),
            "full_channel_video_details_refetched":False},
        "channel":{"id":channel.get("id"),"title":channel.get("snippet",{}).get("title"),
            "custom_url":channel.get("snippet",{}).get("customUrl"),
            "statistics":channel.get("statistics",{})},
        "analytics_available":aggregate["available"],"analytics_note":aggregate.get("reason"),
        "analytics_pages_fetched":aggregate["pages_fetched"],
        "videos_with_target_period_analytics":aggregate["videos_with_analytics"],
        "daily_analytics_available":daily["available"],"daily_analytics_note":daily.get("reason"),
        "daily_analytics_scope":"disabled",
        "daily_channel_analytics":daily.get("by_day",{}),
        "daily_analytics_pages_fetched":daily["pages_fetched"],"daily_analytics_rows":daily["daily_rows"],
        "thumbnail_reach_available":False,"thumbnail_reach_note":reach.get("reason"),
        "thumbnail_reach_reports_read":0,
        "thumbnail_reach_job_created":False,
        "thumbnail_reach_report_type_id":None,
        "playlist_items_scanned":playlist_scanned,"unique_video_ids":len(ids),
        "new_video_ids_discovered_this_run":newly_found,
        "inventory_cache_used":bool(cached_by_id),
        "inventory_cache_video_count":len(videos_by_id),
        "inventory_video_count":len(videos),
        "duplicate_uploads_playlist_entry_count":len(duplicate_entries),
        "duplicate_uploads_playlist_entries":duplicate_entries,
        "duplicate_uploads_playlist_entries_note":"Repeated uploads-playlist references are not additional videos.",
        "duplicate_playlist_entries_count":len(duplicate_entries),
        "duplicate_playlist_entries":duplicate_entries,
        "duplicate_video_resource_ids_suppressed":duplicate_resources,"videos":videos,
        "safety":{"read_only":True,"channel_changes_made":False,"uploads_made":False}}
