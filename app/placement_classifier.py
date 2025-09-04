"""Lightweight placement email classifier.

Uses a small GPT model (when OPENAIKEY is set) to decide if an email
is about campus placements/shortlisting/assessments. Falls back to a
simple keyword heuristic if GPT is unavailable.

Whitelist: Certain CDC sender addresses are always accepted.
"""

from __future__ import annotations

import os
import re
from typing import Tuple


# CDC sender whitelist: always treat as placement-related
CDC_SENDER_WHITELIST = {
    "vitianscdc2026@vitstudent.ac.in",
    "krish.verma2022@vitstudent.ac.in"
}


def _looks_like_placement_keyword(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    phrases = [
        "shortlist", "short-listed", "shortlisted", "assessment", "aptitude", "technical interview",
        "hr interview", "drive", "placement", "schedule", "round", "selection process",
        "online test", "coding test", "recruitment", "interview slot", "virtual interview",
    ]
    return any(p in t for p in phrases)


def _contains_company_name(text: str) -> bool:
    if not text:
        return False
    # Very simple heuristic: look for capitalized tokens typical of company names
    # and common suffixes (Labs, Ltd, Pvt, Inc, Technologies, Systems, Hyper, etc.)
    # This is intentionally permissive.
    company_like = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+(?:Labs|Ltd|Pvt|Inc|LLP|Technologies|Systems|Solutions|Hyper|Global|Software|Digital|Networks))?)\b")
    return bool(company_like.search(text))


def is_placement_email(subject: str, body: str, sender_email: str) -> Tuple[bool, str]:
    """Return (is_placement, reason).

    - Always accept CDC whitelist senders.
    - If OPENAIKEY + openai available, ask GPT to classify.
    - Else fallback to simple heuristics.
    """
    sender = (sender_email or "").strip().lower()
    subj = subject or ""
    text = (subject or "") + "\n" + (body or "")

    if sender in CDC_SENDER_WHITELIST:
        return True, f"whitelisted sender: {sender}"

    api_key = os.environ.get("OPENAIKEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key)
            preview = (body or "")
            if len(preview) > 4000:
                preview = preview[:4000]
            system_msg = (
                "You are a strict email classifier for campus placements at VIT.\n"
                "Decide if this email is about a placement/shortlisting/assessment/drive.\n"
                "Heuristics: Look for clear company names and placement-process words.\n"
                "If there is no clear company name or placement context, answer NO.\n"
                "Reply with a single token: YES or NO."
            )
            user_msg = (
                f"Subject: {subj}\n\n"
                f"Body:\n{preview}"
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=3,
            )
            content = (resp.choices[0].message.content or "").strip().upper()
            if "YES" in content and "NO" not in content:
                return True, "gpt: YES"
            return False, f"gpt: {content or 'NO'}"
        except Exception as e:
            # Fall through to heuristic
            pass

    # Heuristic fallback
    if _looks_like_placement_keyword(text) and _contains_company_name(text):
        return True, "heuristic: keywords+company"
    return False, "heuristic: insufficient signals"


__all__ = [
    "CDC_SENDER_WHITELIST",
    "is_placement_email",
]

