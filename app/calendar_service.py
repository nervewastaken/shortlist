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

    # 2) If no unified token with calendar scope, check legacy calendar token
    if not creds and LEGACY_CAL_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(LEGACY_CAL_TOKEN_FILE), SCOPES)
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
    """Fallback extraction using a GPT model."""
    api_key = os.environ.get("OPENAIKEY")
    if not api_key:
        return None, None, None
    try:
        from openai import OpenAI
    except Exception:
        return None, None, None
    client = OpenAI(api_key=api_key)
    prompt = (
        "Extract the event date and time, location (if any) and first URL from "
        "the following email body. Respond in JSON with keys 'datetime', "
        "'location', 'link'. Use ISO 8601 for datetime in Asia/Kolkata.\n\n"
        f"Email:\n{text}"
    )
    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=prompt,
            response_format={"type": "json_object"},
        )
        content = resp.output[0].content[0].text
        data = json.loads(content)
        dt = dateparser.parse(data.get("datetime")) if data.get("datetime") else None
        return dt, data.get("location"), data.get("link")
    except Exception:
        return None, None, None


def extract_event_details(text: str) -> Tuple[Optional[datetime.datetime], Optional[str], Optional[str]]:
    """Extract datetime, location, and link from subject/body text.

    Strategy:
    - Normalize time formats like '9.00 am' -> '9:00 am'.
    - Prefer parsing from the first line (subject) to avoid catching footer times.
    - Look for date+time or time+date pairs within a close window.
    - Fallback to a fuzzy parse across the whole text.
    """
    if not text:
        return None, None, None

    # Normalize common time formats
    text_norm = text
    # Normalize a.m./p.m. variants to am/pm
    text_norm = re.sub(r"\b(a\.?m\.?)\b", "am", text_norm, flags=re.IGNORECASE)
    text_norm = re.sub(r"\b(p\.?m\.?)\b", "pm", text_norm, flags=re.IGNORECASE)
    # Normalize 'noon' and 'midnight'
    text_norm = re.sub(r"\bnoon\b", "12:00 pm", text_norm, flags=re.IGNORECASE)
    text_norm = re.sub(r"\bmidnight\b", "12:00 am", text_norm, flags=re.IGNORECASE)
    # Normalize '9.00 am' -> '9:00 am', and '9 am' -> '9:00 am'
    text_norm = re.sub(r"\b(\d{1,2})\.(\d{2})\s*(am|pm)\b", r"\1:\2 \3", text_norm, flags=re.IGNORECASE)
    text_norm = re.sub(r"\b(\d{1,2})\s*(am|pm)\b", r"\1:00 \2", text_norm, flags=re.IGNORECASE)

    # Subject-only window to avoid unrelated times later in the email
    first_line = text_norm.splitlines()[0] if text_norm.splitlines() else text_norm
    head = first_line[:240]

    # Attempt to parse an explicit date and time first
    dt = None
    # Pattern A: date ... time (e.g., '7th July 2025 by 9:00 am')
    pat_date_time = re.compile(
        r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}).{0,120}?(\d{1,2}[:.]?\d{0,2}\s*(?:am|pm))",
        re.IGNORECASE,
    )
    # Pattern B: time ... date (e.g., '9:00 am on 7th July 2025')
    pat_time_date = re.compile(
        r"(\d{1,2}[:.]?\d{0,2}\s*(?:am|pm)).{0,120}?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
        re.IGNORECASE,
    )
    match = pat_date_time.search(head) or pat_time_date.search(head)
    if not match:
        match = pat_date_time.search(text_norm) or pat_time_date.search(text_norm)
    if match:
        try:
            # Determine which pattern matched and build parse string accordingly
            if len(match.groups()) == 2:
                g1, g2 = match.group(1), match.group(2)
                if pat_date_time.pattern == match.re.pattern:
                    date_part, time_part = g1, g2
                else:
                    time_part, date_part = g1, g2
                time_part = time_part.replace('.', ':')
                dt = dateparser.parse(f"{date_part} {time_part}", fuzzy=True, dayfirst=True)
        except Exception:
            dt = None
    if not dt:
        # Try date-only and time-only extraction, then combine
        date_patters = [
            re.compile(r"\b(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b", re.IGNORECASE),
            re.compile(r"\b([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4})\b", re.IGNORECASE),
        ]
        time_patterns = [
            re.compile(r"\b(\d{1,2})(?::|\.)(\d{2})\s*(am|pm)\b", re.IGNORECASE),
            re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.IGNORECASE),
            re.compile(r"\b(\d{1,2})(?::|\.)(\d{2})\b"),  # 24h like 09:00 or 9.00
            re.compile(r"\b(\d{1,2})(\d{2})\s*(?:hrs|hours|h)\b", re.IGNORECASE),  # 0900 hrs
        ]

        def find_first(patterns, s1, s2):
            for p in patterns:
                m = p.search(s1)
                if m:
                    return m
            for p in patterns:
                m = p.search(s2)
                if m:
                    return m
            return None

        date_match = None
        for p in date_patters:
            date_match = p.search(head) or p.search(text_norm)
            if date_match:
                break
        time_match = find_first(time_patterns, head, text_norm)

        if date_match and time_match:
            try:
                date_part = date_match.group(1)
                # Build time string
                if time_match.re.pattern.find('hrs') != -1 or time_match.re.pattern.find('hours') != -1:
                    hh = time_match.group(1)
                    mm = time_match.group(2)
                    time_part = f"{hh}:{mm}"
                elif len(time_match.groups()) == 3:
                    hh, mm, ap = time_match.group(1), time_match.group(2), time_match.group(3)
                    time_part = f"{hh}:{mm} {ap}"
                elif len(time_match.groups()) == 2:
                    # either HH am/pm or HH:MM 24h
                    g1, g2 = time_match.group(1), time_match.group(2)
                    if g2.lower() in ('am','pm'):
                        time_part = f"{g1}:00 {g2}"
                    else:
                        time_part = f"{g1}:{g2}"
                else:
                    time_part = time_match.group(0)
                dt = dateparser.parse(f"{date_part} {time_part}", fuzzy=True, dayfirst=True)
            except Exception:
                dt = None
    if not dt:
        try:
            dt = dateparser.parse(text_norm, fuzzy=True, dayfirst=True)
        except Exception:
            dt = None

    # Location: check halls first, then block codes
    location = None
    for hall, desc in HALLS.items():
        if re.search(hall, text, re.IGNORECASE):
            location = desc
            break
    if not location:
        for code, desc in BLOCKS.items():
            if re.search(code, text, re.IGNORECASE):
                location = desc
                break

    # First URL in the text as join link
    link = None
    link_match = re.search(r"(https?://\S+)", text_norm)
    if link_match:
        link = link_match.group(1)

    # If critical information missing, try GPT
    if not dt or not location or not link:
        gpt_dt, gpt_loc, gpt_link = _gpt_extract(text)
        dt = dt or gpt_dt
        location = location or gpt_loc
        link = link or gpt_link

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
    # Parse from combined subject + body so dates in subject are not missed
    start_dt, location, link = extract_event_details(f"{subject}\n\n{body}")
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
