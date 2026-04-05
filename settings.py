"""
settings.py — /settings inline keyboard menu.

Allows users to configure everything from Telegram itself:
  • Prefix
  • Caption
  • Thumbnail
  • Send mode (Document / Media)
  • Dump channel
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from database import get_user, update_user
import state

# ── Settings menu builder ──────────────────────────────────────

def _settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    prefix    = user.get("file_prefix") or "Not set"
    thumb     = "✅ Set" if user.get("thumb") else "❌ Not set"
    mode      = user.get("send_mode") or "Document"
    dump      = user.get("dump_channel") or "Not set"
    caption   = "✅ Custom" if user.get("caption_template") and user.get("caption_template") != "<b>{newname}</b>" else "Default"

    buttons = [
        [InlineKeyboardButton(f"🏷 Prefix: {prefix[:20]}", callback_data="set_prefix")],
        [InlineKeyboardButton(f"📝 Caption: {caption}", callback_data="set_caption")],
        [InlineKeyboardButton(f"🖼 Thumbnail: {thumb}", callback_data="set_thumb")],
        [
            InlineKeyboardButton(f"📄 Mode: {mode}", callback_data="toggle_mode"),
            InlineKeyboardButton(f"🗂 Dump: {dump[:15]}", callback_data="set_dump"),
        ],
        [InlineKeyboardButton("🔄 Reset Caption", callback_data="reset_caption")],
        [InlineKeyboardButton("🗑 Remove Prefix", callback_data="remove_prefix"),
         InlineKeyboardButton("🗑 Remove Thumb", callback_data="remove_thumb")],
        [InlineKeyboardButton("❌ Close", callback_data="close_settings")],
    ]
    return InlineKeyboardMarkup(buttons)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id if update.effective_user else None
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⛔ You are not registered.")
        return
    if not user.get("active"):
        await update.message.reply_text("⛔ Your account is disabled.")
        return

    text = (
        f"⚙️ <b>Settings — {user['name']}</b>\n\n"
        f"🏷 <b>Prefix:</b> <code>{user.get('file_prefix') or '—'}</code>\n"
        f"📝 <b>Caption:</b> {'Custom' if user.get('caption_template') and user.get('caption_template') != '<b>{newname}</b>' else 'Default'}\n"
        f"🖼 <b>Thumbnail:</b> {'✅ Set' if user.get('thumb') else '❌ Not set'}\n"
        f"📄 <b>Send Mode:</b> {user.get('send_mode') or 'Document'}\n"
        f"🗂 <b>Dump Channel:</b> <code>{user.get('dump_channel') or '—'}</code>\n\n"
        f"Tap a button below to change settings:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                    reply_markup=_settings_keyboard(user))


# ── Callback handler ───────────────────────────────────────────

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = query.from_user.id
    data   = query.data
    user   = await get_user(uid)

    if not user:
        await query.answer("⛔ Not registered.")
        return

    await query.answer()

    # ── Close ──────────────────────────────────────────────────
    if data == "close_settings":
        await query.message.delete()
        return

    # ── Toggle send mode ───────────────────────────────────────
    if data == "toggle_mode":
        current = user.get("send_mode") or "Document"
        new_mode = "Media" if current == "Document" else "Document"
        await update_user(uid, send_mode=new_mode)
        user["send_mode"] = new_mode
        await query.edit_message_reply_markup(_settings_keyboard(user))
        await query.answer(f"Mode set to {new_mode}", show_alert=True)
        return

    # ── Remove prefix ──────────────────────────────────────────
    if data == "remove_prefix":
        await update_user(uid, file_prefix="")
        user["file_prefix"] = ""
        await query.edit_message_reply_markup(_settings_keyboard(user))
        await query.answer("Prefix removed.", show_alert=True)
        return

    # ── Remove thumbnail ───────────────────────────────────────
    if data == "remove_thumb":
        await update_user(uid, thumb=None)
        user["thumb"] = None
        await query.edit_message_reply_markup(_settings_keyboard(user))
        await query.answer("Thumbnail removed.", show_alert=True)
        return

    # ── Reset caption ──────────────────────────────────────────
    if data == "reset_caption":
        await update_user(uid, caption_template="<b>{newname}</b>")
        user["caption_template"] = "<b>{newname}</b>"
        await query.edit_message_reply_markup(_settings_keyboard(user))
        await query.answer("Caption reset to default.", show_alert=True)
        return

    # ── Set prefix (prompt) ────────────────────────────────────
    if data == "set_prefix":
        state.awaiting_input[uid] = "prefix"
        await query.message.reply_text(
            "🏷 <b>Send your new prefix:</b>\n\n"
            "Example: <code>@AskMovies4</code> or <code>[AskMovies]</code>\n\n"
            "Send /cancel to cancel.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Set caption (prompt) ───────────────────────────────────
    if data == "set_caption":
        state.awaiting_input[uid] = "caption"
        await query.message.reply_text(
            "📝 <b>Send your caption template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> · <code>{filename}</code> · "
            "<code>{name}</code> · <code>{ext}</code> · "
            "<code>{size}</code> · <code>{prefix}</code>\n\n"
            "Example:\n"
            "<code>🎬 {newname}\n📦 {size}\n\n📢 @AskMovies4</code>\n\n"
            "Send /cancel to cancel.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Set dump channel (prompt) ──────────────────────────────
    if data == "set_dump":
        state.awaiting_input[uid] = "dump"
        await query.message.reply_text(
            "🗂 <b>Send your dump channel ID:</b>\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "Send /cancel to cancel.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Set thumbnail (prompt) ─────────────────────────────────
    if data == "set_thumb":
        state.awaiting_thumb[uid] = True
        await query.message.reply_text(
            "🖼 <b>Send a photo</b> to use as thumbnail.\n"
            "Send as photo (not file).",
            parse_mode=ParseMode.HTML,
        )
        return


# ── Text input handler (for prefix / caption / dump) ──────────

async def handle_settings_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    uid  = message.from_user.id
    mode = state.awaiting_input.pop(uid, None)
    if not mode:
        return

    text = message.text.strip()

    if text == "/cancel":
        await message.reply_text("❌ Cancelled.")
        return

    user = await get_user(uid)
    if not user:
        return

    if mode == "prefix":
        await update_user(uid, file_prefix=text)
        await message.reply_text(
            f"✅ Prefix set: <code>{text}</code>\n\n"
            f"Example: <code>{text} Movie.Name.2024.mkv</code>",
            parse_mode=ParseMode.HTML,
        )
    elif mode == "caption":
        await update_user(uid, caption_template=text)
        await message.reply_text(
            f"✅ Caption saved:\n\n<code>{text}</code>",
            parse_mode=ParseMode.HTML,
        )
    elif mode == "dump":
        if not text.lstrip("-").isdigit():
            await message.reply_text("❌ Invalid channel ID. Must be like <code>-1001234567890</code>", parse_mode=ParseMode.HTML)
            return
        await update_user(uid, dump_channel=text)
        await message.reply_text(
            f"✅ Dump channel set: <code>{text}</code>",
            parse_mode=ParseMode.HTML,
        )

    # Show updated settings
    user = await get_user(uid)
    await message.reply_text(
        f"⚙️ <b>Updated Settings</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(user),
    )
