from datetime import datetime
from collections import defaultdict
from app.database import get_connection, format_timestamp, LOCAL_TZ
from app.ai import summarize_session


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
        session["label"], session["summary"] = summarize_session(session["events"])

    return sorted(sessions, key=lambda s: s["total_mins"], reverse=True)


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
    source = (event.get("source") or "").lower()
    url = (event.get("url") or "").lower()
    title = (event.get("title") or "").lower()

    if any(x in url for x in ["leetcode", "hackerrank", "codewars", "neetcode"]):
        return "coding_practice"
    if any(x in url for x in ["github", "stackoverflow", "docs.", "developer."]):
        return "coding_research"
    if any(x in url for x in ["linkedin", "greenhouse", "lever", "ashby", "glassdoor", "wellfound"]):
        return "job_search"
    if any(x in url for x in ["youtube", "netflix", "twitch", "spotify"]):
        return "entertainment"
    if any(x in url for x in ["notion", "docs.google", "confluence", "figma"]):
        return "productivity"
    if any(x in url for x in ["twitter", "reddit", "hackernews", "news"]):
        return "reading"
    if event.get("category") not in ("other", "browsing", None):
        return event["category"]
    return "other"


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
