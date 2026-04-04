"""
LeechBot — Main Entry Point
============================
Downloads files from source channels, embeds thumbnail + metadata,
renames with prefix, uploads to destination channel.

Usage:
  python3 main.py

Required env vars (in .env):
  BOT_TOKEN      Telegram bot token
  ADMIN_IDS      Comma-separated admin IDs
  MONGO_URL      MongoDB connection string
  MONGO_DB_NAME  MongoDB DB name (default: leech_bot)
  DOWNLOAD_DIR   Temp dir (default: /tmp/leech)
"""

import atexit
import datetime
import os
import signal
import sys
import traceback

import requests

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_IDS, MONGO_URL, DOWNLOAD_DIR, log
from database import all_users
import state

from commands_admin import (
    start_command, commands_command,
    adduser_command, removeuser_command,
    listusers_command, userinfo_command,
    toggleuser_command, stats_command,
    broadcast_command,
)
from commands_user import (
    myinfo_command,
    setsource_command, removesource_command,
    setchannel_command,
    setprefix_command, removeprefix_command,
    setcaption_command, resetcaption_command,
    setthumb_command, removethumb_command,
)
from handlers import handle_channel_post, handle_thumb_photo


# ══════════════════════════════════════════════════════════════
# SYNC NOTIFIER
# ══════════════════════════════════════════════════════════════

def _sync_notify(text: str):
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for admin_id in ADMIN_IDS:
        try:
            requests.post(url, data={
                "chat_id": admin_id, "text": text, "parse_mode": "HTML",
            }, timeout=10)
        except Exception as exc:
            log.warning("Sync notify failed: %s", exc)


def _offline_msg(reason: str, extra: str = "") -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    return (
        f"⚠️ <b>LeechBot Offline</b>\n\n"
        f"🕐 Time: {now} UTC\n"
        f"❗ Reason: <b>{reason}</b>\n"
        f"📦 Session posts: {state.stats.get('total', 0)}\n"
        f"{('📋 ' + extra + '\n') if extra else ''}"
        f"Restart: <code>systemctl restart leechbot</code>"
    )


# ══════════════════════════════════════════════════════════════
# STARTUP / SHUTDOWN
# ══════════════════════════════════════════════════════════════

async def on_startup(app):
    state.bot_app = app
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    users  = await all_users()
    active = [u for u in users if u.get("active")]
    now    = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    _sync_notify(
        f"✅ <b>LeechBot Online</b>\n\n"
        f"🕐 Started: {now} UTC\n"
        f"👥 Users: {len(active)} active / {len(users)} total\n"
        f"📁 Temp dir: <code>{DOWNLOAD_DIR}</code>\n\n"
        f"Bot is ready! 🚀"
    )
    log.info("✅ LeechBot started. %d active / %d total users", len(active), len(users))


async def on_shutdown(app=None):
    global _notified_offline
    _notified_offline = True
    _sync_notify(_offline_msg("Graceful Shutdown"))
    log.info("⚠️ LeechBot shutting down.")


# ══════════════════════════════════════════════════════════════
# SIGNAL / CRASH HANDLERS
# ══════════════════════════════════════════════════════════════

_signal_names = {
    signal.SIGTERM: "SIGTERM (systemctl stop)",
    signal.SIGINT:  "SIGINT (Ctrl+C)",
}

def _make_signal_handler(name):
    def _h(signum, frame):
        log.warning("🔴 %s received", name)
        _sync_notify(_offline_msg(name))
        sys.exit(0)
    return _h

for _sig, _name in _signal_names.items():
    try:
        signal.signal(_sig, _make_signal_handler(_name))
    except (OSError, ValueError):
        pass

_orig_excepthook = sys.excepthook

def _excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        _orig_excepthook(exc_type, exc_value, exc_tb)
        return
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.critical("💥 Uncaught exception:\n%s", tb)
    _sync_notify(_offline_msg("Crash", extra=f"{exc_type.__name__}: {str(exc_value)[:200]}"))
    _orig_excepthook(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook

_notified_offline = False

def _atexit():
    global _notified_offline
    if _notified_offline:
        return
    _notified_offline = True
    _sync_notify(_offline_msg("Process Exit"))

atexit.register(_atexit)


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not BOT_TOKEN:
        log.error("BOT_TOKEN is not set. Exiting.")
        sys.exit(1)
    if not MONGO_URL:
        log.warning("⚠️  MONGO_URL not set — configs will not persist!")
    if not ADMIN_IDS:
        log.warning("⚠️  ADMIN_IDS not set — all commands are unrestricted!")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .read_timeout(300)        # 5 min — for large file downloads
        .write_timeout(300)       # 5 min — for large file uploads
        .connect_timeout(60)
        .pool_timeout(300)
        .build()
    )
    state.bot_app = app

    # ── General ────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",         start_command))
    app.add_handler(CommandHandler("commands",      commands_command))

    # ── Admin ──────────────────────────────────────────────────
    app.add_handler(CommandHandler("adduser",       adduser_command))
    app.add_handler(CommandHandler("removeuser",    removeuser_command))
    app.add_handler(CommandHandler("listusers",     listusers_command))
    app.add_handler(CommandHandler("userinfo",      userinfo_command))
    app.add_handler(CommandHandler("toggleuser",    toggleuser_command))
    app.add_handler(CommandHandler("stats",         stats_command))
    app.add_handler(CommandHandler("broadcast",     broadcast_command))

    # ── User config ────────────────────────────────────────────
    app.add_handler(CommandHandler("myinfo",        myinfo_command))
    app.add_handler(CommandHandler("setsource",     setsource_command))
    app.add_handler(CommandHandler("removesource",  removesource_command))
    app.add_handler(CommandHandler("setchannel",    setchannel_command))
    app.add_handler(CommandHandler("setprefix",     setprefix_command))
    app.add_handler(CommandHandler("removeprefix",  removeprefix_command))
    app.add_handler(CommandHandler("setcaption",    setcaption_command))
    app.add_handler(CommandHandler("resetcaption",  resetcaption_command))
    app.add_handler(CommandHandler("setthumb",      setthumb_command))
    app.add_handler(CommandHandler("removethumb",   removethumb_command))

    # ── Thumbnail photo capture ────────────────────────────────
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        handle_thumb_photo,
    ))

    # ── Channel post listener ──────────────────────────────────
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & ~filters.UpdateType.EDITED,
        handle_channel_post,
    ))

    log.info("🤖 LeechBot starting…")
    try:
        app.run_polling(drop_pending_updates=True)
    except Exception as exc:
        tb = traceback.format_exc()
        log.critical("💥 run_polling crashed: %s\n%s", exc, tb)
        _sync_notify(_offline_msg("run_polling Crashed", extra=f"{type(exc).__name__}: {str(exc)[:200]}"))
        _notified_offline = True
        raise
    finally:
        _notified_offline = True
