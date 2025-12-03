from collections import deque
from threading import Lock
from time import strftime, localtime
from typing import List, Tuple

_buffer: deque[Tuple[int, str]] = deque(maxlen=1000)
_lock = Lock()
_next_id = 1


def log(message: str) -> None:
    """Append a timestamped message to the in-memory buffer and print to stdout."""
    global _next_id
    ts = strftime("%Y-%m-%d %H:%M:%S", localtime())
    line = f"[{ts}] {message}"
    try:
        print(message)
    except Exception:
        # Printing should never break logging storage
        pass
    with _lock:
        _buffer.append((_next_id, line))
        _next_id += 1


def get_recent(limit: int = 200, since_id: int | None = None) -> List[Tuple[int, str]]:
    """Get up to 'limit' recent lines, optionally only those with id > since_id."""
    with _lock:
        items = list(_buffer)
    if since_id is not None:
        items = [item for item in items if item[0] > since_id]
    if limit is not None and limit > 0:
        items = items[-limit:]
    return items


