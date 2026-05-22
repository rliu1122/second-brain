from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from app.database import init_db, get_activities_today, get_emails_today, get_all_focus_sessions, create_focus_session, delete_focus_session, toggle_focus_session_completion, add_focus_session_note, delete_focus_session_note, complete_focus_session
from app.sync import sync_all
from app.ai import answer_question
from app.sessions import get_sessions_today
from app.connectors.calendar import get_todays_events

load_dotenv()

app = FastAPI()


def format_time(value: str) -> str:
    try:
        from app.database import LOCAL_TZ
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        return dt.strftime("%-I:%M %p")
    except Exception:
        return value
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["format_time"] = format_time

scheduler = BackgroundScheduler()


@app.on_event("startup")
def startup():
    init_db()
    scheduler.add_job(sync_all, "interval", hours=1, id="sync")
    scheduler.start()
    # Run initial sync in background so startup doesn't block
    import threading
    threading.Thread(target=lambda: sync_all(initial=True), daemon=True).start()


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, page: int = 1, email_page: int = 1):
    page_size = 10
    activities, total = get_activities_today(page=page, page_size=page_size)
    emails, email_total = get_emails_today(page=email_page, page_size=page_size)
    sessions = get_sessions_today()
    total_pages = max(1, (total + page_size - 1) // page_size)
    try:
        calendar_events = get_todays_events()
    except Exception as e:
        print(f"[calendar] unavailable: {e}")
        calendar_events = []
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "activities": activities,
        "emails": emails,
        "sessions": sessions,
        "calendar_events": calendar_events,
        "focus_sessions": get_all_focus_sessions(),
        "email_page": email_page,
        "email_total_pages": max(1, (email_total + page_size - 1) // page_size),
        "page": page,
        "total_pages": total_pages,
    })


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, question: str = Form(...)):
    activities, _ = get_activities_today(page=1, page_size=200)
    emails, _ = get_emails_today(page=1, page_size=200)
    answer = answer_question(question, activities, emails)
    return templates.TemplateResponse("query.html", {
        "request": request,
        "question": question,
        "answer": answer,
    })


@app.post("/focus_sessions", response_class=HTMLResponse)
async def add_focus_session(request: Request, name: str = Form(...), emoji: str = Form("🎯"), frequency: str = Form("")):
    create_focus_session(name, emoji, frequency)
    focus_sessions = get_all_focus_sessions()
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": focus_sessions})


@app.delete("/focus_sessions/{focus_session_id}", response_class=HTMLResponse)
async def remove_focus_session(request: Request, focus_session_id: int):
    delete_focus_session(focus_session_id)
    focus_sessions = get_all_focus_sessions()
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": focus_sessions})


@app.post("/focus_sessions/{focus_session_id}/toggle", response_class=HTMLResponse)
async def toggle_focus_session(request: Request, focus_session_id: int):
    toggle_focus_session_completion(focus_session_id)
    focus_sessions = get_all_focus_sessions()
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": focus_sessions})


@app.post("/chat")
async def chat(request: Request):
    from app.ai import chat_with_agent
    body = await request.json()
    messages = body.get("messages", [])
    activities, _ = get_activities_today(page=1, page_size=200)
    emails, _ = get_emails_today(page=1, page_size=200)
    reply = chat_with_agent(messages, activities, emails)
    return {"reply": reply}


@app.post("/focus_sessions/{focus_session_id}/notes", response_class=HTMLResponse)
async def add_note(request: Request, focus_session_id: int, note: str = Form(...)):
    add_focus_session_note(focus_session_id, note)
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": get_all_focus_sessions()})


@app.delete("/focus_sessions/notes/{note_id}", response_class=HTMLResponse)
async def remove_note(request: Request, note_id: int):
    delete_focus_session_note(note_id)
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": get_all_focus_sessions()})


@app.post("/focus_sessions/{focus_session_id}/complete", response_class=HTMLResponse)
async def mark_complete(request: Request, focus_session_id: int):
    complete_focus_session(focus_session_id)
    return templates.TemplateResponse("focus_sessions.html", {"request": request, "focus_sessions": get_all_focus_sessions()})


@app.post("/hide-session")
async def hide_session_route(request: Request):
    from app.database import hide_session
    body = await request.json()
    hide_session(body.get("session_id"))
    return {"status": "ok"}


@app.post("/merge-sessions")
async def merge_sessions(request: Request):
    from app.ai import summarize_merged_sessions
    from app.database import save_session_merge
    body = await request.json()
    labels = body.get("labels", [])
    summaries = body.get("summaries", [])
    target_id = body.get("target_id")
    merged_ids = body.get("merged_ids", [])
    label, summary = summarize_merged_sessions(labels, summaries)
    if target_id:
        save_session_merge(target_id, merged_ids, label, summary)
    return {"label": label, "summary": summary}


@app.post("/sync")
async def manual_sync():
    import threading
    threading.Thread(target=sync_all, daemon=True).start()
    return {"status": "ok"}
