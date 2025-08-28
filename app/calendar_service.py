"""Calendar integration for shortlist notifications.

This module creates Google Calendar events based on email content.  It first
tries simple parsing rules and falls back to a small GPT model when no explicit
date/time can be detected.  The OpenAI key is read from
``process.env.OPENAIKEY`` (i.e. the ``OPENAIKEY`` environment variable) so the
user can provide it via a ``.env`` file.
"""

import re
import os
import json
import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from dateutil import parser as dateparser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [CALENDAR_SCOPE]
COMBINED_SCOPES = [GMAIL_READ_SCOPE, CALENDAR_SCOPE]

ROOT = Path(__file__).resolve().parents[1]
# Primary unified token (shared with Gmail)
PRIMARY_TOKEN_FILE = ROOT / "token.json"
# Legacy calendar-only token (kept for backward compatibility)
LEGACY_CAL_TOKEN_FILE = ROOT / "calendar_token.json"
CREDENTIALS_FILE = ROOT / "credentials.json"

# Recognize local env files for convenience
ENV_FILES = [ROOT / ".env.local", ROOT / ".env"]

def _load_env_files_if_needed():
    """Load key=value pairs from .env.local/.env into os.environ if not present.

    This is a minimal loader to avoid an extra dependency. It supports lines like:
    - OPENAIKEY=sk-...
    - export OPENAIKEY="sk-..."
    - Comments starting with '#'
    """
    for path in ENV_FILES:
        try:
            if not path.exists():
                continue
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                # Allow optional leading 'export'
                if line.lower().startswith('export '):
                    line = line[7:].lstrip()
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        except Exception:
            # Silently ignore malformed env files
            pass

# Academic block codes and hall names
BLOCKS = {
    "PRP": "Pearl Research Park",
    "MGB": "Mahatma Gandhi Block",
    "SJT": "Silver Jubliee Tower",
    "TT": "Technology Tower",
    "SMV": "SMV",
    "MGR": "MGR",
    "CDMM": "CDMM",
    "GDN": "GDN",
}

HALLS = {
    "Sarojini Naidu": "SJT 6th floor",
    "Bhagat Singh": "SJT 8th floor",
    "Homi Bhabha": "SJT 4th floor",
    "Channa Reddy": "MGR Ground flood",
    "Anna Auditorium": "Opposite MGR",
    "Kamaraj Auditorium": "TT 8th floor",
    "Ambedkar auditorium": "TT Ground Floor",
}

def get_calendar_service():
    """Authenticate and return a Google Calendar API service."""
    creds = None

    # 1) Prefer unified token.json if it already includes calendar scope
    if PRIMARY_TOKEN_FILE.exists():
        try:
            data = json.loads(PRIMARY_TOKEN_FILE.read_text())
            scopes = set(data.get("scopes", []))
            if CALENDAR_SCOPE in scopes:
                creds = Credentials.from_authorized_user_file(str(PRIMARY_TOKEN_FILE), SCOPES)
        except Exception:
            creds = None


    # 3) If still missing/invalid, refresh or run a unified OAuth flow (both Gmail + Calendar)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), COMBINED_SCOPES)
            creds = flow.run_local_server(port=0)
        # Always write/update unified token.json so future runs need only one token
        PRIMARY_TOKEN_FILE.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _gpt_extract(text: str) -> Tuple[Optional[datetime.datetime], Optional[str], Optional[str]]:
    """Extract event details using a GPT model only.

    Returns combined datetime built from separate 'date' and 'time' fields
    when available to avoid ambiguous single-datetime parsing.
    """
    # Try env directly; if missing, attempt to load from .env.local/.env
    api_key = os.environ.get("OPENAIKEY")
    if not api_key:
        _load_env_files_if_needed()
        api_key = os.environ.get("OPENAIKEY")
    if not api_key:
        print("⚠️ OPENAIKEY not set; GPT extraction disabled")
        return None, None, None
    try:
        from openai import OpenAI
    except Exception:
        print("⚠️ openai package not available; GPT extraction disabled")
        return None, None, None
    client = OpenAI(api_key=api_key)
    # Debug: key presence and input stats
    try:
        subj_line = next((ln for ln in (text.splitlines() if text else []) if ln.lower().startswith("subject:")), "")
        print(f"🧪 GPT extract start | key=present | text_len={len(text or '')} | subject='{subj_line}'")
    except Exception:
        pass
    prompt = (
        f"""You are extracting calendar event details from an email. Read BOTH the Subject and the Body.
        The date/time is often present in the Subject. Return ONLY valid JSON with keys exactly:
        'date', 'time', 'location', and 'link'.

        Rules:
        - date: 'YYYY-MM-DD' (Asia/Kolkata). Convert formats like '7th July 2025' -> '2025-07-07'.
        - time: 'HH:MM am/pm' (e.g., '9:00 am') OR 24-hour 'HH:MM'. Convert '9.00 am' -> '9:00 am'.
        - location: venue/hall name or 'virtual' if clearly online, else empty string.
        - link: first URL if present, else empty string.
        - If unknown, set that field to an empty string.

        Example:
        Subject: Okta online test is scheduled on 7th July 2025 by 9.00 am - virtual mode
        Body: Test duration: 2 hours
        Output: {{"date": "2025-07-07", "time": "9:00 am", "location": "virtual", "link": ""}}

        Subject and Body below:
        {text}
        """
    )
    try:
        print("📤 Sending to OpenAI chat.completions (gpt-4o-mini) ...")
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": "Extract calendar event details. Return only JSON with keys: date, time, location, link."},
                {"role": "user", "content": prompt},
            ],
        )
        # Be tolerant to SDK response variants
        try:
            content = resp.choices[0].message.content
        except Exception:
            try:
                content = resp.choices[0]["message"]["content"]
            except Exception:
                content = None
        print(f"📥 GPT raw content length: {len(content or '')}")
        if content:
            preview = content if len(content) <= 400 else content[:400] + "..."
            print(f"📥 GPT raw content preview: {preview}")
        else:
            print("❌ GPT returned empty content")
            return None, None, None
        data = json.loads(content)
        date_str = (data.get("date") or "").strip()
        time_str = (data.get("time") or "").strip()
        dt = None
        if date_str:
            try:
                dt = dateparser.parse(f"{date_str} {time_str}".strip(), fuzzy=True, dayfirst=True)
            except Exception:
                try:
                    dt = dateparser.parse(date_str, fuzzy=True, dayfirst=True)
                except Exception:
                    dt = None
        print(f"🔎 GPT fields -> date='{date_str}', time='{time_str}', location='{data.get('location','')}', link='{data.get('link','')}'")
        print(f"🧮 Combined datetime candidate: {dt}")
        return dt, (data.get("location") or None), (data.get("link") or None)
    except Exception:
        import traceback
        print("❌ GPT extraction exception:\n" + traceback.format_exc())
        return None, None, None


