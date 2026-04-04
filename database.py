"""
database.py — MongoDB CRUD via Motor (async).

User document schema:
{
  "user_id":          int,
  "name":             str,
  "active":           bool,
  "source_channels":  list[str],
  "dest_channel":     str | None,
  "file_prefix":      str,
  "caption_template": str,
  "thumb":            str | None,   # Telegram file_id of thumbnail
  "thumb_path":       str | None,   # local path of downloaded thumb
  "added_at":         str,
  "stats":            {"total": int, "failed": int}
}
"""

import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, MONGO_DB, log

_client = None
_db     = None


def _get_db():
    global _client, _db
    if _db is None:
        if not MONGO_URL:
            log.warning("MONGO_URL not set — DB calls will fail!")
            return None
        _client = AsyncIOMotorClient(MONGO_URL)
        _db     = _client[MONGO_DB]
    return _db


async def get_user(user_id: int) -> dict | None:
    db = _get_db()
    if db is None:
        return None
    return await db.users.find_one({"user_id": user_id})


async def all_users() -> list[dict]:
    db = _get_db()
    if db is None:
        return []
    return await db.users.find().to_list(None)


async def active_users() -> list[dict]:
    db = _get_db()
    if db is None:
        return []
    return await db.users.find({"active": True}).to_list(None)


async def add_user(user_id: int, name: str) -> bool:
    db = _get_db()
    if db is None:
        return False
    existing = await db.users.find_one({"user_id": user_id})
    if existing:
        return False
    await db.users.insert_one({
        "user_id":          user_id,
        "name":             name,
        "active":           True,
        "source_channels":  [],
        "dest_channel":     None,
        "file_prefix":      "",
        "caption_template": "<b>{newname}</b>",
        "thumb":            None,
        "thumb_path":       None,
        "added_at":         datetime.datetime.utcnow().isoformat(),
        "stats":            {"total": 0, "failed": 0},
    })
    return True


async def remove_user(user_id: int) -> bool:
    db = _get_db()
    if db is None:
        return False
    r = await db.users.delete_one({"user_id": user_id})
    return r.deleted_count > 0


async def toggle_user(user_id: int) -> bool | None:
    db = _get_db()
    if db is None:
        return None
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return None
    new_state = not user.get("active", True)
    await db.users.update_one({"user_id": user_id}, {"$set": {"active": new_state}})
    return new_state


async def update_user(user_id: int, **kwargs) -> None:
    db = _get_db()
    if db is None:
        return
    await db.users.update_one({"user_id": user_id}, {"$set": kwargs})


async def add_source_channel(user_id: int, channel_id: str) -> bool:
    db = _get_db()
    if db is None:
        return False
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return False
    sources = user.get("source_channels") or []
    if channel_id in sources:
        return False
    sources.append(channel_id)
    await db.users.update_one({"user_id": user_id}, {"$set": {"source_channels": sources}})
    return True


async def remove_source_channel(user_id: int, channel_id: str) -> bool:
    db = _get_db()
    if db is None:
        return False
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return False
    sources = user.get("source_channels") or []
    if channel_id not in sources:
        return False
    sources.remove(channel_id)
    await db.users.update_one({"user_id": user_id}, {"$set": {"source_channels": sources}})
    return True


async def increment_stats(user_id: int, failed: bool = False) -> None:
    db = _get_db()
    if db is None:
        return
    if failed:
        await db.users.update_one({"user_id": user_id}, {"$inc": {"stats.failed": 1}})
    else:
        await db.users.update_one({"user_id": user_id}, {"$inc": {"stats.total": 1}})


async def users_for_source(channel_id: str) -> list[dict]:
    db = _get_db()
    if db is None:
        return []
    return await db.users.find({
        "active":          True,
        "source_channels": channel_id,
    }).to_list(None)
