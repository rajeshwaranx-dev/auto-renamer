"""
state.py — Shared mutable state.
"""
import asyncio

bot_app = None

stats = {
    "total": 0, "by_user": {},
    "failed": 0, "downloaded": 0, "uploaded": 0,
}

awaiting_thumb:  dict[int, bool] = {}
awaiting_input:  dict[int, str]  = {}
active_tasks:    dict[int, int]  = {}

# ── Task queue system ──────────────────────────────────────────
# Global queue of (user, message, context) tuples
task_queue: asyncio.Queue = None
# Semaphore — max 20 concurrent tasks across all users
task_semaphore: asyncio.Semaphore = None
# Pending count per user (for display)
pending_count: dict[int, int] = {}

def init_queue():
    global task_queue, task_semaphore
    task_queue     = asyncio.Queue()
    task_semaphore = asyncio.Semaphore(20)
