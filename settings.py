"""
settings.py — Clean /settings like LCU bot.
Shows thumbnail + user info + all settings + inline buttons.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import get_user, update_user
import state


def _kb(user: dict) -> InlineKeyboardMarkup:
    """Build inline keyboard — clean 2-column layout."""
    prefix      = (user.get("file_prefix") or "Not set")[:18]
    thumb       = "✅ Exists" if user.get("thumb") else "❌ Not set"
    mode        = user.get("send_mode") or "Document"
    log_ch      = "✅ Set" if user.get("log_channel") else "Not set"
    dump        = "✅ Set" if user.get("dump_channel") else "Not set"
    caption     = "✅ Custom" if (user.get("caption_template") and
                   user.get("caption_template") != "<b>{newname}</b>\n\n🌐 Language : {languages}\n📺 Quality : {quality}") else "Default"
    meta_title  = "✅ Set" if user.get("metadata_title") else "Default"
    audio_track = "✅ Set" if user.get("audio_track_title") else "Stripped"
    strip_words = "✅ Set" if user.get("strip_words") else "Not set"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🏷 Prefix",       callback_data="set_prefix"),
         InlineKeyboardButton(f"📝 Caption",      callback_data="set_caption")],
        [InlineKeyboardButton(f"🖼 Thumbnail",    callback_data="set_thumb"),
         InlineKeyboardButton(f"📄 Mode: {mode}", callback_data="toggle_mode")],
        [InlineKeyboardButton(f"🧹 Strip Words",  callback_data="set_strip_words"),
         InlineKeyboardButton(f"🗂 Dump Channel", callback_data="set_dump")],
        [InlineKeyboardButton(f"📋 Log Channel",  callback_data="set_log_channel"),
         InlineKeyboardButton(f"🎬 Metadata",     callback_data="set_meta_title")],
        [InlineKeyboardButton(f"🔊 Audio Track",  callback_data="set_audio_title"),
         InlineKeyboardButton(f"🔄 Reset Caption",callback_data="reset_caption")],
        [InlineKeyboardButton(f"🗑 Clear Prefix", callback_data="remove_prefix"),
         InlineKeyboardButton(f"🗑 Remove Thumb", callback_data="remove_thumb")],
        [InlineKeyboardButton(f"❌ Close",        callback_data="close_settings")],
    ])


def _settings_text(user: dict) -> str:
    """Build settings summary text — clean like LCU bot."""
    cap_custom = (user.get("caption_template") and
                  "<b>{newname}</b>" not in (user.get("caption_template") or ""))
    sources = user.get("source_channels") or []

    return (
        f"⚙️ <b>Leech Settings for {user['name']}</b>\n\n"
        f"• <b>Prefix:</b> <code>{user.get('file_prefix') or 'Not set'}</code>\n"
        f"• <b>Strip Words:</b> <code>{user.get('strip_words') or 'Not set'}</code>\n"
        f"• <b>Send Mode:</b> {user.get('send_mode') or 'Document'}\n"
        f"• <b>Custom Thumbnail:</b> {'Exists' if user.get('thumb') else 'Not set'}\n"
        f"• <b>Leech Caption:</b> {'Custom' if cap_custom else 'Default'}\n"
        f"• <b>Log Channel:</b> <code>{user.get('log_channel') or 'Not set'}</code>\n"
        f"• <b>Dump Channel:</b> <code>{user.get('dump_channel') or 'Not set'}</code>\n"
        f"• <b>Metadata Title:</b> {'Custom' if user.get('metadata_title') else 'Default'}\n"
        f"• <b>Audio Track:</b> {'Custom' if user.get('audio_track_title') else 'Stripped'}\n"
        f"• <b>Source Channels:</b> {len(sources)}\n"
        f"• <b>Dest Channel:</b> <code>{user.get('dest_channel') or 'Not set'}</code>\n\n"
        f"📊 <b>Stats:</b> "
        f"{user.get('stats',{}).get('total',0)} done | "
        f"{user.get('stats',{}).get('failed',0)} failed"
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id if update.effective_user else None
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⛔ You are not registered.\nAsk admin to add you with /adduser.")
        return
    if not user.get("active"):
        await update.message.reply_text("⛔ Your account is disabled.")
        return

    text = _settings_text(user)
    kb   = _kb(user)
    thumb = user.get("thumb")

    if thumb:
        # Show thumbnail + settings text like LCU bot
        try:
            await update.message.reply_photo(
                photo      = thumb,
                caption    = text,
                parse_mode = ParseMode.HTML,
                reply_markup = kb,
            )
            return
        except Exception:
            pass

    # No thumbnail — plain text
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data
    user  = await get_user(uid)
    if not user:
        await query.answer("⛔ Not registered."); return
    await query.answer()

    # ── One-tap actions ────────────────────────────────────────

    if data == "close_settings":
        await query.message.delete(); return

    if data == "toggle_mode":
        cur = user.get("send_mode") or "Document"
        new = "Media" if cur == "Document" else "Document"
        await update_user(uid, send_mode=new)
        user["send_mode"] = new
        await _refresh_settings(query, user)
        await query.answer(f"Mode → {new}", show_alert=True); return

    if data == "remove_prefix":
        await update_user(uid, file_prefix="")
        user["file_prefix"] = ""
        await _refresh_settings(query, user)
        await query.answer("Prefix cleared.", show_alert=True); return

    if data == "remove_thumb":
        await update_user(uid, thumb=None)
        user["thumb"] = None
        await _refresh_settings(query, user)
        await query.answer("Thumbnail removed.", show_alert=True); return

    if data == "reset_caption":
        default = "<b>{newname}</b>\n\n🌐 Language : {languages}\n📺 Quality : {quality}"
        await update_user(uid, caption_template=default)
        user["caption_template"] = default
        await _refresh_settings(query, user)
        await query.answer("Caption reset to default.", show_alert=True); return

    # ── Prompt inputs ──────────────────────────────────────────

    prompts = {
        "set_prefix": ("prefix",
            "🏷 <b>Send your file prefix:</b>\n\n"
            "Examples:\n<code>@AskMovies4</code>\n<code>[AskMovies]</code>\n\n"
            "Send /cancel to cancel."),

        "set_caption": ("caption",
            "📝 <b>Send your caption template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> — renamed filename\n"
            "<code>{filename}</code> — original filename\n"
            "<code>{name}</code> — name without extension\n"
            "<code>{ext}</code> — file extension\n"
            "<code>{size}</code> — file size\n"
            "<code>{prefix}</code> — your prefix\n"
            "<code>{languages}</code> — detected languages\n"
            "<code>{quality}</code> — detected quality\n"
            "<code>{source}</code> — detected source (WEB-DL etc)\n\n"
            "<b>Example (like image 2):</b>\n"
            "<code>{newname}\n\nLanguage : {languages}\nQuality : {quality}\n\n📢 @AskMovies4</code>\n\n"
            "Send /cancel to cancel."),

        "set_dump": ("dump",
            "🗂 <b>Send dump channel ID:</b>\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "Send /cancel to cancel."),

        "set_log_channel": ("log_channel",
            "📋 <b>Send log channel ID:</b>\n\n"
            "All task events (start, done, failed, duplicate) will be sent there.\n"
            "Make sure bot is admin in that channel.\n\n"
            "Example: <code>-1001234567890</code>\n\n"
            "Send /cancel to cancel."),

        "set_meta_title": ("meta_title",
            "🎬 <b>Send metadata title template:</b>\n\n"
            "Embedded inside file — visible in VLC → Media Properties\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> · <code>{name}</code> · <code>{languages}</code>\n"
            "<code>{quality}</code> · <code>{source}</code> · <code>{prefix}</code>\n\n"
            "<b>Example:</b>\n"
            "<code>{name} | {languages} | {quality} | @AskMovies4</code>\n\n"
            "Send /cancel to cancel."),

        "set_audio_title": ("audio_title",
            "🔊 <b>Send audio track title:</b>\n\n"
            "Replaces all audio track names in the file.\n"
            "VLC → Audio → Audio Track shows this.\n\n"
            "Examples:\n"
            "<code>@AskMovies4</code>\n"
            "<code>Telegram ~ @AskMovies4</code>\n\n"
            "Send <code>-</code> to strip/empty all track names.\n\n"
            "Send /cancel to cancel."),

        "set_strip_words": ("strip_words",
            "🧹 <b>Send words to strip from filenames:</b>\n\n"
            "Separate multiple with comma.\n\n"
            "<b>Example:</b>\n"
            "<code>CineBase, TamilMV, HDHub</code>\n\n"
            "Result:\n"
            "• <code>CineBase Title 2024.mkv</code> → <code>Title 2024.mkv</code>\n\n"
            "Send /cancel to cancel."),

        "set_thumb": (None, None),
    }

    if data in prompts:
        mode, prompt = prompts[data]
        if data == "set_thumb":
            state.awaiting_thumb[uid] = True
            await query.message.reply_text(
                "🖼 <b>Send a photo</b> to set as thumbnail.\n"
                "Send as <b>photo</b>, not as file.",
                parse_mode=ParseMode.HTML)
        else:
            state.awaiting_input[uid] = mode
            await query.message.reply_text(prompt, parse_mode=ParseMode.HTML)


async def _refresh_settings(query, user: dict):
    """Refresh settings message after a change."""
    text = _settings_text(user)
    kb   = _kb(user)
    try:
        # Try to edit caption (if it's a photo message)
        if query.message.photo:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


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

    # Validate channel IDs
    if mode in ("dump", "log_channel") and not text.lstrip("-").isdigit():
        await message.reply_text(
            "❌ Invalid channel ID. Must be like <code>-1001234567890</code>",
            parse_mode=ParseMode.HTML); return

    # Empty audio title
    if mode == "audio_title" and text == "-":
        text = ""

    db_map = {
        "prefix":      ("file_prefix",        f"✅ Prefix set: <code>{text}</code>"),
        "caption":     ("caption_template",    f"✅ Caption saved."),
        "dump":        ("dump_channel",        f"✅ Dump channel: <code>{text}</code>"),
        "log_channel": ("log_channel",         f"✅ Log channel: <code>{text}</code>\n\nMake sure bot is admin there."),
        "meta_title":  ("metadata_title",      f"✅ Metadata title set."),
        "audio_title": ("audio_track_title",   f"✅ Audio track: <code>{text or '(stripped)'}</code>"),
        "strip_words": ("strip_words",         f"✅ Strip words: <code>{text}</code>"),
    }

    if mode in db_map:
        db_key, reply = db_map[mode]
        await update_user(uid, **{db_key: text})
        await message.reply_text(reply, parse_mode=ParseMode.HTML)

    # Show updated settings
    user = await get_user(uid)
    text_s = _settings_text(user)
    kb     = _kb(user)
    thumb  = user.get("thumb")

    if thumb:
        try:
            await message.reply_photo(photo=thumb, caption=text_s,
                parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except: pass
    await message.reply_text(text_s, parse_mode=ParseMode.HTML, reply_markup=kb)
