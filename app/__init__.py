"""
App package initializer.

Exports:
- paths: common project paths
- VERSION: app version string
- REGEX: shared compiled patterns (e.g., VIT registration number)
"""

from pathlib import Path
import re

# Semantic version for internal reference
VERSION = "0.1.0"

# Resolve repo root (two levels up from this file)
ROOT = Path(__file__).resolve().parents[1]

# Common file locations used across modules
paths = {
    "root": ROOT,
    "credentials": ROOT / "credentials.json",
    "token": ROOT / "token.json",
    "profile": ROOT / "profile.json",
    "state": ROOT / "state.json",
    "data_dir": ROOT / "data",   # optional
    "logs_dir": ROOT / "logs",   # optional
}

# Ensure optional directories exist
paths["data_dir"].mkdir(exist_ok=True)
paths["logs_dir"].mkdir(exist_ok=True)

# Shared regex patterns
REGEX = {
    # Example VIT pattern: 22BCE2382 (2 digits + 3 letters + 4 digits)
    "vit_regno": re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE),
}

__all__ = ["VERSION", "paths", "REGEX"]
