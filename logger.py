"""
logger.py — All events go to single bot-wide log channel (admin only).
"""
from telegram.constants import ParseMode
from config import log, BOT_LOG_CHANNEL
import state

async def _get_log_channel() -> str:
    """Get bot-wide log channel from DB or fallback to env."""
    try:
        from database import get_bot_settings
        settings = await get_bot_settings()
        return settings.get("log_channel") or BOT_LOG_CHANNEL
    except:
        return BOT_LOG_CHANNEL

async def _send(bot, text: str, photo=None):
    ch = await _get_log_channel()
    if not ch or not bot: return
    try:
        if photo:
            await bot.send_photo(chat_id=ch, photo=photo,
                caption=text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=ch, text=text,
                parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning("Log channel send failed: %s", e)

async def log_task_start(bot, user: dict, filename: str, new_name: str, file_size: str):
    await _send(bot,
        f"📥 <b>Task Started</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 Original: <code>{filename}</code>\n"
        f"✏️ Renamed:  <code>{new_name}</code>\n"
        f"📦 Size: {file_size}"
    )

async def log_task_done(bot, user: dict, new_name: str, file_size: str,
                        languages: str, quality: str, thumb=None):
    lines = [
        f"✅ <b>Task Done</b>\n",
        f"👤 User: <b>{user['name']}</b>",
        f"📄 File: <code>{new_name}</code>",
        f"📦 Size: {file_size}",
    ]
    if languages: lines.append(f"🌐 Language: {languages}")
    if quality:   lines.append(f"📺 Quality: {quality}")
    lines.append(f"📤 Dest: <code>{user.get('dest_channel','—')}</code>")
    await _send(bot, "\n".join(lines), photo=thumb)

async def log_task_failed(bot, user: dict, filename: str, error: str):
    await _send(bot,
        f"❌ <b>Task Failed</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 File: <code>{filename}</code>\n"
        f"⚠️ Error: <code>{error[:300]}</code>"
    )

async def log_duplicate(bot, user: dict, filename: str):
    await _send(bot,
        f"⏭ <b>Duplicate Skipped</b>\n\n"
        f"👤 User: <b>{user['name']}</b>\n"
        f"📄 File: <code>{filename}</code>\n"
        f"ℹ️ Same file processed within last 10 minutes."
    )

async def log_bot_start(bot, users_count: int, active_count: int):
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    await _send(bot,
        f"✅ <b>LeechBot Online</b>\n\n"
        f"🕐 Started: {now} UTC\n"
        f"👥 Users: {active_count} active / {users_count} total\n"
        f"🔄 Max concurrent: 20\n"
        f"⏱ Duplicate expiry: 10 minutes\n\n"
        f"Bot is ready! 🚀"
    )

async def log_bot_stop(bot, reason: str, total_posts: int):
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    await _send(bot,
        f"⚠️ <b>LeechBot Offline</b>\n\n"
        f"🕐 Time: {now} UTC\n"
        f"❗ Reason: <b>{reason}</b>\n"
        f"📦 Session posts: {total_posts}"
    )
