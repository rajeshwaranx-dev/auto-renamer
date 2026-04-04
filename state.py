"""
state.py — Shared mutable state.
"""

# PTB Application instance
bot_app = None

# Session stats
stats = {
    "total":      0,
    "by_user":    {},
    "failed":     0,
    "downloaded": 0,   # bytes downloaded this session
    "uploaded":   0,   # bytes uploaded this session
}

# Users currently awaiting a thumbnail photo
# { user_id (int): True }
awaiting_thumb: dict[int, bool] = {}

# Active leech tasks per user (to avoid duplicate processing)
# { user_id: count }
active_tasks: dict[int, int] = {}
