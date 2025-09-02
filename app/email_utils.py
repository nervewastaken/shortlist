"""Email-related helper utilities for parsing and extraction.

This module centralizes small helpers used by the runner to keep the
main control flow lean and readable.
"""

from __future__ import annotations

import base64
import re
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Iterable, Tuple

# VIT reg-no pattern, e.g., 22BCE2382
REG_RE = re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE)

# Phrases to strip from display names (common in list/forwarded mail)
VIA_CLAUSES: tuple[str, ...] = (
    r"\s+via\s+.*$",                # "via Something"
    r"\s+\(via\s+.*\)$",            # "(via Something)"
    r"\s*[-–]\s*Google\s+Groups$",  # "- Google Groups"
)


def header(headers: Iterable[dict], key: str) -> str:
    """Return a header value from a list of Gmail header dicts."""
    for h in headers or []:
        if h.get("name", "").lower() == key.lower():
            return h.get("value", "")
    return ""


def decode_display_name(raw: str) -> str:
    """Decode RFC2047-encoded display names and trim whitespace."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return str(raw).strip()


def clean_display_name(name: str) -> str:
    """Remove routing decorations and extra whitespace from a display name."""
    if not name:
        return ""
    out = str(name).strip()
    for pat in VIA_CLAUSES:
        out = re.sub(pat, "", out, flags=re.IGNORECASE).strip()
    # Remove extra quotes
    out = out.strip("'\" ").strip()
    # Collapse whitespace
    out = re.sub(r"\s{2,}", " ", out)
    return out


def parse_from_header(from_value: str) -> Tuple[str, str]:
    """Return a cleaned display name and email address from a From header."""
    raw_name, addr = parseaddr(from_value or "")
    name = decode_display_name(raw_name)
    name = clean_display_name(name)
    return name, addr


def split_name_and_reg(display_name: str) -> Tuple[str, str]:
    """Extract reg number from display name; return (name, reg)."""
    if not display_name:
        return "", ""
    m = REG_RE.search(display_name)
    reg = m.group(0).upper() if m else ""
    name = display_name
    if reg:
        name = re.sub(re.escape(reg), "", name, flags=re.IGNORECASE).strip()
    # Remove any trailing commas or stray separators
    name = re.sub(r"[,\-–]+$", "", name).strip()
    name = re.sub(r"\s{2,}", " ", name)
    return name, reg


def extract_text(payload: dict) -> str:
    """Extract a human-readable text body from a Gmail message payload."""
    # Prefer text/plain parts
    if "parts" in payload:
        for p in payload["parts"]:
            if p.get("mimeType", "").startswith("text/plain"):
                data = p.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode(errors="ignore")
    data = payload.get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode(errors="ignore")
    return ""


__all__ = [
    "REG_RE",
    "VIA_CLAUSES",
    "header",
    "decode_display_name",
    "clean_display_name",
    "parse_from_header",
    "split_name_and_reg",
    "extract_text",
]

