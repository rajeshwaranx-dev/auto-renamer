"""
bsettings.py — /bsettings (admin only).
Controls: bot-wide log channel + strip words per user.
"""
import functools
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import ADMIN_IDS, log
from database import (get_bot_settings, set_bot_settings,
                      all_users, update_user, get_user)
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


def _main_text(bot_cfg: dict, users: list) -> str:
    lines = [
        "🔧 <b>Bot Admin Settings</b>\n",
        f"• <b>Log Channel:</b> <code>{bot_cfg.get('log_channel') or 'Not set'}</code>",
        f"• <b>Duplicate Expiry:</b> 10 minutes",
        f"• <b>Max Concurrent:</b> 20 tasks\n",
        "👥 <b>User Strip Words:</b>",
    ]
    for u in users:
        status = "🟢" if u.get("active") else "🔴"
        strip  = u.get("strip_words") or "Not set"
        lines.append(f"{status} <b>{u['name']}</b>: <code>{strip}</code>")
    return "\n".join(lines)


def _main_kb(users: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📋 Set Log Channel",   callback_data="bs_menu_log")],
    ]
    for u in users:
        rows.append([
            InlineKeyboardButton(
                f"🧹 Strip Words: {u['name']}",
                callback_data=f"bs_menu_strip_{u['user_id']}"
            )
        ])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="bs_close")])
    return InlineKeyboardMarkup(rows)


def _log_menu_text(bot_cfg: dict) -> str:
    return (
        f"📋 <b>Log Channel Settings</b>\n\n"
        f"• <b>Current:</b> <code>{bot_cfg.get('log_channel') or 'Not set'}</code>\n\n"
        f"<b>Description:</b> All task events from ALL users "
        f"go to this single channel.\n\n"
        f"Make sure bot is <b>admin</b> in that channel.\n\n"
        f"<b>Format:</b> <code>-1001234567890</code>"
    )


def _log_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change", callback_data="bs_input_log"),
         InlineKeyboardButton("🗑 Clear",  callback_data="bs_clear_log")],
        [InlineKeyboardButton("◀️ Back",   callback_data="bs_back"),
         InlineKeyboardButton("❌ Close",  callback_data="bs_close")],
    ])


def _strip_menu_text(user: dict) -> str:
    return (
        f"🧹 <b>Strip Words for {user['name']}</b>\n\n"
        f"• <b>Current:</b> <code>{user.get('strip_words') or 'Not set'}</code>\n\n"
        f"<b>Description:</b> Words stripped from the START "
        f"of filenames before adding prefix.\n\n"
        f"<b>Format:</b> Comma-separated\n\n"
        f"<b>Example:</b>\n"
        f"<code>ASK, CineBase, TamilMV</code>\n\n"
        f"Result:\n"
        f"<code>ASK Movie Name.mkv</code> → <code>Movie Name.mkv</code>"
    )


def _strip_menu_kb(target_uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change", callback_data=f"bs_input_strip_{target_uid}"),
         InlineKeyboardButton("🗑 Clear",  callback_data=f"bs_clear_strip_{target_uid}")],
        [InlineKeyboardButton("◀️ Back",   callback_data="bs_back"),
         InlineKeyboardButton("❌ Close",  callback_data="bs_close")],
    ])


async def _show_main(update_or_query, is_query=False):
    bot_cfg = await get_bot_settings()
    users   = await all_users()
    text    = _main_text(bot_cfg, users)
    kb      = _main_kb(users)
    if is_query:
        try:
            await update_or_query.message.edit_text(
                text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except: pass
    else:
        await update_or_query.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=kb)


@admin_only
async def bsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_main(update.message, is_query=False)


async def bsettings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data

    if uid not in ADMIN_IDS:
        await query.answer("⛔ Admin only."); return
    await query.answer()

    if data == "bs_close":
        await query.message.delete(); return

    if data == "bs_back":
        await _show_main(query, is_query=True); return

    # Log channel menu
    if data == "bs_menu_log":
        bot_cfg = await get_bot_settings()
        await query.message.edit_text(
            _log_menu_text(bot_cfg),
            parse_mode=ParseMode.HTML,
            reply_markup=_log_menu_kb()); return

    if data == "bs_input_log":
        state.awaiting_input[uid] = "bs_log"
        await query.message.reply_text(
            "📋 <b>Send bot-wide log channel ID:</b>\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "Send /cancel to cancel.",
            parse_mode=ParseMode.HTML); return

    if data == "bs_clear_log":
        await set_bot_settings(log_channel="")
        await query.answer("✅ Log channel cleared.", show_alert=True)
        bot_cfg = await get_bot_settings()
        await query.message.edit_text(
            _log_menu_text(bot_cfg),
            parse_mode=ParseMode.HTML,
            reply_markup=_log_menu_kb()); return

    # Strip words menu
    if data.startswith("bs_menu_strip_"):
        target_uid  = int(data.replace("bs_menu_strip_", ""))
        target_user = await get_user(target_uid)
        if not target_user:
            await query.answer("User not found."); return
        await query.message.edit_text(
            _strip_menu_text(target_user),
            parse_mode=ParseMode.HTML,
            reply_markup=_strip_menu_kb(target_uid)); return

    if data.startswith("bs_input_strip_"):
        target_uid = int(data.replace("bs_input_strip_", ""))
        state.awaiting_input[uid] = f"bs_strip_{target_uid}"
        target_user = await get_user(target_uid)
        name = target_user["name"] if target_user else str(target_uid)
        await query.message.reply_text(
            f"🧹 <b>Send strip words for {name}:</b>\n\n"
            "Comma-separated words to strip from filenames.\n\n"
            "<b>Example:</b>\n"
            "<code>ASK, CineBase, TamilMV</code>\n\n"
            "Send <code>-</code> to clear.\n\n"
            "Send /cancel to cancel.",
            parse_mode=ParseMode.HTML); return

    if data.startswith("bs_clear_strip_"):
        target_uid = int(data.replace("bs_clear_strip_", ""))
        await update_user(target_uid, strip_words="")
        await query.answer("✅ Strip words cleared.", show_alert=True)
        target_user = await get_user(target_uid)
        await query.message.edit_text(
            _strip_menu_text(target_user),
            parse_mode=ParseMode.HTML,
            reply_markup=_strip_menu_kb(target_uid)); return


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

    if mode == "bs_log":
        if not text.lstrip("-").isdigit():
            await message.reply_text(
                "❌ Invalid ID. Must be like <code>-1001234567890</code>",
                parse_mode=ParseMode.HTML); return
        await set_bot_settings(log_channel=text)
        await message.reply_text(
            f"✅ <b>Log channel set:</b> <code>{text}</code>",
            parse_mode=ParseMode.HTML)

    elif mode.startswith("bs_strip_"):
        target_uid = int(mode.replace("bs_strip_", ""))
        strip_val  = "" if text == "-" else text
        await update_user(target_uid, strip_words=strip_val)
        target_user = await get_user(target_uid)
        name = target_user["name"] if target_user else str(target_uid)
        await message.reply_text(
            f"✅ Strip words for <b>{name}</b> set to:\n"
            f"<code>{strip_val or '(cleared)'}</code>",
            parse_mode=ParseMode.HTML)

    # Refresh main bsettings
    await _show_main(message, is_query=False)
