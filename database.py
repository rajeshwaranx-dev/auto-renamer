"""
database.py — MongoDB CRUD. Duplicate expiry: 10 minutes.
"""
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, MONGO_DB, log

_client = None
_db     = None
DUPLICATE_EXPIRY_MINUTES = 10

def _get_db():
    global _client, _db
    if _db is None:
        if not MONGO_URL: log.warning("MONGO_URL not set"); return None
        _client = AsyncIOMotorClient(MONGO_URL)
        _db     = _client[MONGO_DB]
    return _db

async def get_user(user_id: int) -> dict | None:
    db = _get_db()
    if db is None: return None
    return await db.users.find_one({"user_id": user_id})

async def all_users() -> list[dict]:
    db = _get_db()
    if db is None: return []
    return await db.users.find().to_list(None)

async def active_users() -> list[dict]:
    db = _get_db()
    if db is None: return []
    return await db.users.find({"active": True}).to_list(None)

async def add_user(user_id: int, name: str) -> bool:
    db = _get_db()
    if db is None: return False
    if await db.users.find_one({"user_id": user_id}): return False
    await db.users.insert_one({
        "user_id":           user_id,
        "name":              name,
        "active":            True,
        "source_channels":   [],
        "dest_channel":      None,
        "file_prefix":       "",
        "strip_words":       "",
        "caption_template":  "",
        "thumb":             None,
        "send_mode":         "Document",
        "dump_channel":      None,
        "metadata_title":    "",
        "audio_track_title": "",
        "added_at":          datetime.datetime.utcnow().isoformat(),
        "stats":             {"total": 0, "failed": 0},
    })
    return True

async def remove_user(user_id: int) -> bool:
    db = _get_db()
    if db is None: return False
    r = await db.users.delete_one({"user_id": user_id})
    return r.deleted_count > 0

async def toggle_user(user_id: int) -> bool | None:
    db = _get_db()
    if db is None: return None
    user = await db.users.find_one({"user_id": user_id})
    if not user: return None
    new_state = not user.get("active", True)
    await db.users.update_one({"user_id": user_id}, {"$set": {"active": new_state}})
    return new_state

async def update_user(user_id: int, **kwargs) -> None:
    db = _get_db()
    if db is None: return
    await db.users.update_one({"user_id": user_id}, {"$set": kwargs})

async def add_source_channel(user_id: int, channel_id: str) -> bool:
    db = _get_db()
    if db is None: return False
    user = await db.users.find_one({"user_id": user_id})
    if not user: return False
    sources = user.get("source_channels") or []
    if channel_id in sources: return False
    sources.append(channel_id)
    await db.users.update_one({"user_id": user_id}, {"$set": {"source_channels": sources}})
    return True

async def remove_source_channel(user_id: int, channel_id: str) -> bool:
    db = _get_db()
    if db is None: return False
    user = await db.users.find_one({"user_id": user_id})
    if not user: return False
    sources = user.get("source_channels") or []
    if channel_id not in sources: return False
    sources.remove(channel_id)
    await db.users.update_one({"user_id": user_id}, {"$set": {"source_channels": sources}})
    return True

async def increment_stats(user_id: int, failed: bool = False) -> None:
    db = _get_db()
    if db is None: return
    key = "stats.failed" if failed else "stats.total"
    await db.users.update_one({"user_id": user_id}, {"$inc": {key: 1}})

async def users_for_source(channel_id: str) -> list[dict]:
    db = _get_db()
    if db is None: return []
    return await db.users.find({
        "active": True, "source_channels": channel_id
    }).to_list(None)

# ── Duplicate detection — 10 minute expiry ─────────────────────

async def is_duplicate(user_id: int, file_id: str) -> bool:
    """
    True if file_id was processed by this user in last 10 minutes.
    Uses Python datetime comparison (no MongoDB TTL index needed).
    """
    db = _get_db()
    if db is None: return False

    # Cutoff = exactly 10 minutes ago in UTC
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=DUPLICATE_EXPIRY_MINUTES)

    result = await db.processed.find_one({
        "user_id": user_id,
        "file_id": file_id,
        "ts":      {"$gte": cutoff},
    })
    log.info("Duplicate check | user=%s file_id=%s cutoff=%s result=%s",
             user_id, file_id[:20], cutoff.isoformat(), bool(result))
    return result is not None

async def mark_processed(user_id: int, file_id: str, filename: str) -> None:
    """Record processed file with UTC timestamp."""
    db = _get_db()
    if db is None: return
    now = datetime.datetime.utcnow()
    await db.processed.insert_one({
        "user_id":  user_id,
        "file_id":  file_id,
        "filename": filename,
        "ts":       now,
    })
    log.info("Marked processed | user=%s | file=%s | ts=%s", user_id, filename, now.isoformat())
    # Keep last 5000 per user
    count = await db.processed.count_documents({"user_id": user_id})
    if count > 5000:
        oldest = await db.processed.find(
            {"user_id": user_id}, sort=[("ts", 1)]
        ).limit(count - 5000).to_list(None)
        ids = [d["_id"] for d in oldest]
        if ids:
            await db.processed.delete_many({"_id": {"$in": ids}})

# ── Bot-wide settings ──────────────────────────────────────────

async def get_bot_settings() -> dict:
    db = _get_db()
    if db is None: return {}
    doc = await db.bot_settings.find_one({"_id": "global"})
    return doc or {}

async def set_bot_settings(**kwargs) -> None:
    db = _get_db()
    if db is None: return
    await db.bot_settings.update_one(
        {"_id": "global"}, {"$set": kwargs}, upsert=True)
