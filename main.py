import atexit, datetime, os, signal, sys, traceback, asyncio
import requests
from telegram.ext import (ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters)
from config import BOT_TOKEN, ADMIN_IDS, MONGO_URL, DOWNLOAD_DIR, API_ID, API_HASH, SESSION_STRING, log
from database import all_users
import state
from commands_admin import (start_command, commands_command, adduser_command,
    removeuser_command, listusers_command, userinfo_command, toggleuser_command,
    stats_command, broadcast_command)
from commands_user import (myinfo_command, setsource_command, removesource_command,
    setchannel_command, setprefix_command, removeprefix_command, setcaption_command,
    resetcaption_command, setthumb_command, removethumb_command, setlogchannel_command)
from handlers import handle_channel_post, handle_thumb_photo, init_pyro_client, stop_pyro_client, queue_worker
from settings import settings_command, settings_callback, handle_settings_input
from logger import log_bot_start, log_bot_stop

def _sync_notify(text):
    if not BOT_TOKEN or not ADMIN_IDS: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for admin_id in ADMIN_IDS:
        try: requests.post(url, data={"chat_id":admin_id,"text":text,"parse_mode":"HTML"}, timeout=10)
        except Exception as exc: log.warning("Notify failed: %s", exc)

def _offline_msg(reason, extra=""):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    return (f"⚠️ <b>LeechBot Offline</b>\n\n🕐 {now} UTC\n❗ <b>{reason}</b>\n"
            f"📦 Posts: {state.stats.get('total',0)}\n"
            f"{('📋 '+extra+chr(10)) if extra else ''}"
            f"Restart: <code>systemctl restart leechbot</code>")

async def on_startup(app):
    state.bot_app = app
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    state.init_queue()

    # Start queue workers
    for _ in range(3):
        asyncio.create_task(queue_worker())
    log.info("Queue workers started (max 20 concurrent)")

    # Init Pyrogram
    if API_ID and API_HASH:
        await init_pyro_client(api_id=API_ID, api_hash=API_HASH,
            session_string=SESSION_STRING,
            bot_token=BOT_TOKEN if not SESSION_STRING else "")
    else:
        log.warning("API_ID/API_HASH not set")

    users  = await all_users()
    active = [u for u in users if u.get("active")]

    # Notify all log channels on startup
    log_channels = list({u.get("log_channel") for u in users if u.get("log_channel")})
    await log_bot_start(app.bot, log_channels, len(users), len(active))

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    _sync_notify(
        f"✅ <b>LeechBot Online</b>\n\n"
        f"🕐 {now} UTC\n"
        f"👥 {len(active)} active / {len(users)} total\n"
        f"🔄 Max concurrent: 20\n\n"
        f"Bot ready! 🚀"
    )
    log.info("LeechBot started. %d active / %d total", len(active), len(users))

async def on_shutdown(app=None):
    global _notified_offline
    _notified_offline = True
    # Notify log channels
    try:
        users = await all_users()
        log_channels = list({u.get("log_channel") for u in users if u.get("log_channel")})
        if app and log_channels:
            await log_bot_stop(app.bot, log_channels, "Graceful Shutdown", state.stats.get("total",0))
    except: pass
    await stop_pyro_client()
    _sync_notify(_offline_msg("Graceful Shutdown"))

_signal_names = {signal.SIGTERM:"SIGTERM", signal.SIGINT:"SIGINT"}
def _make_sig(name):
    def _h(s, f): _sync_notify(_offline_msg(name)); sys.exit(0)
    return _h
for _s, _n in _signal_names.items():
    try: signal.signal(_s, _make_sig(_n))
    except: pass

_orig = sys.excepthook
def _hook(t, v, tb):
    if issubclass(t, (KeyboardInterrupt, SystemExit)): _orig(t, v, tb); return
    _sync_notify(_offline_msg("Crash", f"{t.__name__}: {str(v)[:200]}"))
    _orig(t, v, tb)
sys.excepthook = _hook

_notified_offline = False
def _atexit():
    global _notified_offline
    if _notified_offline: return
    _notified_offline = True
    _sync_notify(_offline_msg("Process Exit"))
atexit.register(_atexit)

if __name__ == "__main__":
    if not BOT_TOKEN: log.error("BOT_TOKEN not set"); sys.exit(1)

    app = (ApplicationBuilder().token(BOT_TOKEN)
        .post_init(on_startup).post_shutdown(on_shutdown)
        .read_timeout(600).write_timeout(600)
        .connect_timeout(60).pool_timeout(600).build())
    state.bot_app = app

    app.add_handler(CommandHandler("start",          start_command))
    app.add_handler(CommandHandler("commands",       commands_command))
    app.add_handler(CommandHandler("adduser",        adduser_command))
    app.add_handler(CommandHandler("removeuser",     removeuser_command))
    app.add_handler(CommandHandler("listusers",      listusers_command))
    app.add_handler(CommandHandler("userinfo",       userinfo_command))
    app.add_handler(CommandHandler("toggleuser",     toggleuser_command))
    app.add_handler(CommandHandler("stats",          stats_command))
    app.add_handler(CommandHandler("broadcast",      broadcast_command))
    app.add_handler(CommandHandler("myinfo",         myinfo_command))
    app.add_handler(CommandHandler("setsource",      setsource_command))
    app.add_handler(CommandHandler("removesource",   removesource_command))
    app.add_handler(CommandHandler("setchannel",     setchannel_command))
    app.add_handler(CommandHandler("setprefix",      setprefix_command))
    app.add_handler(CommandHandler("removeprefix",   removeprefix_command))
    app.add_handler(CommandHandler("setcaption",     setcaption_command))
    app.add_handler(CommandHandler("resetcaption",   resetcaption_command))
    app.add_handler(CommandHandler("setthumb",       setthumb_command))
    app.add_handler(CommandHandler("removethumb",    removethumb_command))
    app.add_handler(CommandHandler("setlogchannel",  setlogchannel_command))
    app.add_handler(CommandHandler("settings",       settings_command))

    app.add_handler(CallbackQueryHandler(settings_callback))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_thumb_photo))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_settings_input))
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & ~filters.UpdateType.EDITED,
        handle_channel_post))

    log.info("LeechBot starting...")
    try:
        app.run_polling(drop_pending_updates=True)
    except Exception as exc:
        _sync_notify(_offline_msg("Crash", f"{type(exc).__name__}: {str(exc)[:200]}"))
        _notified_offline = True; raise
    finally:
        _notified_offline = True
