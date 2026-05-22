import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

LOCAL_TZ = datetime.now().astimezone().tzinfo


def format_timestamp(ts: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(ts)
        dt = dt.astimezone(LOCAL_TZ)
        now = datetime.now(LOCAL_TZ)
        if dt.date() == now.date():
            return dt.strftime("Today %-I:%M %p")
        return dt.strftime("%b %-d, %-I:%M %p")
    except Exception:
        return ts

DB_PATH = Path(__file__).parent.parent / "data" / "second_brain.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                ai_category TEXT,
                url TEXT,
                title TEXT,
                duration_seconds INTEGER,
                raw_data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(timestamp, url)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                sender TEXT,
                subject TEXT,
                snippet TEXT,
                summary TEXT,
                category TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_cache (
                id TEXT PRIMARY KEY,
                label TEXT,
                summary TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '🎯',
                frequency TEXT,
                summary TEXT,
                total_mins INTEGER DEFAULT 0,
                last_active_date TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS focus_session_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                focus_session_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                UNIQUE(focus_session_id, date),
                FOREIGN KEY(focus_session_id) REFERENCES focus_sessions(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS focus_session_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                focus_session_id INTEGER NOT NULL,
                session_category TEXT NOT NULL,
                date TEXT NOT NULL,
                total_mins INTEGER DEFAULT 0,
                label TEXT,
                UNIQUE(focus_session_id, session_category, date),
                FOREIGN KEY(focus_session_id) REFERENCES focus_sessions(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS focus_session_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                focus_session_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(focus_session_id) REFERENCES focus_sessions(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_sessions (
                session_id TEXT NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (session_id, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_merges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                merged_ids TEXT NOT NULL,
                label TEXT NOT NULL,
                summary TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def insert_activity(source: str, category: str, timestamp: str,
                    url: str, title: str, duration_seconds: int, raw_data: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO activities
            (source, category, timestamp, url, title, duration_seconds, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source, category, timestamp, url, title, duration_seconds, raw_data))
        conn.commit()


def insert_email(message_id: str, timestamp: str, sender: str,
                 subject: str, snippet: str, summary: str, category: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO emails
            (message_id, timestamp, sender, subject, snippet, summary, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (message_id, timestamp, sender, subject, snippet, summary, category))
        conn.commit()


def add_focus_session_link(focus_session_id: int, session_category: str, date: str, total_mins: int, label: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO focus_session_links
            (focus_session_id, session_category, date, total_mins, label)
            VALUES (?, ?, ?, ?, ?)
        """, (focus_session_id, session_category, date, total_mins, label))
        conn.commit()


def update_focus_session_summary(focus_session_id: int, summary: str, total_mins: int, last_active_date: str):
    with get_connection() as conn:
        conn.execute("""
            UPDATE focus_sessions SET summary = ?, total_mins = ?, last_active_date = ? WHERE id = ?
        """, (summary, total_mins, last_active_date, focus_session_id))
        conn.commit()


def get_focus_session_links(focus_session_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM focus_session_links WHERE focus_session_id = ?
            ORDER BY date DESC
        """, (focus_session_id,)).fetchall()
    return [dict(r) for r in rows]


def add_focus_session_note(focus_session_id: int, note: str):
    with get_connection() as conn:
        conn.execute("INSERT INTO focus_session_notes (focus_session_id, note) VALUES (?, ?)", (focus_session_id, note))
        conn.commit()


def delete_focus_session_note(note_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM focus_session_notes WHERE id = ?", (note_id,))
        conn.commit()


def get_focus_session_notes(focus_session_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM focus_session_notes WHERE focus_session_id = ? ORDER BY created_at DESC
        """, (focus_session_id,)).fetchall()
    return [dict(r) for r in rows]


def complete_focus_session(focus_session_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE focus_sessions SET completed_at = datetime('now') WHERE id = ?", (focus_session_id,))
        conn.commit()


def get_all_focus_sessions() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM focus_sessions WHERE completed_at IS NULL ORDER BY created_at ASC"
        ).fetchall()
        focus_sessions = [dict(r) for r in rows]
        for fs in focus_sessions:
            done = conn.execute(
                "SELECT 1 FROM focus_session_completions WHERE focus_session_id = ? AND date = ?",
                (fs["id"], today)
            ).fetchone()
            fs["done_today"] = bool(done)
            fs["streak"] = _calc_streak(conn, fs["id"])
            fs["notes"] = [dict(r) for r in conn.execute(
                "SELECT * FROM focus_session_notes WHERE focus_session_id = ? ORDER BY created_at DESC",
                (fs["id"],)
            ).fetchall()]
            fs["links"] = [dict(r) for r in conn.execute(
                "SELECT * FROM focus_session_links WHERE focus_session_id = ? ORDER BY date DESC LIMIT 10",
                (fs["id"],)
            ).fetchall()]
    return focus_sessions


def _calc_streak(conn, focus_session_id: int) -> int:
    rows = conn.execute(
        "SELECT date FROM focus_session_completions WHERE focus_session_id = ? ORDER BY date DESC",
        (focus_session_id,)
    ).fetchall()
    if not rows:
        return 0
    streak = 0
    check = datetime.now().date()
    for row in rows:
        d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if d == check or d == check - __import__('datetime').timedelta(days=1):
            streak += 1
            check = d - __import__('datetime').timedelta(days=1)
        else:
            break
    return streak


def create_focus_session(name: str, emoji: str = "🎯", frequency: str = "") -> dict:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO focus_sessions (name, emoji, frequency) VALUES (?, ?, ?)",
            (name, emoji, frequency)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM focus_sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def delete_focus_session(focus_session_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM focus_sessions WHERE id = ?", (focus_session_id,))
        conn.execute("DELETE FROM focus_session_completions WHERE focus_session_id = ?", (focus_session_id,))
        conn.commit()


def toggle_focus_session_completion(focus_session_id: int) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM focus_session_completions WHERE focus_session_id = ? AND date = ?",
            (focus_session_id, today)
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM focus_session_completions WHERE focus_session_id = ? AND date = ?", (focus_session_id, today))
            conn.commit()
            return False
        else:
            conn.execute("INSERT INTO focus_session_completions (focus_session_id, date) VALUES (?, ?)", (focus_session_id, today))
            conn.commit()
            return True


def hide_session(session_id: str):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO hidden_sessions (session_id, date) VALUES (?, ?)", (session_id, today))
        conn.commit()


def get_hidden_sessions() -> set:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute("SELECT session_id FROM hidden_sessions WHERE date = ?", (today,)).fetchall()
    return {r["session_id"] for r in rows}


def save_session_merge(target_id: str, merged_ids: list[str], label: str, summary: str):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        # Remove any existing merge for this target today
        conn.execute("DELETE FROM session_merges WHERE target_id = ? AND date = ?", (target_id, today))
        conn.execute("""
            INSERT INTO session_merges (target_id, merged_ids, label, summary, date)
            VALUES (?, ?, ?, ?, ?)
        """, (target_id, json.dumps(merged_ids), label, summary, today))
        conn.commit()


def get_todays_merges() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM session_merges WHERE date = ? ORDER BY created_at ASC", (today,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_uncategorized_activities() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, url, title FROM activities
            WHERE ai_category IS NULL AND timestamp >= ?
        """, (today,)).fetchall()
    return [dict(r) for r in rows]


def update_ai_categories(id_category_map: dict[int, str]):
    with get_connection() as conn:
        for activity_id, category in id_category_map.items():
            conn.execute("UPDATE activities SET ai_category = ? WHERE id = ?", (category, activity_id))
        conn.commit()


def get_cached_session(session_id: str) -> tuple[str, str] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT label, summary FROM session_cache WHERE id = ?", (session_id,)
        ).fetchone()
    return (row["label"], row["summary"]) if row else None


def cache_session(session_id: str, label: str, summary: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO session_cache (id, label, summary) VALUES (?, ?, ?)",
            (session_id, label, summary)
        )
        conn.commit()


def get_activities_today(page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
    today = datetime.now().strftime("%Y-%m-%d")
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute("""
            SELECT COUNT(*) FROM activities WHERE timestamp >= ?
        """, (today,)).fetchone()[0]
        rows = conn.execute("""
            SELECT * FROM activities
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (today, page_size, offset)).fetchall()
    results = [dict(r) for r in rows]
    for r in results:
        r["timestamp"] = format_timestamp(r["timestamp"])
    return results, total


def get_emails_today(page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
    today = datetime.now().strftime("%Y-%m-%d")
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM emails WHERE timestamp >= ?", (today,)).fetchone()[0]
        rows = conn.execute("""
            SELECT * FROM emails
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (today, page_size, offset)).fetchall()
    results = [dict(r) for r in rows]
    for r in results:
        r["timestamp"] = format_timestamp(r["timestamp"])
    return results, total
