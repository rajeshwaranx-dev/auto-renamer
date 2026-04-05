"""
logger.py — Log channel notifications.

Every significant event is sent to the user's log_channel if set.
Format: clean, readable, with emoji indicators.
"""
from telegram.constants import ParseMode
from config import log
import state


async def _send_log(bot, channel_id: str, text: str, photo=None):
    """Send a message (optionally with photo) to log channel."""
    if not channel_id or not bot:
        return
    try:
        if photo:
            await bot.send_photo(
                chat_id    = channel_id,
                photo      = photo,
                caption    = text,
                parse_mode = ParseMode.HTML,
            )
        else:
            await bot.send_message(
                chat_id    = channel_id,
                text       = text,
                parse_mode = ParseMode.HTML,
            )
    except Exception as e:
        log.warning("Log channel send failed (%s): %s", channel_id, e)


async def log_task_start(bot, user: dict, filename: str, new_name: str, file_size: str):
    ch = user.get("log_channel")
    if not ch: return
    await _send_log(bot, ch,
        f"📥 <b>Task Started</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 Original: <code>{filename}</code>\n"
        f"✏️ Renamed:  <code>{new_name}</code>\n"
        f"📦 Size: {file_size}"
    )


async def log_task_done(bot, user: dict, new_name: str, file_size: str,
                        languages: str, quality: str, thumb=None):
    ch = user.get("log_channel")
    if not ch: return
    text = (
        f"✅ <b>Task Done</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 File: <code>{new_name}</code>\n"
        f"📦 Size: {file_size}\n"
        f"🌐 Language: {languages}\n"
        f"📺 Quality: {quality or '—'}\n"
        f"📤 Dest: <code>{user.get('dest_channel','—')}</code>"
    )
    await _send_log(bot, ch, text, photo=thumb)


async def log_task_failed(bot, user: dict, filename: str, error: str):
    ch = user.get("log_channel")
    if not ch: return
    await _send_log(bot, ch,
        f"❌ <b>Task Failed</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 File: <code>{filename}</code>\n"
        f"⚠️ Error: <code>{error[:300]}</code>"
    )


async def log_duplicate(bot, user: dict, filename: str):
    ch = user.get("log_channel")
    if not ch: return
    await _send_log(bot, ch,
        f"⏭ <b>Duplicate Skipped</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 File: <code>{filename}</code>\n"
        f"ℹ️ Same file_id already processed — skipped."
    )


async def log_bot_start(bot, log_channels: list[str], users_count: int, active_count: int):
    """Notify all unique log channels on bot startup."""
    import datetime
    now  = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = (
        f"✅ <b>LeechBot Online</b>\n\n"
        f"🕐 Started: {now} UTC\n"
        f"👥 Users: {active_count} active / {users_count} total\n"
        f"🔄 Max concurrent: 20\n\n"
        f"Bot is ready! 🚀"
    )
    seen = set()
    for ch in log_channels:
        if ch and ch not in seen:
            seen.add(ch)
            await _send_log(bot, ch, text)


async def log_bot_stop(bot, log_channels: list[str], reason: str, total_posts: int):
    import datetime
    now  = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = (
        f"⚠️ <b>LeechBot Offline</b>\n\n"
        f"🕐 Time: {now} UTC\n"
        f"❗ Reason: <b>{reason}</b>\n"
        f"📦 Session posts: {total_posts}"
    )
    seen = set()
    for ch in log_channels:
        if ch and ch not in seen:
            seen.add(ch)
            await _send_log(bot, ch, text)
