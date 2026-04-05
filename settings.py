"""
settings.py — /settings inline menu with full control.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import get_user, update_user
import state

def _kb(user):
    prefix      = (user.get("file_prefix") or "Not set")[:18]
    thumb       = "✅ Set" if user.get("thumb") else "❌ Not set"
    mode        = user.get("send_mode") or "Document"
    dump        = (user.get("dump_channel") or "Not set")[:15]
    caption     = "✅ Custom" if (user.get("caption_template") and user.get("caption_template") != "<b>{newname}</b>") else "Default"
    meta_title  = "✅ Set" if user.get("metadata_title") else "Default"
    audio_track = "✅ Set" if user.get("audio_track_title") else "Stripped"
    strip_words = "✅ Set" if user.get("strip_words") else "Not set"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🏷 Prefix: {prefix}", callback_data="set_prefix")],
        [InlineKeyboardButton(f"📝 Caption: {caption}", callback_data="set_caption")],
        [InlineKeyboardButton(f"🖼 Thumbnail: {thumb}", callback_data="set_thumb")],
        [InlineKeyboardButton(f"📄 Mode: {mode}", callback_data="toggle_mode"),
         InlineKeyboardButton(f"🗂 Dump: {dump}", callback_data="set_dump")],
        [InlineKeyboardButton(f"🎬 Metadata Title: {meta_title}", callback_data="set_meta_title")],
        [InlineKeyboardButton(f"🔊 Audio Track: {audio_track}", callback_data="set_audio_title")],
        [InlineKeyboardButton(f"🧹 Strip Words: {strip_words}", callback_data="set_strip_words")],
        [InlineKeyboardButton("🗑 Clear Prefix", callback_data="remove_prefix"),
         InlineKeyboardButton("🗑 Remove Thumb", callback_data="remove_thumb")],
        [InlineKeyboardButton("🔄 Reset Caption", callback_data="reset_caption"),
         InlineKeyboardButton("🗑 Clear Metadata", callback_data="clear_metadata")],
        [InlineKeyboardButton("❌ Close", callback_data="close_settings")],
    ])


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id if update.effective_user else None
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⛔ You are not registered."); return
    if not user.get("active"):
        await update.message.reply_text("⛔ Disabled."); return

    cap_custom = user.get("caption_template") and user.get("caption_template") != "<b>{newname}</b>"
    text = (
        f"⚙️ <b>Settings — {user['name']}</b>\n\n"
        f"🏷 <b>Prefix:</b>         <code>{user.get('file_prefix') or '—'}</code>\n"
        f"🧹 <b>Strip Words:</b>    <code>{user.get('strip_words') or '—'}</code>\n"
        f"📝 <b>Caption:</b>        {'Custom' if cap_custom else 'Default'}\n"
        f"🖼 <b>Thumbnail:</b>      {'✅ Set' if user.get('thumb') else '❌ Not set'}\n"
        f"📄 <b>Mode:</b>           {user.get('send_mode') or 'Document'}\n"
        f"🗂 <b>Dump Channel:</b>   <code>{user.get('dump_channel') or '—'}</code>\n"
        f"🎬 <b>Metadata Title:</b> <code>{(user.get('metadata_title') or 'Default')[:50]}</code>\n"
        f"🔊 <b>Audio Track:</b>    <code>{user.get('audio_track_title') or 'Stripped (empty)'}</code>\n\n"
        f"<b>Caption/Metadata placeholders:</b>\n"
        f"<code>{{newname}}</code> · <code>{{filename}}</code> · <code>{{name}}</code>\n"
        f"<code>{{ext}}</code> · <code>{{size}}</code> · <code>{{prefix}}</code>\n"
        f"<code>{{languages}}</code> · <code>{{quality}}</code> · <code>{{source}}</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_kb(user))


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data
    user  = await get_user(uid)
    if not user:
        await query.answer("⛔ Not registered."); return
    await query.answer()

    if data == "close_settings":
        await query.message.delete(); return

    if data == "toggle_mode":
        cur = user.get("send_mode") or "Document"
        new = "Media" if cur == "Document" else "Document"
        await update_user(uid, send_mode=new)
        user["send_mode"] = new
        await query.edit_message_reply_markup(_kb(user))
        await query.answer(f"Mode → {new}", show_alert=True); return

    if data == "remove_prefix":
        await update_user(uid, file_prefix="")
        user["file_prefix"] = ""
        await query.edit_message_reply_markup(_kb(user))
        await query.answer("Prefix removed.", show_alert=True); return

    if data == "remove_thumb":
        await update_user(uid, thumb=None)
        user["thumb"] = None
        await query.edit_message_reply_markup(_kb(user))
        await query.answer("Thumbnail removed.", show_alert=True); return

    if data == "reset_caption":
        await update_user(uid, caption_template="<b>{newname}</b>")
        user["caption_template"] = "<b>{newname}</b>"
        await query.edit_message_reply_markup(_kb(user))
        await query.answer("Caption reset.", show_alert=True); return

    if data == "clear_metadata":
        await update_user(uid, metadata_title="", audio_track_title="")
        user.update({"metadata_title":"","audio_track_title":""})
        await query.edit_message_reply_markup(_kb(user))
        await query.answer("Metadata cleared.", show_alert=True); return

    prompts = {
        "set_prefix": ("prefix",
            "🏷 <b>Send your file prefix:</b>\n\n"
            "Example: <code>@AskMovies4</code> or <code>[AskMovies]</code>\n\n/cancel to cancel."),
        "set_caption": ("caption",
            "📝 <b>Send your caption template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> — renamed filename\n"
            "<code>{filename}</code> — original filename\n"
            "<code>{name}</code> — name without ext\n"
            "<code>{ext}</code> — extension\n"
            "<code>{size}</code> — file size\n"
            "<code>{prefix}</code> — your prefix\n"
            "<code>{languages}</code> — detected languages\n"
            "<code>{quality}</code> — detected quality\n"
            "<code>{source}</code> — detected source\n\n"
            "<b>Example:</b>\n"
            "<code>🎬 {newname}\n🌐 {languages} | 📺 {quality}\n📦 {size}\n\n📢 @AskMovies4</code>\n\n"
            "/cancel to cancel."),
        "set_dump": ("dump",
            "🗂 <b>Send dump channel ID:</b>\n\nExample: <code>-1001234567890</code>\n\n/cancel to cancel."),
        "set_meta_title": ("meta_title",
            "🎬 <b>Send file metadata title template:</b>\n\n"
            "This is the Title embedded inside the file.\n"
            "Visible in VLC → Media Properties → Title\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> · <code>{name}</code> · <code>{prefix}</code>\n"
            "<code>{languages}</code> · <code>{quality}</code> · <code>{source}</code>\n\n"
            "<b>Example:</b>\n"
            "<code>{name} | {languages} | {quality} | @AskMovies4</code>\n\n"
            "/cancel to cancel."),
        "set_audio_title": ("audio_title",
            "🔊 <b>Send audio track title:</b>\n\n"
            "Replaces ALL audio track names inside the file.\n"
            "Shown in VLC → Audio → Audio Track\n\n"
            "<b>Examples:</b>\n"
            "<code>@AskMovies4</code>\n"
            "<code>Telegram ~ @AskMovies4</code>\n\n"
            "Send empty <code>-</code> to strip all track names.\n\n/cancel to cancel."),
        "set_strip_words": ("strip_words",
            "🧹 <b>Send words to strip from filenames:</b>\n\n"
            "These words are removed from the START of original filenames.\n"
            "Separate multiple words with comma.\n\n"
            "<b>Example:</b>\n"
            "<code>CineBase, Tamil Rockerz, TamilMV</code>\n\n"
            "This will strip:\n"
            "• <code>CineBase - Title.mkv</code> → <code>Title.mkv</code>\n"
            "• <code>Tamil Rockerz Title.mkv</code> → <code>Title.mkv</code>\n\n"
            "/cancel to cancel."),
        "set_thumb": (None, None),
    }

    if data in prompts:
        mode, prompt = prompts[data]
        if data == "set_thumb":
            state.awaiting_thumb[uid] = True
            await query.message.reply_text("🖼 <b>Send a photo</b> as thumbnail.", parse_mode=ParseMode.HTML)
        else:
            state.awaiting_input[uid] = mode
            await query.message.reply_text(prompt, parse_mode=ParseMode.HTML)


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
        await message.reply_text("❌ Cancelled."); return

    user = await get_user(uid)
    if not user: return

    if mode == "dump" and not text.lstrip("-").isdigit():
        await message.reply_text("❌ Invalid ID.", parse_mode=ParseMode.HTML); return

    # Handle empty audio title
    if mode == "audio_title" and text == "-":
        text = ""

    db_map = {
        "prefix":      "file_prefix",
        "caption":     "caption_template",
        "dump":        "dump_channel",
        "meta_title":  "metadata_title",
        "audio_title": "audio_track_title",
        "strip_words": "strip_words",
    }
    replies = {
        "prefix":      f"✅ Prefix set: <code>{text}</code>",
        "caption":     f"✅ Caption saved:\n\n<code>{text}</code>",
        "dump":        f"✅ Dump channel: <code>{text}</code>",
        "meta_title":  f"✅ Metadata title:\n<code>{text}</code>",
        "audio_title": f"✅ Audio track title: <code>{text or '(stripped)'}</code>",
        "strip_words": f"✅ Strip words set:\n<code>{text}</code>",
    }

    if mode in db_map:
        await update_user(uid, **{db_map[mode]: text})
        await message.reply_text(replies[mode], parse_mode=ParseMode.HTML)

    user = await get_user(uid)
    await message.reply_text("⚙️ <b>Updated!</b>", parse_mode=ParseMode.HTML, reply_markup=_kb(user))
