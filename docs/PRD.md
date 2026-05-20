# PRD: Second Brain — Personal AI Life Logger

## Problem Statement

Knowledge workers and learners face two compounding problems:

1. **Context switching overhead** — juggling work, personal projects, and home tasks creates mental load, anxiety, and lost momentum
2. **Knowledge fragmentation** — notes are scattered, retrieval is broken, and manual capture adds friction that kills consistency

Existing tools (Notion, Obsidian, Apple Notes) all require deliberate manual input. People don't use them consistently because capturing feels like a second job.

## Core Insight

The best capture is no capture. An AI-native life logger should passively observe what you do and build your second brain automatically. Manual input is a fallback, not the default.

---

## Target User

Solo individual (initially: the builder themselves) who:
- Juggles multiple projects simultaneously
- Wants to learn and retain knowledge better
- Feels anxious about open loops and unfinished tasks
- Dislikes manual note-taking

---

## Passive Capture Sources

| Source | What it captures | Effort |
|---|---|---|
| ActivityWatch (browser) | Time spent on configured sites (LeetCode, LinkedIn, GitHub, etc.) | Low |
| Gmail | Emails sent/received, recruiters, decisions | Low |
| LeetCode API | Problems solved, submissions, pass/fail, difficulty | Medium |
| Git commits | Code written, repos worked on | Medium |
| App/screen time | Time per app on desktop/mobile | Medium |
| Screen summarization | Periodic screenshot → AI summary | High |
| Voice | Ambient transcription + summarization | High |

### Site Tracking Config
Users define which sites to track via a config file. ActivityWatch captures time on any configured site — no custom connector needed per site.

```yaml
sources:
  - name: LeetCode
    type: browser
    url: leetcode.com
    category: coding_practice
  - name: LinkedIn
    type: browser
    url: linkedin.com
    category: job_search
  - name: GitHub
    type: browser
    url: github.com
    category: coding
  - name: Gmail
    type: api
    connector: gmail
    category: communication
```

---

## Core Features

### 1. Passive Activity Logging
- ActivityWatch runs silently in the background, tracking time per configured site
- Syncs every hour to pull activity and store in local SQLite
- Gmail syncs every hour for new emails
- Stores structured activity log: `{timestamp, source, activity, category, duration, notes}`
- Example: *"3:00–5:30pm — LeetCode: 2.5 hrs on leetcode.com"*

### 2. Brain Dump
- Frictionless quick capture: voice memo, text, photo
- AI instantly categorizes, tags, and links it to existing knowledge
- No folders, no manual organization

### 3. Daily Summary
- Every evening: AI generates a digest of what you did, learned, and left unfinished
- Flags open loops so your brain can let go of them
- Suggests what to prioritize tomorrow

### 4. Semantic Search & Q&A
- Ask in natural language: *"What did I work on last Tuesday?"* or *"What do I know about sliding window?"*
- Returns relevant notes, activities, and context — not just keyword matches

### 5. Context Resume
- When switching back to a task, AI shows: last action, where you left off, relevant notes
- Reduces the "where was I?" tax

---

## Technical Stack

- **Backend**: Python + FastAPI
- **Frontend**: HTMX (server-rendered, minimal JavaScript)
- **Storage**: Local SQLite (privacy-first, no cloud required)
- **AI layer**: Claude API for summarization, categorization, Q&A
- **Activity tracking**: ActivityWatch (local app + Chrome extension)
- **Sync frequency**: Hourly

---

## Phased Implementation

### Phase 1 — Foundation
**Goal:** Working app that captures activity and answers basic questions

Sources:
- ActivityWatch (browser time tracking for configured sites)
- Gmail

Features:
- Config system for which sites to track
- Hourly sync from ActivityWatch API + Gmail API
- SQLite storage
- Web UI (FastAPI + HTMX)
- Basic Q&A: *"What did I do today?"*

### Phase 2 — Richer Data
- LeetCode API (submission history, pass/fail, difficulty)
- Git commits
- Daily summary generation
- Semantic search

### Phase 3 — Intelligence
- Context resume
- Brain dump (voice, text, photo)
- Proactive reminders for open loops
- Smarter summarization across sources

---

## Out of Scope (V1)
- Multi-user / team features
- Mobile app
- Building a custom browser extension (using ActivityWatch instead)

---

## Success Metrics (Personal)
- Zero manual logging required for >80% of daily activities
- Can answer "what did I do/learn this week?" without thinking
- Noticeable reduction in end-of-day anxiety about open loops
