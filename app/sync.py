from datetime import datetime, timedelta, timezone
from app.config import load_config, get_browser_sources, get_api_sources
from app.connectors.activitywatch import get_browser_activity
from app.connectors.gmail import get_recent_emails
from app.database import insert_activity, insert_email, get_uncategorized_activities, update_ai_categories
from app.ai import summarize_email, categorize_events
import json


def _normalize_timestamp(ts: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(ts)
        return dt.isoformat()
    except Exception:
        return ts


def sync_activitywatch():
    try:
        config = load_config()
        browser_sources = get_browser_sources(config)
        tracked_urls = [s["url"] for s in browser_sources]
        source_map = {s["url"]: s for s in browser_sources}

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=1)

        events = get_browser_activity(start, end, tracked_urls)

        for event in events:
            matched = event["matched_source"]
            source = source_map.get(matched, {"name": matched, "category": "browsing"})
            insert_activity(
                source=source["name"],
                category=source["category"],
                timestamp=event["timestamp"],
                url=event["url"],
                title=event["title"],
                duration_seconds=event["duration_seconds"],
                raw_data=json.dumps(event),
            )

        print(f"[sync] ActivityWatch: {len(events)} events synced")
    except Exception as e:
        print(f"[sync] ActivityWatch unavailable: {e}")


def sync_gmail(hours: int = 1):
    try:
        # Always sync from start of today to avoid missing emails on new day
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        hours_since_midnight = now.hour + now.minute / 60
        hours_to_fetch = max(hours, int(hours_since_midnight) + 1)

        emails = get_recent_emails(hours=hours_to_fetch)
        for email in emails:
            summary = summarize_email(email["sender"], email["subject"], email["snippet"])
            insert_email(
                message_id=email["message_id"],
                timestamp=_normalize_timestamp(email["timestamp"]),
                sender=email["sender"],
                subject=email["subject"],
                snippet=email["snippet"],
                summary=summary,
                category="communication",
            )
        print(f"[sync] Gmail: {len(emails)} emails synced")
    except Exception as e:
        print(f"[sync] Gmail unavailable: {e}")


def sync_categories():
    try:
        uncategorized = get_uncategorized_activities()
        if not uncategorized:
            return
        ai_cats = categorize_events(uncategorized)
        id_map = {uncategorized[int(i)]["id"]: cat for i, cat in ai_cats.items() if i.isdigit() and int(i) < len(uncategorized)}
        if id_map:
            update_ai_categories(id_map)
        print(f"[sync] Categorized {len(id_map)} activities")
    except Exception as e:
        print(f"[sync] Categorization failed: {e}")


def sync_sessions():
    try:
        from app.sessions import get_sessions_today, _session_id
        from app.database import get_cached_session, cache_session
        from app.ai import summarize_session, summarize_claude_session
        from app.connectors.claude_code import get_todays_sessions as get_claude_sessions

        sessions = get_sessions_today()
        for session in sessions:
            if session.get("pending") and session.get("total_mins", 0) >= 2:
                sid = session.get("session_id") or _session_id(session["events"], session.get("category", ""))
                label, summary = summarize_session(session["events"])
                cache_session(sid, label, summary)

        for cs in get_claude_sessions():
            cached = get_cached_session(cs["session_id"])
            if not cached:
                label, summary = summarize_claude_session(cs["messages"], cs["duration_mins"])
                cache_session(cs["session_id"], label, summary)

        print(f"[sync] Sessions summarized")
    except Exception as e:
        print(f"[sync] Session summarization failed: {e}")


def sync_focus_sessions():
    try:
        from app.database import get_all_focus_sessions, add_focus_session_link, update_focus_session_summary, get_focus_session_links
        from app.ai import link_sessions_to_focus, summarize_focus_session
        from app.sessions import get_sessions_today
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        focus_items = get_all_focus_sessions()
        if not focus_items:
            return

        sessions = [s for s in get_sessions_today() if not s.get("pending")]
        if not sessions:
            return

        for fs in focus_items:
            related_cats = link_sessions_to_focus(fs["name"], sessions)
            for cat in related_cats:
                session = next((s for s in sessions if s["category"] == cat), None)
                if session:
                    add_focus_session_link(
                        focus_session_id=fs["id"],
                        session_category=cat,
                        date=today,
                        total_mins=session["total_mins"],
                        label=session["label"],
                    )

            all_links = get_focus_session_links(fs["id"])
            if all_links:
                total_mins = sum(l["total_mins"] for l in all_links)
                last_active = max(l["date"] for l in all_links)
                summary = summarize_focus_session(fs["name"], all_links, fs.get("notes", []))
                update_focus_session_summary(fs["id"], summary, total_mins, last_active)

        print(f"[sync] Focus sessions updated")
    except Exception as e:
        print(f"[sync] Focus session sync failed: {e}")


def sync_all(initial: bool = False):
    print(f"[sync] Starting sync at {datetime.now()}")
    sync_activitywatch()
    sync_gmail(hours=24 if initial else 1)
    sync_categories()
    sync_sessions()
    sync_focus_sessions()
    print(f"[sync] Done")
