import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def _generate(prompt: str) -> str:
    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text.strip()


def chat_with_agent(messages: list[dict], activities: list[dict], emails: list[dict]) -> str:
    context = _build_context(activities, emails)
    system = (
        "You are a personal AI assistant with access to the user's activity log for today. "
        "Answer questions about what they did, learned, or worked on. "
        "Be concise and conversational. Use the activity data below as your source of truth.\n\n"
        f"Activity data:\n{context}"
    )
    history = [
        {"role": "user", "parts": [{"text": system}]},
        {"role": "model", "parts": [{"text": "Got it, I have your activity data. What would you like to know?"}]},
    ]
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": msg["content"]}]})

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=MODEL,
            contents=history,
        )
        return response.text.strip()
    except Exception as e:
        return f"Sorry, I ran into an error: {e}"


def answer_question(question: str, activities: list[dict], emails: list[dict]) -> str:
    context = _build_context(activities, emails)
    prompt = (
        "You are a personal AI assistant with access to the user's activity log.\n"
        "Answer the question based on the data provided.\n\n"
        "Format your response as structured sections using this style:\n"
        "📌 Section Title\n"
        "  • bullet point\n"
        "  • bullet point\n\n"
        "Use relevant emojis for section titles (e.g. 🧠 Deep Work, 💼 Job Search, 📅 Upcoming, 📧 Emails).\n"
        "Be concise. Only include sections that have relevant data.\n"
        "If the data doesn't contain enough information, say so briefly.\n\n"
        f"Activity data:\n{context}\n\nQuestion: {question}"
    )
    return _generate(prompt)


def categorize_events(events: list[dict]) -> dict[str, str]:
    """Returns a mapping of event index -> category for a batch of events."""
    lines = []
    for i, e in enumerate(events):
        lines.append(f"{i}: url={e.get('url','')[:80]} title={e.get('title','')[:60]}")

    prompt = (
        "Categorize each browsing event into one of these categories:\n"
        "coding_practice, coding_research, job_search, entertainment, "
        "productivity, communication, reading, social, learning, shopping, other\n\n"
        "Events:\n" + "\n".join(lines) + "\n\n"
        "Reply with one line per event in format: <index>:<category>\n"
        "Example:\n0:coding_practice\n1:job_search"
    )
    try:
        text = _generate(prompt)
        result = {}
        for line in text.strip().splitlines():
            if ":" in line:
                idx, cat = line.split(":", 1)
                result[idx.strip()] = cat.strip()
        return result
    except Exception:
        return {}


def summarize_session(events: list[dict]) -> tuple[str, str]:
    total_mins = sum(e.get("duration_seconds", 0) for e in events) // 60

    seen = set()
    unique_titles = []
    for e in events:
        t = (e.get("title") or "").strip()
        if t and t not in seen:
            seen.add(t)
            unique_titles.append(f"- {t} ({e.get('duration_seconds', 0) // 60} mins)")

    prompt = (
        f"A user spent {total_mins} minutes on these pages:\n"
        f"{chr(10).join(unique_titles[:15])}\n\n"
        f"1. Give a short label (3-5 words) with a relevant emoji for what they were working on.\n"
        f"2. Write one sentence describing what they did, including specific page/problem names where relevant.\n\n"
        f"Respond in exactly this format:\n"
        f"LABEL: <emoji> <label>\n"
        f"SUMMARY: <one sentence>"
    )
    try:
        text = _generate(prompt)
        label, summary = "", ""
        for line in text.splitlines():
            if line.startswith("LABEL:"):
                label = line.replace("LABEL:", "").strip()
            elif line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
        return label or "🌐 Browsing", summary or ""
    except Exception:
        return "🌐 Browsing", ""


