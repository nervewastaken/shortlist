"""Match evaluation logic, separated from the runner control flow.

Keeps the runner readable while consolidating name/email/reg matching.
"""

from __future__ import annotations

import re
from .match_utils import best


def check_name_match(profile_name: str, email_name: str) -> bool:
    """Case-insensitive, order-preserving loose match of profile name in email name."""
    if not profile_name or not email_name:
        return False

    profile_name = profile_name.lower().strip()
    email_name = email_name.lower().strip()

    # Exact match
    if profile_name == email_name:
        return True

    # All profile name words should be present in the email name
    profile_words = set(profile_name.split())
    email_words = set(email_name.split())
    return profile_words.issubset(email_words)


def check_email_match(profile_email: str, email_addr: str) -> bool:
    """Strict case-insensitive equality for email addresses.

    Note: We no longer use email address equality as a positive signal for
    shortlisting. This helper remains for guard checks (e.g., filtering out
    self-sent messages), but should not contribute to match scoring.
    """
    if not profile_email or not email_addr:
        return False
    return profile_email.lower().strip() == email_addr.lower().strip()


def text_contains_name(text: str, name: str) -> bool:
    """Return True if all name words appear in order within the text."""
    if not text or not name:
        return False
    # Normalize whitespace and case
    t = re.sub(r"\s+", " ", text).lower()
    n = re.sub(r"\s+", " ", name).lower().strip()
    if not n:
        return False
    # Require that all name words appear in order (loose match)
    parts = [p for p in n.split(" ") if p]
    idx = 0
    for p in parts:
        found = t.find(p, idx)
        if found == -1:
            return False
        idx = found + len(p)
    return True


def evaluate_match(profile: dict, parsed_name: str, parsed_reg: str, sender_email: str) -> str:
    """Evaluate header-based match using only name and registration number.

    Email address equality is explicitly excluded from positive signals to
    avoid false positives (e.g., self-sent emails or list recipients).
    """
    profile_name = profile.get("name", "")
    profile_reg = profile.get("registration_number", "")

    name_match = check_name_match(profile_name, parsed_name)
    reg_match = bool(profile_reg and parsed_reg and profile_reg.upper() == parsed_reg.upper())
    # Do NOT count email matches as a positive signal
    if name_match and reg_match:
        return "CONFIRMED_MATCH"
    elif name_match:
        return "POSSIBILITY"
    elif reg_match:
        return "PARTIAL_MATCH"
    else:
        return "NO_MATCH"


def evaluate_content_match(profile: dict, subject: str, body: str) -> str:
    """Evaluate content-based match from subject/body.

    Signals considered:
    - Name match is robust to extra whitespace and order
    - Reg number exact pattern match (string contains profile reg)
    Email address presence is intentionally ignored to prevent false positives.
    """
    text = f"{subject}\n{body}" if body else subject or ""

    prof_name = (profile.get("name") or "").strip()
    prof_reg = (profile.get("registration_number") or "").strip()

    name_match = text_contains_name(text, prof_name)
    reg_match = bool(prof_reg) and bool(re.search(re.escape(prof_reg), text, re.IGNORECASE))
    
    if name_match and reg_match:
        return "CONFIRMED_MATCH"
    elif name_match:
        return "POSSIBILITY"
    elif reg_match:
        return "PARTIAL_MATCH"
    return "NO_MATCH"


__all__ = [
    "check_name_match",
    "check_email_match",
    "text_contains_name",
    "evaluate_match",
    "evaluate_content_match",
]
