import httpx
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

AW_URL = os.getenv("ACTIVITYWATCH_URL", "http://localhost:5600")


def get_buckets() -> list[dict]:
    response = httpx.get(f"{AW_URL}/api/0/buckets/")
    response.raise_for_status()
    return list(response.json().values())


def get_browser_bucket_id() -> str | None:
    buckets = get_buckets()
    for bucket in buckets:
        if "web" in bucket["id"].lower() or "browser" in bucket["id"].lower():
            return bucket["id"]
    return None


def get_events(bucket_id: str, start: datetime, end: datetime) -> list[dict]:
    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": 1000,
    }
    response = httpx.get(f"{AW_URL}/api/0/buckets/{bucket_id}/events", params=params)
    response.raise_for_status()
    return response.json()


def get_browser_activity(start: datetime, end: datetime, tracked_urls: list[str]) -> list[dict]:
    bucket_id = get_browser_bucket_id()
    if not bucket_id:
        return []

    events = get_events(bucket_id, start, end)
    results = []

    for event in events:
        url = event.get("data", {}).get("url", "")
        title = event.get("data", {}).get("title", "")
        duration = event.get("duration", 0)

        # Match against configured URLs, fall back to the domain name
        matched_source = urlparse(url).netloc or "other"
        for tracked_url in tracked_urls:
            if tracked_url in url:
                matched_source = tracked_url
                break

        results.append({
            "url": url,
            "title": title,
            "duration_seconds": int(duration),
            "timestamp": event.get("timestamp"),
            "matched_source": matched_source,
        })

    return results
