from datetime import datetime
from collections import defaultdict
import hashlib
import json
from app.database import get_connection, format_timestamp, LOCAL_TZ, get_cached_session, cache_session, get_todays_merges, hide_session, get_hidden_sessions as _get_hidden_sessions
from app.ai import summarize_session, summarize_claude_session
from app.connectors.claude_code import get_todays_sessions as get_claude_sessions


def get_sessions_today() -> list[dict]:
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM activities
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (today,)).fetchall()

    events = [dict(r) for r in rows]
    if not events:
        return []

    sessions = _group_by_category(events)
    for session in sessions:
        session_id = _session_id(session["events"], session["category"])
        session["session_id"] = session_id
        cached = get_cached_session(session_id)
        if cached:
            session["label"], session["summary"] = cached
        else:
            session["label"] = "⏳ Processing…"
            session["summary"] = "Summary will appear after next sync."
            session["pending"] = True

    # Add Claude Code sessions
    for cs in get_claude_sessions():
        cached = get_cached_session(cs["session_id"])
        if cached:
            label, summary = cached
        else:
            label, summary = "⏳ Processing…", "Summary will appear after next sync."
        # Normalize messages to match browser event structure for the template
        normalized_events = [
            {
                "source": "Claude Code",
                "title": m["content"][:80] + ("…" if len(m["content"]) > 80 else ""),
                "duration_seconds": 0,
                "timestamp": m["timestamp"].isoformat(),
                "category": "ai_coding",
                "url": "",
            }
            for m in cs["messages"]
        ]
        start_local = cs["start"].astimezone(LOCAL_TZ)
        end_local = cs["end"].astimezone(LOCAL_TZ)
        sessions.append({
            "category": "ai_coding",
            "events": normalized_events,
            "total_mins": cs["duration_mins"],
            "visit_count": len(cs["messages"]),
            "time_range": f"{start_local.strftime('%-I:%M %p')} – {end_local.strftime('%-I:%M %p')}",
            "label": label,
            "summary": summary,
        })

    # Assign stable IDs based on category before applying merges
    for i, s in enumerate(sessions):
        s["stable_id"] = s["category"]

    sessions = _apply_merges(sessions)
    # Filter out trivial sessions and manually hidden ones
    hidden = _get_hidden_sessions()
    sessions = [s for s in sessions if s["total_mins"] >= 2 and s.get("session_id") not in hidden]
    return sorted(sessions, key=lambda s: s["total_mins"], reverse=True)


def _apply_merges(sessions: list[dict]) -> list[dict]:
    merges = get_todays_merges()
    if not merges:
        return sessions

    import json as _json
    # Use category as stable key
    cat_map = {s["category"]: s for s in sessions}
    merged_away = set()

    for merge in merges:
        target_cat = merge["target_id"]
        merged_cats = _json.loads(merge["merged_ids"])
        target = cat_map.get(target_cat)
        if not target:
            continue
        target["label"] = merge["label"]
        target["summary"] = merge["summary"]
        for mcat in merged_cats:
            src = cat_map.get(mcat)
            if src:
                target["total_mins"] += src.get("total_mins", 0)
                merged_away.add(mcat)

    return [s for s in sessions if s["category"] not in merged_away]


def _group_by_category(events: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for event in events:
        category = _infer_category(event)
        groups[category].append(event)

    sessions = []
    for category, evts in groups.items():
        timestamps = [_parse_ts(e["timestamp"]) for e in evts if _parse_ts(e["timestamp"])]
        total_secs = sum(e.get("duration_seconds", 0) for e in evts)
        sessions.append({
            "category": category,
            "events": evts,
            "total_mins": max(1, total_secs // 60),
            "visit_count": len(evts),
            "time_range": _format_range(timestamps),
            "label": "",
            "summary": "",
        })

    return sessions


def _infer_category(event: dict) -> str:
    # Use AI category from DB if available
    if event.get("ai_category"):
        return event["ai_category"]
    # Fall back to domain-based grouping
    url = (event.get("url") or "").lower()
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    return f"browsing:{domain}" if domain else "other"


def _session_id(events: list[dict], category: str = "") -> str:
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    return hashlib.md5(f"{today}:{category}".encode()).hexdigest()


def _format_range(timestamps: list) -> str:
    if not timestamps:
        return ""
    start = min(timestamps)
    end = max(timestamps)
    return f"{start.strftime('%-I:%M %p')} – {end.strftime('%-I:%M %p')}"


def _parse_ts(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
    except Exception:
        return None
