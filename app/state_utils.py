"""Small helpers for reading/writing state and logs.

Paths are passed in explicitly so the runner remains in control.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


def load_state(path: Path) -> dict:
    """Load the JSON state object from a file, with a safe fallback."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "last_message_id": None,
        "confirmed_matches": [],
        "possibilities": [],
        "partial_matches": [],
    }


def save_state(state: dict, path: Path) -> None:
    """Persist the state to disk as pretty JSON."""
    path.write_text(json.dumps(state, indent=2))


def save_profile(profile: dict, path: Path) -> None:
    """Persist the profile to disk as pretty JSON."""
    path.write_text(json.dumps(profile, indent=2))


def log_match_to_data(profile: Dict[str, Any], email_data: Dict[str, Any], data_dir: Path) -> None:
    """Log a match between profile and email to the data directory."""
    import datetime

    timestamp = datetime.datetime.now().isoformat()
    match_data = {
        "timestamp": timestamp,
        "profile": {
            "name": profile.get("name", ""),
            "registration_number": profile.get("registration_number", ""),
            "gmail_address": profile.get("gmail_address", ""),
            "personal_email": profile.get("personal_email", ""),
        },
        "email": {
            "message_id": email_data.get("message_id", ""),
            "from_display_name": email_data.get("from_display_name", ""),
            "from_email": email_data.get("from_email", ""),
            "parsed_name": email_data.get("parsed_name", ""),
            "parsed_reg": email_data.get("parsed_reg", ""),
            "subject": email_data.get("subject", ""),
            "body_preview": email_data.get("body_preview", ""),
        },
        "match_type": email_data.get("match_type", ""),
        "attachments": email_data.get("attachments", []),
    }

    # Create filename with timestamp
    filename = f"match_{timestamp.replace(':', '-').replace('.', '_')}.json"
    match_file = data_dir / filename

    try:
        match_file.write_text(json.dumps(match_data, indent=2))
        print(f"✓ Match logged to: {filename}")
    except Exception as e:
        print(f"Error saving match data: {e}")


def update_state_with_match(state: dict, email_data: dict, match_type: str) -> None:
    """Update in-memory state counters by match type, with size limits."""
    import time as _time

    match_entry = {
        "message_id": email_data.get("message_id", ""),
        "timestamp": _time.time(),
        "from_display_name": email_data.get("from_display_name", ""),
        "from_email": email_data.get("from_email", ""),
        "parsed_name": email_data.get("parsed_name", ""),
        "parsed_reg": email_data.get("parsed_reg", ""),
        "subject": email_data.get("subject", ""),
    }

    if match_type == "CONFIRMED_MATCH":
        state["confirmed_matches"].append(match_entry)
    elif match_type == "POSSIBILITY":
        state["possibilities"].append(match_entry)
    elif match_type == "PARTIAL_MATCH":
        state["partial_matches"].append(match_entry)

    # Keep only last 100 entries per category to prevent unlimited growth
    for key in ("confirmed_matches", "possibilities", "partial_matches"):
        if len(state[key]) > 100:
            state[key] = state[key][-100:]


__all__ = [
    "load_state",
    "save_state",
    "save_profile",
    "log_match_to_data",
    "update_state_with_match",
]

