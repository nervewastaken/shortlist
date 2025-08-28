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

# Scope for inserting events into user's calendar
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = ROOT / "calendar_token.json"
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
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
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
    """Extract datetime, location, and link from email text."""
    if not text:
        return None, None, None

    # Attempt to parse an explicit date and time first
    dt = None
    match = re.search(
        r"(\d{1,2}[a-z]{0,2}\s+[A-Za-z]+\s+\d{4}).{0,40}?(\d{1,2}[:.]?\d{0,2}\s*(?:am|pm))",
        text,
        re.IGNORECASE,
    )
    if match:
        try:
            dt = dateparser.parse(f"{match.group(1)} {match.group(2)}", fuzzy=True, dayfirst=True)
        except Exception:
            dt = None
    if not dt:
        try:
            dt = dateparser.parse(text, fuzzy=True, dayfirst=True)
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
    link_match = re.search(r"(https?://\S+)", text)
    if link_match:
        link = link_match.group(1)

    # If critical information missing, try GPT
    if not dt or not location or not link:
        gpt_dt, gpt_loc, gpt_link = _gpt_extract(text)
        dt = dt or gpt_dt
        location = location or gpt_loc
        link = link or gpt_link

    return dt, location, link


def create_calendar_event(subject: str, body: str, message_id: str) -> bool:
    """Create a calendar event from email details."""
    service = get_calendar_service()
    start_dt, location, link = extract_event_details(body)
    if not start_dt:
        print("❌ No date/time found in email; skipping calendar event")
        return False

    end_dt = start_dt + datetime.timedelta(hours=1)

    description_lines = [f"Original mail: https://mail.google.com/mail/u/0/#inbox/{message_id}"]
    if link:
        description_lines.append(f"Join link: {link}")

    event: Dict[str, Any] = {
        "summary": subject or "Shortlisted Event",
        "description": "\n".join(description_lines),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
    }
    if location:
        event["location"] = location
    elif link:
        event["location"] = link

    service.events().insert(calendarId="primary", body=event).execute()
    return True


def should_create_calendar_event(email_data: Dict[str, Any]) -> bool:
    """Determine if the email warrants creating a calendar event."""
    match_type = email_data.get("match_type", "NO_MATCH")
    if match_type != "CONFIRMED_MATCH":
        return False

    subject = email_data.get("subject", "").lower()
    body_preview = email_data.get("body_preview", "").lower()

    shortlist_keywords = [
        "shortlist",
        "selected",
        "qualified",
        "interview",
        "next round",
        "congratulations",
        "proceed",
        "further process",
        "round 2",
        "technical interview",
        "hr interview",
        "final round",
    ]

    combined_text = f"{subject} {body_preview}"
    return any(keyword in combined_text for keyword in shortlist_keywords)
