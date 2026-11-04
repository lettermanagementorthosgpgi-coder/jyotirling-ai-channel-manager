"""Persist before-SEO baselines and calculate observed post-SEO performance deltas."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def record_successful_seo_baseline(db_path, video_id, before_stats, seo_changed_at=None,
                                   old_metadata=None, new_metadata=None):
    """Record pre-change lifetime counts only after the SEO update was verified."""
    changed_at = seo_changed_at or datetime.now(timezone.utc).isoformat()
    stats = before_stats or {}
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS seo_performance_baselines (
            video_id TEXT PRIMARY KEY,
            seo_changed_at TEXT NOT NULL,
            baseline_views INTEGER,
            baseline_likes INTEGER,
            baseline_comments INTEGER,
            old_metadata_json TEXT,
            new_metadata_json TEXT
        )""")
        db.execute("""INSERT INTO seo_performance_baselines(
            video_id, seo_changed_at, baseline_views, baseline_likes,
            baseline_comments, old_metadata_json, new_metadata_json
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(video_id) DO UPDATE SET
            seo_changed_at=excluded.seo_changed_at,
            baseline_views=excluded.baseline_views,
            baseline_likes=excluded.baseline_likes,
            baseline_comments=excluded.baseline_comments,
            old_metadata_json=excluded.old_metadata_json,
            new_metadata_json=excluded.new_metadata_json""",
            (video_id, changed_at, _int_or_none(stats.get("viewCount")),
             _int_or_none(stats.get("likeCount")), _int_or_none(stats.get("commentCount")),
             json.dumps(old_metadata or {}, ensure_ascii=False),
             json.dumps(new_metadata or {}, ensure_ascii=False)))
    return {"video_id": video_id, "seo_changed_at": changed_at,
            "baseline_captured": True}


def get_seo_baseline(db_path, video_id):
    with sqlite3.connect(db_path) as db:
        row = db.execute("""SELECT seo_changed_at, baseline_views, baseline_likes,
            baseline_comments, old_metadata_json, new_metadata_json
            FROM seo_performance_baselines WHERE video_id=?""", (video_id,)).fetchone()
    if not row:
        return None
    return {
        "seo_changed_at": row[0],
        "baseline_views": row[1],
        "baseline_likes": row[2],
        "baseline_comments": row[3],
        "old_metadata": json.loads(row[4] or "{}"),
        "new_metadata": json.loads(row[5] or "{}")
    }


def build_performance_delta(db_path, video_id, current_stats, subscribers_gained=None,
                            analytics_available=True):
    """Compare current lifetime counters and post-change subscribers with baseline."""
    baseline = get_seo_baseline(db_path, video_id)
    if baseline is None:
        return {"video_id": video_id, "baseline_available": False,
                "note": "No verified SEO-change baseline has been recorded for this video."}
    current = current_stats or {}
    deltas = {}
    for field, key in (("views", "viewCount"), ("likes", "likeCount"),
                       ("comments", "commentCount")):
        before, after = baseline.get("baseline_" + field), _int_or_none(current.get(key))
        deltas[field] = (after - before) if before is not None and after is not None else None
    return {
        "video_id": video_id,
        "baseline_available": True,
        "seo_changed_at": baseline["seo_changed_at"],
        "baseline": {
            "views": baseline["baseline_views"],
            "likes": baseline["baseline_likes"],
            "comments": baseline["baseline_comments"]
        },
        "current": {
            "views": _int_or_none(current.get("viewCount")),
            "likes": _int_or_none(current.get("likeCount")),
            "comments": _int_or_none(current.get("commentCount")),
            "subscribers_gained_since_seo": _int_or_none(subscribers_gained)
                if analytics_available else None
        },
        "observed_change": {
            **deltas,
            "subscribers_gained_since_seo": _int_or_none(subscribers_gained)
                if analytics_available else None
        },
        "analytics_available": bool(analytics_available),
        "interpretation": "Observed change since the verified SEO update; not proof that SEO alone caused the change."
    }


def query_subscribers_gained_since(analytics, video_id, start_date, end_date):
    """Query only this video's subscribers gained after its recorded SEO change."""
    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="subscribersGained",
            filters="video==" + video_id,
            maxResults=1
        ).execute()
        rows = response.get("rows", [])
        return {"available": True, "subscribers_gained": _int_or_none(rows[0][0]) if rows else 0}
    except Exception as exc:
        return {"available": False, "subscribers_gained": None,
                "reason": f"{type(exc).__name__}: {exc}"[:500]}


def _int_or_none(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
