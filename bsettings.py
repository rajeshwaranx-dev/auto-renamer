"""
bsettings.py — /bsettings (admin only).
Controls: bot-wide log channel + strip words per user.
"""
import functools
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import ADMIN_IDS, log
from database import get_bot_settings, set_bot_settings, all_users, update_user, get_user
import state


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if uid not in ADMIN_IDS:
            await update.message.reply_text("⛔ Admin only.")
            return
        return await func(update, context)
    return wrapper


def _bsettings_text(bot_cfg: dict, users: list) -> str:
    lines = [
        "🔧 <b>Bot Admin Settings</b>\n",
        f"• <b>Log Channel:</b> <code>{bot_cfg.get('log_channel') or 'Not set'}</code>",
        f"• <b>Duplicate Expiry:</b> 10 minutes",
        f"• <b>Max Concurrent Tasks:</b> 20\n",
        "👥 <b>Users & Strip Words:</b>",
    ]
    for u in users:
        status = "🟢" if u.get("active") else "🔴"
        strip  = u.get("strip_words") or "Not set"
        lines.append(f"{status} <b>{u['name']}</b> — Strip: <code>{strip}</code>")
    return "\n".join(lines)


def _bsettings_kb(users: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📋 Set Log Channel", callback_data="bs_set_log")],
        [InlineKeyboardButton("🗑 Clear Log Channel", callback_data="bs_clear_log")],
    ]
    # Strip words button per user
    for u in users:
        rows.append([
            InlineKeyboardButton(
                f"🧹 Strip Words: {u['name']}",
                callback_data=f"bs_strip_{u['user_id']}"
            )
        ])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="bs_close")])
    return InlineKeyboardMarkup(rows)


@admin_only
async def bsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_cfg = await get_bot_settings()
    users   = await all_users()
    text    = _bsettings_text(bot_cfg, users)
    kb      = _bsettings_kb(users)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def bsettings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data

    if uid not in ADMIN_IDS:
        await query.answer("⛔ Admin only."); return
    await query.answer()

    if data == "bs_close":
        await query.message.delete(); return

    if data == "bs_set_log":
        state.awaiting_input[uid] = "bs_log_channel"
        await query.message.reply_text(
            "📋 <b>Send bot-wide log channel ID:</b>\n\n"
            "ALL task events from ALL users will go here.\n"
            "Make sure bot is admin in that channel.\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "/cancel to cancel.",
            parse_mode=ParseMode.HTML); return

    if data == "bs_clear_log":
        await set_bot_settings(log_channel="")
        await query.answer("Log channel cleared.", show_alert=True)
        # Refresh
        bot_cfg = await get_bot_settings()
        users   = await all_users()
        try:
            await query.message.edit_text(
                _bsettings_text(bot_cfg, users),
                parse_mode=ParseMode.HTML,
                reply_markup=_bsettings_kb(users))
        except: pass
        return

    if data.startswith("bs_strip_"):
        target_uid = int(data.replace("bs_strip_", ""))
        state.awaiting_input[uid] = f"bs_strip_{target_uid}"
        target_user = await get_user(target_uid)
        name = target_user["name"] if target_user else str(target_uid)
        current = (target_user or {}).get("strip_words") or "Not set"
        await query.message.reply_text(
            f"🧹 <b>Set strip words for {name}:</b>\n\n"
            f"Current: <code>{current}</code>\n\n"
            "Send comma-separated words to strip from filenames.\n\n"
            "<b>Example:</b>\n"
            "<code>CineBase, TamilMV, HDHub4u</code>\n\n"
            "Send <code>-</code> to clear strip words.\n\n"
            "/cancel to cancel.",
            parse_mode=ParseMode.HTML); return


async def handle_bsettings_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    uid  = message.from_user.id
    if uid not in ADMIN_IDS: return
    mode = state.awaiting_input.get(uid, "")
    if not mode.startswith("bs_"): return
    state.awaiting_input.pop(uid, None)

    text = message.text.strip()
    if text == "/cancel":
        await message.reply_text("❌ Cancelled."); return

    if mode == "bs_log_channel":
        if not text.lstrip("-").isdigit():
            await message.reply_text(
                "❌ Invalid ID. Must be like <code>-1001234567890</code>",
                parse_mode=ParseMode.HTML); return
        await set_bot_settings(log_channel=text)
        await message.reply_text(
            f"✅ <b>Bot log channel set:</b> <code>{text}</code>\n\n"
            "All task events will now go there.",
            parse_mode=ParseMode.HTML)
        return

    if mode.startswith("bs_strip_"):
        target_uid = int(mode.replace("bs_strip_", ""))
        strip_val  = "" if text == "-" else text
        await update_user(target_uid, strip_words=strip_val)
        target_user = await get_user(target_uid)
        name = target_user["name"] if target_user else str(target_uid)
        await message.reply_text(
            f"✅ Strip words for <b>{name}</b>:\n"
            f"<code>{strip_val or '(cleared)'}</code>",
            parse_mode=ParseMode.HTML)

    # Refresh bsettings
    bot_cfg = await get_bot_settings()
    users   = await all_users()
    await message.reply_text(
        _bsettings_text(bot_cfg, users),
        parse_mode=ParseMode.HTML,
        reply_markup=_bsettings_kb(users))
