"""
settings.py — /settings with sub-menus + Back buttons (like LCU bot).
User-only: Prefix, Caption, Thumbnail, Mode, Dump, Metadata, Audio Track.
NO log channel or strip words (admin only via /bsettings).
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import get_user, update_user
import state

# ── Main menu ──────────────────────────────────────────────────

def _main_kb(user: dict) -> InlineKeyboardMarkup:
    mode = user.get("send_mode") or "Document"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷 Prefix",         callback_data="s_menu_prefix"),
         InlineKeyboardButton("📝 Caption",        callback_data="s_menu_caption")],
        [InlineKeyboardButton("🖼 Thumbnail",      callback_data="s_menu_thumb"),
         InlineKeyboardButton(f"📄 Mode: {mode}",  callback_data="s_menu_mode")],
        [InlineKeyboardButton("🗂 Dump Channel",   callback_data="s_menu_dump"),
         InlineKeyboardButton("🎬 Metadata Title", callback_data="s_menu_meta")],
        [InlineKeyboardButton("🔊 Audio Track",    callback_data="s_menu_audio"),
         InlineKeyboardButton("❌ Close",          callback_data="s_close")],
    ])

def _main_text(user: dict) -> str:
    cap_custom = bool(user.get("caption_template"))
    return (
        f"⚙️ <b>Leech Settings for {user['name']}</b>\n\n"
        f"• <b>Prefix:</b>        <code>{user.get('file_prefix') or 'Not set'}</code>\n"
        f"• <b>Send Mode:</b>     {user.get('send_mode') or 'Document'}\n"
        f"• <b>Thumbnail:</b>     {'Exists ✅' if user.get('thumb') else 'Not set ❌'}\n"
        f"• <b>Caption:</b>       {'Custom ✅' if cap_custom else 'Default'}\n"
        f"• <b>Dump Channel:</b>  <code>{user.get('dump_channel') or 'Not set'}</code>\n"
        f"• <b>Metadata:</b>      {'Custom ✅' if user.get('metadata_title') else 'Default'}\n"
        f"• <b>Audio Track:</b>   {'Custom ✅' if user.get('audio_track_title') else 'Stripped'}\n"
        f"• <b>Sources:</b>       {len(user.get('source_channels') or [])}\n"
        f"• <b>Dest Channel:</b>  <code>{user.get('dest_channel') or 'Not set'}</code>\n\n"
        f"📊 <b>Stats:</b> {user.get('stats',{}).get('total',0)} done | "
        f"{user.get('stats',{}).get('failed',0)} failed"
    )

# ── Sub-menu builders ──────────────────────────────────────────

def _back_kb(extra_buttons: list = None) -> InlineKeyboardMarkup:
    rows = extra_buttons or []
    rows.append([
        InlineKeyboardButton("◀️ Back", callback_data="s_back"),
        InlineKeyboardButton("❌ Close", callback_data="s_close"),
    ])
    return InlineKeyboardMarkup(rows)


def _prefix_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    current = user.get("file_prefix") or "Not set"
    text = (
        f"🏷 <b>Prefix Settings</b>\n\n"
        f"• <b>Current Prefix:</b> <code>{current}</code>\n\n"
        f"<b>Description:</b> Added at the start of every filename.\n\n"
        f"<b>Example:</b>\n"
        f"Prefix: <code>@AskMovies4</code>\n"
        f"Result: <code>@AskMovies4 Movie Name 2024.mkv</code>\n\n"
        f"Tap <b>Change</b> to set a new prefix."
    )
    buttons = [
        [InlineKeyboardButton("✏️ Change", callback_data="s_input_prefix"),
         InlineKeyboardButton("🗑 Clear", callback_data="s_clear_prefix")],
    ]
    return text, _back_kb(buttons)


def _caption_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    cap = user.get("caption_template") or "Default (auto filename + language + quality)"
    text = (
        f"📝 <b>Caption Settings</b>\n\n"
        f"• <b>Current:</b>\n<code>{cap[:200]}</code>\n\n"
        f"<b>Placeholders:</b>\n"
        f"<code>{{newname}}</code> — renamed filename\n"
        f"<code>{{filename}}</code> — original filename\n"
        f"<code>{{name}}</code> — name without extension\n"
        f"<code>{{size}}</code> — file size\n"
        f"<code>{{languages}}</code> — detected languages\n"
        f"<code>{{quality}}</code> — detected quality\n"
        f"<code>{{prefix}}</code> — your prefix\n\n"
        f"⚠️ Lines with empty language/quality auto-hide."
    )
    buttons = [
        [InlineKeyboardButton("✏️ Change", callback_data="s_input_caption"),
         InlineKeyboardButton("🔄 Reset Default", callback_data="s_clear_caption")],
    ]
    return text, _back_kb(buttons)


def _thumb_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    has_thumb = bool(user.get("thumb"))
    text = (
        f"🖼 <b>Thumbnail Settings</b>\n\n"
        f"• <b>Custom Thumbnail:</b> {'Exists ✅' if has_thumb else 'Not set ❌'}\n\n"
        f"<b>Description:</b> Custom thumbnail to appear on "
        f"all leeched files uploaded by the bot.\n\n"
        f"{'Tap <b>Change</b> to update or <b>Delete</b> to remove.' if has_thumb else 'Tap <b>Set</b> to upload a thumbnail photo.'}"
    )
    if has_thumb:
        buttons = [
            [InlineKeyboardButton("✏️ Change", callback_data="s_input_thumb"),
             InlineKeyboardButton("🗑 Delete", callback_data="s_clear_thumb")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton("📷 Set Thumbnail", callback_data="s_input_thumb")],
        ]
    return text, _back_kb(buttons)


def _mode_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    current = user.get("send_mode") or "Document"
    other   = "Media" if current == "Document" else "Document"
    text = (
        f"📄 <b>Send Mode Settings</b>\n\n"
        f"• <b>Current Mode:</b> {current}\n\n"
        f"<b>Document:</b> Sends as file — all formats supported, "
        f"no size limit issues.\n\n"
        f"<b>Media:</b> Sends .mp4 as streamable video. "
        f".mkv still sent as document.\n\n"
        f"Tap <b>Switch to {other}</b> to change."
    )
    buttons = [
        [InlineKeyboardButton(f"🔄 Switch to {other}", callback_data="s_toggle_mode")],
    ]
    return text, _back_kb(buttons)


def _dump_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    current = user.get("dump_channel") or "Not set"
    text = (
        f"🗂 <b>Dump Channel Settings</b>\n\n"
        f"• <b>Current:</b> <code>{current}</code>\n\n"
        f"<b>Description:</b> A secondary channel where files "
        f"are also uploaded (in addition to main destination).\n\n"
        f"<b>Format:</b> <code>-1001234567890</code>"
    )
    buttons = [
        [InlineKeyboardButton("✏️ Change", callback_data="s_input_dump"),
         InlineKeyboardButton("🗑 Clear", callback_data="s_clear_dump")],
    ]
    return text, _back_kb(buttons)


def _meta_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    current = user.get("metadata_title") or "Default ({newname})"
    text = (
        f"🎬 <b>Metadata Title Settings</b>\n\n"
        f"• <b>Current:</b> <code>{current[:100]}</code>\n\n"
        f"<b>Description:</b> Title embedded inside the file.\n"
        f"Visible in VLC → Media Properties → Title.\n\n"
        f"<b>Placeholders:</b>\n"
        f"<code>{{newname}}</code> · <code>{{name}}</code> · "
        f"<code>{{languages}}</code> · <code>{{quality}}</code>\n\n"
        f"<b>Example:</b>\n"
        f"<code>{{name}} | {{languages}} | {{quality}} | @AskMovies4</code>"
    )
    buttons = [
        [InlineKeyboardButton("✏️ Change", callback_data="s_input_meta"),
         InlineKeyboardButton("🗑 Clear", callback_data="s_clear_meta")],
    ]
    return text, _back_kb(buttons)


def _audio_menu(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    current = user.get("audio_track_title") or "Stripped (empty)"
    text = (
        f"🔊 <b>Audio Track Settings</b>\n\n"
        f"• <b>Current:</b> <code>{current}</code>\n\n"
        f"<b>Description:</b> Replaces ALL audio track names "
        f"inside the file.\nVisible in VLC → Audio → Audio Track.\n\n"
        f"<b>Examples:</b>\n"
        f"<code>@AskMovies4</code>\n"
        f"<code>Telegram ~ @AskMovies4</code>\n\n"
        f"Leave empty to strip all original track names."
    )
    buttons = [
        [InlineKeyboardButton("✏️ Change", callback_data="s_input_audio"),
         InlineKeyboardButton("🗑 Clear", callback_data="s_clear_audio")],
    ]
    return text, _back_kb(buttons)


# ── Show settings ──────────────────────────────────────────────

async def _show_main(update_or_query, user: dict, is_query: bool = False):
    text  = _main_text(user)
    kb    = _main_kb(user)
    thumb = user.get("thumb")

    if is_query:
        query = update_or_query
        try:
            if query.message.photo:
                await query.message.edit_caption(
                    caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except: pass
    else:
        message = update_or_query
        if thumb:
            try:
                await message.reply_photo(photo=thumb, caption=text,
                    parse_mode=ParseMode.HTML, reply_markup=kb)
                return
            except: pass
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def _show_submenu(query, text: str, kb: InlineKeyboardMarkup,
                        thumb=None, is_thumb_menu=False):
    """Show sub-menu. If is_thumb_menu and thumb exists, show thumbnail."""
    try:
        if is_thumb_menu and thumb:
            # Show thumbnail in sub-menu too
            if query.message.photo:
                await query.message.edit_caption(
                    caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            if query.message.photo:
                await query.message.edit_caption(
                    caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except: pass


# ── Command ────────────────────────────────────────────────────

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id if update.effective_user else None
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(
            "⛔ You are not registered.\nAsk admin to add you with /adduser.")
        return
    if not user.get("active"):
        await update.message.reply_text("⛔ Your account is disabled.")
        return
    await _show_main(update.message, user, is_query=False)


# ── Callback handler ───────────────────────────────────────────

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data
    user  = await get_user(uid)

    if not user:
        await query.answer("⛔ Not registered."); return
    await query.answer()

    # ── Navigation ─────────────────────────────────────────────
    if data == "s_close":
        await query.message.delete(); return

    if data == "s_back":
        user = await get_user(uid)
        await _show_main(query, user, is_query=True); return

    # ── Sub-menu opens ─────────────────────────────────────────
    if data == "s_menu_prefix":
        text, kb = _prefix_menu(user)
        await _show_submenu(query, text, kb); return

    if data == "s_menu_caption":
        text, kb = _caption_menu(user)
        await _show_submenu(query, text, kb); return

    if data == "s_menu_thumb":
        text, kb = _thumb_menu(user)
        await _show_submenu(query, text, kb, thumb=user.get("thumb"), is_thumb_menu=True); return

    if data == "s_menu_mode":
        text, kb = _mode_menu(user)
        await _show_submenu(query, text, kb); return

    if data == "s_menu_dump":
        text, kb = _dump_menu(user)
        await _show_submenu(query, text, kb); return

    if data == "s_menu_meta":
        text, kb = _meta_menu(user)
        await _show_submenu(query, text, kb); return

    if data == "s_menu_audio":
        text, kb = _audio_menu(user)
        await _show_submenu(query, text, kb); return

    # ── Toggle mode (one-tap) ──────────────────────────────────
    if data == "s_toggle_mode":
        cur = user.get("send_mode") or "Document"
        new = "Media" if cur == "Document" else "Document"
        await update_user(uid, send_mode=new)
        user = await get_user(uid)
        text, kb = _mode_menu(user)
        await _show_submenu(query, text, kb)
        await query.answer(f"✅ Mode → {new}", show_alert=True); return

    # ── Clear actions ──────────────────────────────────────────
    clears = {
        "s_clear_prefix":  ("file_prefix",        "✅ Prefix cleared.",        "s_menu_prefix"),
        "s_clear_caption": ("caption_template",   "✅ Caption reset to default.","s_menu_caption"),
        "s_clear_thumb":   ("thumb",              "✅ Thumbnail removed.",      "s_menu_thumb"),
        "s_clear_dump":    ("dump_channel",       "✅ Dump channel cleared.",   "s_menu_dump"),
        "s_clear_meta":    ("metadata_title",     "✅ Metadata title cleared.", "s_menu_meta"),
        "s_clear_audio":   ("audio_track_title",  "✅ Audio track cleared.",    "s_menu_audio"),
    }
    if data in clears:
        db_key, answer, back_menu = clears[data]
        await update_user(uid, **{db_key: "" if db_key != "thumb" else None})
        await query.answer(answer, show_alert=True)
        user = await get_user(uid)
        # Return to sub-menu
        menu_map = {
            "s_menu_prefix":  _prefix_menu,
            "s_menu_caption": _caption_menu,
            "s_menu_thumb":   lambda u: _thumb_menu(u),
            "s_menu_dump":    _dump_menu,
            "s_menu_meta":    _meta_menu,
            "s_menu_audio":   _audio_menu,
        }
        text, kb = menu_map[back_menu](user)
        await _show_submenu(query, text, kb); return

    # ── Input prompts ──────────────────────────────────────────
    input_prompts = {
        "s_input_prefix": ("prefix",
            "🏷 <b>Send your new prefix:</b>\n\n"
            "Examples:\n<code>@AskMovies4</code>\n<code>[AskMovies]</code>\n\n"
            "Send /cancel to cancel."),

        "s_input_caption": ("caption",
            "📝 <b>Send your caption template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> — renamed filename\n"
            "<code>{filename}</code> — original filename\n"
            "<code>{name}</code> — name without ext\n"
            "<code>{size}</code> — file size\n"
            "<code>{languages}</code> — languages\n"
            "<code>{quality}</code> — quality\n"
            "<code>{prefix}</code> — your prefix\n\n"
            "<b>Example:</b>\n"
            "<code>{newname}\n\nLanguage : {languages}\nQuality : {quality}\n\n📢 @AskMovies4</code>\n\n"
            "⚠️ Lines with empty values auto-hide.\n\n"
            "Send /cancel to cancel."),

        "s_input_thumb": (None, None),  # special: photo handler

        "s_input_dump": ("dump",
            "🗂 <b>Send dump channel ID:</b>\n\n"
            "Format: <code>-1001234567890</code>\n\n"
            "Send /cancel to cancel."),

        "s_input_meta": ("meta_title",
            "🎬 <b>Send metadata title template:</b>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{newname}</code> · <code>{name}</code> · "
            "<code>{languages}</code> · <code>{quality}</code>\n\n"
            "<b>Example:</b>\n"
            "<code>{name} | {languages} | {quality} | @AskMovies4</code>\n\n"
            "Send /cancel to cancel."),

        "s_input_audio": ("audio_title",
            "🔊 <b>Send audio track title:</b>\n\n"
            "Replaces all track names inside the file.\n\n"
            "Examples:\n"
            "<code>@AskMovies4</code>\n"
            "<code>Telegram ~ @AskMovies4</code>\n\n"
            "Send <code>-</code> to strip/empty all track names.\n"
            "Send /cancel to cancel."),
    }

    if data in input_prompts:
        mode, prompt = input_prompts[data]
        if data == "s_input_thumb":
            state.awaiting_thumb[uid] = True
            await query.message.reply_text(
                "🖼 <b>Send a photo</b> as thumbnail.\n"
                "• Send as <b>photo</b> (not as file)\n"
                "• Recommended size: 320×320 px\n"
                "• Timeout: 60 seconds",
                parse_mode=ParseMode.HTML)
        else:
            state.awaiting_input[uid] = mode
            await query.message.reply_text(prompt, parse_mode=ParseMode.HTML)


# ── Text input handler ─────────────────────────────────────────

async def handle_settings_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    uid  = message.from_user.id

    # Skip if this is an admin bsettings input
    mode = state.awaiting_input.get(uid, "")
    if mode.startswith("bs_"): return  # handled by bsettings

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
            parse_mode=ParseMode.HTML)
        return

    if mode == "audio_title" and text == "-":
        text = ""

    db_map = {
        "prefix":      "file_prefix",
        "caption":     "caption_template",
        "dump":        "dump_channel",
        "meta_title":  "metadata_title",
        "audio_title": "audio_track_title",
    }

    if mode in db_map:
        await update_user(uid, **{db_map[mode]: text})
        await message.reply_text("✅ Saved!", parse_mode=ParseMode.HTML)

    # Show updated main settings
    user = await get_user(uid)
    await _show_main(message, user, is_query=False)
