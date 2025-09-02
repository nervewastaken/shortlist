"""
Utilities for working with match types and their priority.

Order (best to worst):
- CONFIRMED_MATCH
- POSSIBILITY
- PARTIAL_MATCH
- NO_MATCH
"""

from typing import Iterable

# Define the canonical ordering once
MATCH_HIERARCHY: tuple[str, ...] = (
    "CONFIRMED_MATCH",
    "POSSIBILITY",
    "PARTIAL_MATCH",
    "NO_MATCH",
)


def rank(match_type: str) -> int:
    """Return the rank (lower is better) for a match type.

    Unknown types are treated as worst possible.
    """
    try:
        return MATCH_HIERARCHY.index(match_type)
    except ValueError:
        return len(MATCH_HIERARCHY)


def best(*match_types: str) -> str:
    """Return the strongest match type among the given values.

    Falls back to 'NO_MATCH' if input is empty or only falsey values.
    """
    candidates = [m for m in match_types if m]
    if not candidates:
        return "NO_MATCH"
    return min(candidates, key=rank)


def best_of(iterable: Iterable[str]) -> str:
    """Return the strongest match type from an iterable.

    Convenience wrapper around `best` for iterables.
    """
    return best(*list(iterable))


def is_better(a: str, b: str) -> bool:
    """Return True if a is a stronger match than b."""
    return rank(a) < rank(b)


__all__ = [
    "MATCH_HIERARCHY",
    "rank",
    "best",
    "best_of",
    "is_better",
]

