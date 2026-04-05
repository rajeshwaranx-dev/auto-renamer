"""
settings.py — /settings (user only, no log/strip words)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import get_user, update_user
import state


def _kb(user: dict) -> InlineKeyboardMarkup:
    mode = user.get("send_mode") or "Document"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷 Prefix",        callback_data="set_prefix"),
         InlineKeyboardButton("📝 Caption",       callback_data="set_caption")],
        [InlineKeyboardButton("🖼 Thumbnail",     callback_data="set_thumb"),
         InlineKeyboardButton(f"📄 Mode: {mode}", callback_data="toggle_mode")],
        [InlineKeyboardButton("🗂 Dump Channel",  callback_data="set_dump"),
         InlineKeyboardButton("🎬 Metadata",      callback_data="set_meta_title")],
        [InlineKeyboardButton("🔊 Audio Track",   callback_data="set_audio_title"),
         InlineKeyboardButton("🔄 Reset Caption", callback_data="reset_caption")],
        [InlineKeyboardButton("🗑 Clear Prefix",  callback_data="remove_prefix"),
         InlineKeyboardButton("🗑 Remove Thumb",  callback_data="remove_thumb")],
        [InlineKeyboardButton("❌ Close",         callback_data="close_settings")],
    ])


def _text(user: dict) -> str:
    cap_custom = bool(user.get("caption_template"))
    return (
        f"⚙️ <b>Leech Settings for {user['name']}</b>\n\n"
        f"• <b>Prefix:</b>        <code>{user.get('file_prefix') or 'Not set'}</code>\n"
        f"• <b>Send Mode:</b>     {user.get('send_mode') or 'Document'}\n"
        f"• <b>Thumbnail:</b>     {'Exists ✅' if user.get('thumb') else 'Not set'}\n"
        f"• <b>Caption:</b>       {'Custom ✅' if cap_custom else 'Default'}\n"
        f"• <b>Dump Channel:</b>  <code>{user.get('dump_channel') or 'Not set'}</code>\n"
        f"• <b>Metadata:</b>      {'Custom ✅' if user.get('metadata_title') else 'Default'}\n"
        f"• <b>Audio Track:</b>   {'Custom ✅' if user.get('audio_track_title') else 'Stripped'}\n"
        f"• <b>Dest Channel:</b>  <code>{user.get('dest_channel') or 'Not set'}</code>\n"
        f"• <b>Sources:</b>       {len(user.get('source_channels') or [])}\n\n"
        f"📊 <b>Stats:</b> {user.get('stats',{}).get('total',0)} done | "
        f"{user.get('stats',{}).get('failed',0)} failed"
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id if update.effective_user else None
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(
            "⛔ You are not registered.\nAsk admin to add you with /adduser."); return
    if not user.get("active"):
        await update.message.reply_text("⛔ Your account is disabled."); return

    thumb = user.get("thumb")
    if thumb:
        try:
            await update.message.reply_photo(
                photo=thumb, caption=_text(user),
                parse_mode=ParseMode.HTML, reply_markup=_kb(user))
            return
        except: pass
    await update.message.reply_text(_text(user), parse_mode=ParseMode.HTML, reply_markup=_kb(user))


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data
    user  = await get_user(uid)
    if not user: await query.answer("⛔ Not registered."); return
    await query.answer()

    if data == "close_settings":
        await query.message.delete(); return

    if data == "toggle_mode":
        cur = user.get("send_mode") or "Document"
        new = "Media" if cur == "Document" else "Document"
        await update_user(uid, send_mode=new)
        user["send_mode"] = new
        await _refresh(query, user)
        await query.answer(f"Mode → {new}", show_alert=True); return

    if data == "remove_prefix":
        await update_user(uid, file_prefix="")
        user["file_prefix"] = ""
        await _refresh(query, user)
        await query.answer("Prefix cleared.", show_alert=True); return

    if data == "remove_thumb":
        await update_user(uid, thumb=None)
        user["thumb"] = None
        await _refresh(query, user)
        await query.answer("Thumbnail removed.", show_alert=True); return

    if data == "reset_caption":
        await update_user(uid, caption_template="")
        user["caption_template"] = ""
        await _refresh(query, user)
        await query.answer("Caption reset to default.", show_alert=True); return

    prompts = {
        "set_prefix": ("prefix",
            "🏷 <b>Send your file prefix:</b>\n\n"
            "Examples:\n<code>@AskMovies4</code>\n<code>[AskMovies]</code>\n\n"
            "/cancel to cancel."),

        "set_caption": ("caption",
            "📝 <b>Send your caption template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> — renamed filename\n"
            "<code>{filename}</code> — original filename\n"
            "<code>{name}</code> — name without extension\n"
            "<code>{ext}</code> — file extension\n"
            "<code>{size}</code> — file size\n"
            "<code>{prefix}</code> — your prefix\n"
            "<code>{languages}</code> — detected languages (empty if none)\n"
            "<code>{quality}</code> — detected quality (empty if none)\n\n"
            "<b>Example:</b>\n"
            "<code>{newname}\n\nLanguage : {languages}\nQuality : {quality}\n\n📢 @AskMovies4</code>\n\n"
            "⚠️ Lines with empty Language/Quality auto-hide.\n\n"
            "Send /cancel to cancel."),

        "set_dump": ("dump",
            "🗂 <b>Send dump channel ID:</b>\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "/cancel to cancel."),

        "set_meta_title": ("meta_title",
            "🎬 <b>Send metadata title template:</b>\n\n"
            "Embedded inside file. Visible in VLC → Media Properties.\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> · <code>{name}</code> · <code>{languages}</code>\n"
            "<code>{quality}</code> · <code>{prefix}</code>\n\n"
            "<b>Example:</b>\n"
            "<code>{name} | {languages} | {quality} | @AskMovies4</code>\n\n"
            "/cancel to cancel."),

        "set_audio_title": ("audio_title",
            "🔊 <b>Send audio track title:</b>\n\n"
            "Replaces ALL audio track names inside the file.\n"
            "Visible in VLC → Audio → Audio Track.\n\n"
            "Examples:\n"
            "<code>@AskMovies4</code>\n"
            "<code>Telegram ~ @AskMovies4</code>\n\n"
            "Send <code>-</code> to strip/empty all track names.\n\n"
            "/cancel to cancel."),

        "set_thumb": (None, None),
    }

    if data in prompts:
        mode, prompt = prompts[data]
        if data == "set_thumb":
            state.awaiting_thumb[uid] = True
            await query.message.reply_text(
                "🖼 <b>Send a photo</b> as thumbnail (not as file).",
                parse_mode=ParseMode.HTML)
        else:
            state.awaiting_input[uid] = mode
            await query.message.reply_text(prompt, parse_mode=ParseMode.HTML)


async def _refresh(query, user: dict):
    try:
        if query.message.photo:
            await query.message.edit_caption(caption=_text(user),
                parse_mode=ParseMode.HTML, reply_markup=_kb(user))
        else:
            await query.message.edit_text(_text(user),
                parse_mode=ParseMode.HTML, reply_markup=_kb(user))
    except: pass


async def handle_settings_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    uid  = message.from_user.id
    mode = state.awaiting_input.pop(uid, None)
    if not mode: return
    text = message.text.strip()
    if text == "/cancel":
        await message.reply_text("❌ Cancelled."); return
    user = await get_user(uid)
    if not user: return

    if mode == "dump" and not text.lstrip("-").isdigit():
        await message.reply_text(
            "❌ Invalid ID. Must be like <code>-1001234567890</code>",
            parse_mode=ParseMode.HTML); return

    if mode == "audio_title" and text == "-": text = ""

    db_map = {
        "prefix":      ("file_prefix",        f"✅ Prefix: <code>{text}</code>"),
        "caption":     ("caption_template",    "✅ Caption saved."),
        "dump":        ("dump_channel",        f"✅ Dump channel: <code>{text}</code>"),
        "meta_title":  ("metadata_title",      "✅ Metadata title saved."),
        "audio_title": ("audio_track_title",   f"✅ Audio track: <code>{text or '(stripped)'}</code>"),
    }
    if mode in db_map:
        db_key, reply = db_map[mode]
        await update_user(uid, **{db_key: text})
        await message.reply_text(reply, parse_mode=ParseMode.HTML)

    user = await get_user(uid)
    thumb = user.get("thumb")
    if thumb:
        try:
            await message.reply_photo(photo=thumb, caption=_text(user),
                parse_mode=ParseMode.HTML, reply_markup=_kb(user)); return
        except: pass
    await message.reply_text(_text(user), parse_mode=ParseMode.HTML, reply_markup=_kb(user))
