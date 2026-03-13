from collections import defaultdict
from datetime import datetime

# In-memory store — resets on server restart by design
_sessions: dict[str, list] = defaultdict(list)
MAX_MESSAGES = 20


def add_message(session_id: str, role: str, content: str):
    """role is 'user' or 'assistant'"""
    _sessions[session_id].append({
        "role":    role,
        "content": content,
        "time":    datetime.utcnow().isoformat()
    })
    # Keep only last MAX_MESSAGES
    if len(_sessions[session_id]) > MAX_MESSAGES:
        _sessions[session_id] = _sessions[session_id][-MAX_MESSAGES:]


def get_history(session_id: str) -> list:
    return _sessions.get(session_id, [])


def get_history_summary(session_id: str) -> str:
    """Return last 6 messages as a short text for LLM context."""
    history = get_history(session_id)[-6:]
    if not history:
        return "No previous conversation."
    lines = []
    for msg in history:
        lines.append(f"{msg['role'].upper()}: {msg['content']}")
    return "\n".join(lines)


def clear_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]