def link_sessions_to_focus(focus_name: str, sessions: list[dict]) -> list[str]:
    """Returns list of session categories that are related to the focus item."""
    if not sessions:
        return []
    lines = [f"- [{s['category']}] {s['label']}: {s['summary']}" for s in sessions]
    prompt = (
        f"Focus item: \"{focus_name}\"\n\n"
        f"Today's work sessions:\n" + "\n".join(lines) + "\n\n"
        f"Which session categories are related to this focus item? "
        f"Reply with a comma-separated list of category names only, or 'none' if none match.\n"
        f"Example: coding_practice, job_search"
    )
    try:
        text = _generate(prompt).strip().lower()
        if text == "none" or not text:
            return []
        return [c.strip() for c in text.split(",") if c.strip()]
    except Exception:
        return []


def summarize_focus_session(focus_name: str, links: list[dict], notes: list[dict]) -> str:
    if not links:
        return ""
    link_lines = [f"- {l['date']}: {l['label']} ({l['total_mins']} mins)" for l in links]
    note_lines = [f"- {n['note']}" for n in notes] if notes else []
    total = sum(l["total_mins"] for l in links)
    prompt = (
        f"Write a 2-3 sentence progress summary for the focus item \"{focus_name}\".\n\n"
        f"Work sessions (total: {total} mins across {len(set(l['date'] for l in links))} days):\n"
        + "\n".join(link_lines)
        + ("\n\nUser notes:\n" + "\n".join(note_lines) if note_lines else "")
        + "\n\nBe specific about what was worked on, how much progress, and when last active."
    )
    try:
        return _generate(prompt).strip()
    except Exception:
        return ""


def summarize_merged_sessions(labels: list[str], summaries: list[str]) -> tuple[str, str]:
    prompt = (
        f"The following work sessions are being merged into one:\n\n"
        + "\n".join(f"- {l}: {s}" for l, s in zip(labels, summaries))
        + "\n\n"
        f"Generate a single combined label and summary.\n"
        f"1. Give a short label (3-5 words) with a relevant emoji.\n"
        f"2. Write one sentence summarizing all the work done.\n\n"
        f"Respond in exactly this format:\n"
        f"LABEL: <emoji> <label>\n"
        f"SUMMARY: <one sentence>"
    )
    try:
        text = _generate(prompt)
        label, summary = "", ""
        for line in text.splitlines():
            if line.startswith("LABEL:"):
                label = line.replace("LABEL:", "").strip()
            elif line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
        return label or labels[0], summary or summaries[0]
    except Exception:
        return labels[0], summaries[0]


def summarize_claude_session(messages: list[dict], duration_mins: int) -> tuple[str, str]:
    user_messages = [m["content"] for m in messages if m.get("role") == "user"][:15]
    prompt = (
        f"A user spent {duration_mins} minutes in a Claude Code AI coding session.\n"
        f"Here are their messages:\n"
        + "\n".join(f"- {m}" for m in user_messages)
        + "\n\n"
        f"1. Give a short label (3-5 words) with a relevant emoji for what they were working on.\n"
        f"2. Write one sentence describing what they built or discussed in detail.\n\n"
        f"Respond in exactly this format:\n"
        f"LABEL: <emoji> <label>\n"
        f"SUMMARY: <one sentence>"
    )
    try:
        text = _generate(prompt)
        label, summary = "", ""
        for line in text.splitlines():
            if line.startswith("LABEL:"):
                label = line.replace("LABEL:", "").strip()
            elif line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
        return label or "🤖 AI Coding Session", summary or ""
    except Exception:
        return "🤖 AI Coding Session", ""


def summarize_email(sender: str, subject: str, snippet: str) -> str:
    prompt = (
        f"Summarize this email in one short sentence (max 20 words).\n\n"
        f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}"
    )
    try:
        return _generate(prompt)
    except Exception:
        return snippet[:100]


def _build_context(activities: list[dict], emails: list[dict]) -> str:
    parts = []

    if activities:
        parts.append("=== Browser Activity ===")
        for a in activities:
            mins = a["duration_seconds"] // 60
            parts.append(f"- {a['source']} | {a['title']} | {mins} mins | {a['timestamp']}")

    if emails:
        parts.append("\n=== Emails ===")
        for e in emails:
            parts.append(f"- From: {e['sender']} | Subject: {e['subject']} | {e['timestamp']}")

    return "\n".join(parts) if parts else "No activity data available."
