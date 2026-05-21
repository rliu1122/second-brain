import os
import httpx
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")


def answer_question(question: str, activities: list[dict], emails: list[dict]) -> str:
    context = _build_context(activities, emails)

    prompt = (
        "You are a personal AI assistant with access to the user's activity log. "
        "Answer questions about what they did, learned, or worked on based on the data provided. "
        "Be concise and helpful. If the data doesn't contain enough information, say so.\n\n"
        f"Here is my activity data:\n\n{context}\n\nQuestion: {question}"
    )

    response = httpx.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["response"]


def summarize_session(events: list[dict]) -> tuple[str, str]:
    total_mins = sum(e.get("duration_seconds", 0) for e in events) // 60

    # Deduplicate titles but keep them meaningful
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
        response = httpx.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        text = response.json()["response"].strip()
        label = ""
        summary = ""
        for line in text.splitlines():
            if line.startswith("LABEL:"):
                label = line.replace("LABEL:", "").strip()
            elif line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
        return label or "🌐 Browsing", summary or ""
    except Exception:
        return "🌐 Browsing", ""


def summarize_email(sender: str, subject: str, snippet: str) -> str:
    prompt = (
        f"Summarize this email in one short sentence (max 20 words).\n\n"
        f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}"
    )
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["response"].strip()
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