def extract_event_details(text: str) -> Tuple[Optional[datetime.datetime], Optional[str], Optional[str]]:
    """Extract datetime, location, and link using GPT only.

    All heuristic/regex parsing is intentionally disabled for consistency.
    """
    if not text:
        return None, None, None
    dt, location, link = _gpt_extract(text)
    if not dt:
        print("❌ GPT could not extract date/time from text (no fallback active)")
    return dt, location, link


def _derive_summary(subject: str) -> str:
    """Create a concise event title like 'Okta - Online Test'."""
    if not subject:
        return "Shortlisted Event"
    subj = subject.strip()
    subj = re.sub(r"^(re|fw|fwd)\s*:\s*", "", subj, flags=re.IGNORECASE)

    lower = subj.lower()
    # Order matters: more specific to generic
    kinds = [
        "online test",
        "coding test",
        "aptitude test",
        "online assessment",
        "assessment",
        "technical interview",
        "hr interview",
        "final round",
        "interview",
        "superday",
        "gd",
        "group discussion",
        "written test",
        "exam",
        "test",
    ]
    kind_found = None
    idx = -1
    for k in kinds:
        idx = lower.find(k)
        if idx != -1:
            kind_found = k
            break

    if kind_found is None:
        # Fallback: shorten subject
        return subj[:80]

    # Company is whatever precedes the kind phrase
    company = subj[:idx].strip(" -–—:|\u2013\u2014") or "Company"
    # Normalize casing
    kind_title = " ".join(w.capitalize() for w in kind_found.split())
    return f"{company} - {kind_title}"


def create_calendar_event(subject: str, body: str, message_id: str) -> bool:
    """Create a calendar event from email details."""
    service = get_calendar_service()
    # Parse from explicit Subject/Body labeling so GPT recognizes both
    combined_text = f"Subject: {subject or ''}\n\nBody:\n{body or ''}"
    start_dt, location, link = extract_event_details(combined_text)
    if not start_dt:
        print("❌ No date/time found in email; skipping calendar event")
        return False

    # Determine duration: default 1h; detect phrases like 'duration: 2 hours' or '120 minutes'
    duration_hours = 1
    body_lower = (body or "").lower()
    m_hrs = re.search(r"duration\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:hours|hour|hrs|hr)\b", body_lower)
    m_min = re.search(r"duration\s*[:\-]?\s*(\d+)\s*(?:minutes|min|mins)\b", body_lower)
    if m_hrs:
        try:
            duration_hours = float(m_hrs.group(1))
        except Exception:
            duration_hours = 1
    elif m_min:
        try:
            duration_hours = max(1, int(m_min.group(1)) / 60.0)
        except Exception:
            duration_hours = 1

    # Round duration to quarter-hours and cap to 4 hours to avoid unrealistic spans
    duration_hours = max(1, min(4, round(duration_hours * 4) / 4))
    end_dt = start_dt + datetime.timedelta(hours=duration_hours)

    print(f"🕒 Parsed datetime: {start_dt} | location: {location or '-'} | link: {link or '-'}")
    description_lines = [f"Original mail: https://mail.google.com/mail/u/0/#inbox/{message_id}"]
    if link:
        description_lines.append(f"Join link: {link}")
    if location and (not link or location != link):
        description_lines.append(f"Location: {location}")
    # Include full subject and detected duration for context
    if subject:
        description_lines.append(f"Subject: {subject}")
    if duration_hours and duration_hours != 1:
        description_lines.append(f"Duration: {duration_hours:g} hour(s)")

    event: Dict[str, Any] = {
        "summary": _derive_summary(subject),
        "description": "\n".join(description_lines),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
    }
    if location:
        event["location"] = location
    elif link:
        event["location"] = link

    try:
        service.events().insert(calendarId="primary", body=event).execute()
        return True
    except Exception as e:
        print(f"❌ Calendar API error: {e}")
        return False


def should_create_calendar_event(email_data: Dict[str, Any]) -> bool:
    """Determine if the email warrants creating a calendar event."""
    match_type = email_data.get("match_type", "NO_MATCH")
    # Create events for all confirmed matches without further keyword gating
    return match_type == "CONFIRMED_MATCH"
