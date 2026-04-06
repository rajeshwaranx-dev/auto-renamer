"""
handlers.py — Core leech handler.
"""
import os, re, time, asyncio
from pyrogram import Client as PyroClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import DOWNLOAD_DIR, log
from database import (users_for_source, increment_stats, update_user,
                      all_users, is_duplicate, mark_processed)
from ffmpeg_utils import (embed_metadata, extract_thumb_from_video, human_size,
                           is_video, extract_languages, extract_quality)
from logger import log_task_start, log_task_done, log_task_failed, log_duplicate
import state

_pyro_client = None

# ── Pyrogram ───────────────────────────────────────────────────

async def get_pyro_client():
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        return _pyro_client
    return None

async def init_pyro_client(api_id, api_hash, session_string="", bot_token=""):
    global _pyro_client
    try:
        if session_string:
            _pyro_client = PyroClient("leech_user", api_id=api_id, api_hash=api_hash,
                session_string=session_string, in_memory=True)
        elif bot_token:
            _pyro_client = PyroClient("leech_bot_pyro", api_id=api_id, api_hash=api_hash,
                bot_token=bot_token, in_memory=True)
        else:
            log.warning("No Pyrogram credentials"); return
        await _pyro_client.start()
        me = await _pyro_client.get_me()
        log.info("Pyrogram started as: %s", me.first_name)
        users = await all_users()
        for u in users:
            for ch in (u.get("source_channels") or []):
                try: await _pyro_client.get_chat(int(ch))
                except: pass
            for ch_key in ["dest_channel", "dump_channel"]:
                ch = u.get(ch_key)
                if ch:
                    try: await _pyro_client.get_chat(int(ch))
                    except: pass
        try:
            from database import get_bot_settings
            s = await get_bot_settings()
            lc = s.get("log_channel")
            if lc: await _pyro_client.get_chat(int(lc))
        except: pass
    except Exception as e:
        log.error("Pyrogram failed: %s", e); _pyro_client = None

async def stop_pyro_client():
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        await _pyro_client.stop()

# ── Source caption parser ──────────────────────────────────────

def parse_source_caption(caption: str) -> tuple[str, str]:
    """
    Extract Language and Quality from source channel caption.
    Handles:
    - Typos: Langauge, Lang, Language
    - Hash prefix: #1080p → 1080p
    - Multiple languages: Hindi, Tamil, Telugu
    - Stops at fast download link / join lines
    Returns (languages_str, quality_str)
    """
    if not caption:
        return "", ""

    languages = ""
    quality   = ""

    # Process line by line, stop at URLs or join lines
    for line in caption.split("\n"):
        stripped = line.strip()

        # Stop processing at download links or channel promo lines
        if re.search(r"(http[s]?://|fast\s+download|join\s*»|@\S+channel|t\.me/)", stripped, re.IGNORECASE):
            continue

        # Match language line — handles: Language, Langauge, Lang
        lang_m = re.match(r"lang(?:u?a?g?e?)?(?:uage)?\s*[:\-]\s*(.+)", stripped, re.IGNORECASE)
        if lang_m and not languages:
            raw = lang_m.group(1).strip()
            raw = re.sub(r"#", "", raw)          # remove hashtags
            raw = re.sub(r"\s+", " ", raw).strip()
            # Split and clean
            parts = re.split(r"[,+&/\[\]|]+", raw)
            langs = [p.strip().title() for p in parts if p.strip() and len(p.strip()) > 1]
            languages = ", ".join(langs)
            log.info("Parsed language from caption: %r → %r", raw, languages)

        # Match quality line
        qual_m = re.match(r"quality\s*[:\-]\s*(.+)", stripped, re.IGNORECASE)
        if qual_m and not quality:
            raw = qual_m.group(1).strip()
            raw = re.sub(r"#", "", raw).strip()  # remove # from #1080p
            quality = raw
            log.info("Parsed quality from caption: %r → %r", qual_m.group(1), quality)

    return languages, quality


# ── Caption builder ────────────────────────────────────────────

def build_final_caption(new_name: str, languages: str, quality: str,
                        custom_footer: str = "") -> str:
    """
    Build caption in exact format:
    {filename}

    Language : {languages}

    Quality : {quality}

    {custom_footer}
    """
    parts = [f"<b>{new_name}</b>"]

    if languages:
        parts.append(f"\nLanguage : {languages}")

    if quality:
        parts.append(f"\nQuality : {quality}")

    if custom_footer and custom_footer.strip():
        parts.append(f"\n\n{custom_footer.strip()}")

    return "".join(parts)


def build_custom_caption(template: str, new_name: str, languages: str,
                         quality: str, **kwargs) -> str:
    """
    If user has a FULL custom template, use it with placeholders.
    Lines with empty language/quality auto-hide.
    """
    try:
        result = template.format(
            newname   = new_name,
            languages = languages or "—",
            quality   = quality or "—",
            **kwargs
        )
        # Hide lines that show empty labels
        lines = result.split("\n")
        cleaned = []
        for line in lines:
            if re.search(
                r"(Language|Quality)\s*:\s*(—|--)?\s*$",
                line.strip(), re.IGNORECASE
            ):
                continue
            cleaned.append(line)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()
    except Exception:
        return new_name


# ── Filename cleaner ───────────────────────────────────────────

def _split_ext(filename):
    m = re.match(r"^(.*?)(\.[a-zA-Z0-9]{2,5})$", filename)
    return (m.group(1), m.group(2)) if m else (filename, "")

def clean_original_name(filename: str, strip_words: list[str] = None) -> str:
    """Strip ONLY manual strip_words + [tags] + @channel. NO auto-detect."""
    name, ext = _split_ext(filename)
    name = re.sub(r"[_.]", " ", name).strip()

    if strip_words:
        for word in strip_words:
            word = word.strip()
            if not word: continue
            name = re.sub(
                r"^\s*" + re.escape(word) + r"\s*[-_]?\s*",
                "", name, flags=re.IGNORECASE
            ).strip()

    # Strip [tags] at start
    name = re.sub(r"^\s*\[[^\]]{1,30}\]\s*", "", name).strip()
    # Strip @channel at start
    name = re.sub(r"^\s*@\S+\s*[-]?\s*", "", name).strip()
    # Clean spaces
    name = re.sub(r"\s+", " ", name).strip()
    log.info("Cleaned: %r → %r", _split_ext(filename)[0], name)
    return name + ext


def _get_media(message):
    return message.document or message.video or message.audio or message.voice

def _ensure_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def _cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try: os.remove(p)
            except Exception as e: log.warning("Cleanup %s: %s", p, e)

def _fmt_eta(s):
    if s < 60: return f"{int(s)}s"
    elif s < 3600: return f"{int(s//60)}m {int(s%60)}s"
    else: return f"{int(s//3600)}h {int((s%3600)//60)}m"


# ── Progress tracker ───────────────────────────────────────────

class ProgressTracker:
    def __init__(self, bot, chat_id, msg_id, label="Downloading"):
        self.bot=bot; self.chat_id=chat_id; self.msg_id=msg_id
        self.label=label; self.last_edit=0; self.start_time=time.time()

    async def update(self, current, total):
        now = time.time()
        if now - self.last_edit < 4: return
        self.last_edit = now
        try:
            pct     = current/total*100 if total else 0
            elapsed = now - self.start_time
            speed   = current/elapsed if elapsed > 0 else 0
            eta     = (total-current)/speed if speed > 0 else 0
            filled  = int(pct/10)
            bar     = "●"*filled + "○"*(10-filled)
            emoji   = "⬇️" if "Down" in self.label else "⬆️"
            await self.bot.edit_message_text(
                chat_id=self.chat_id, message_id=self.msg_id,
                parse_mode=ParseMode.HTML,
                text=(f"{emoji} <b>{self.label}</b>\n\n"
                      f"{bar} {pct:.1f}%\n"
                      f"📦 {human_size(current)} of {human_size(total)}\n"
                      f"⚡ {human_size(int(speed))}/s\n"
                      f"⏱ ETA: {_fmt_eta(eta)} | ⏳ {_fmt_eta(elapsed)}"))
        except: pass


# ── Download / Upload ──────────────────────────────────────────

async def _pyro_download(chat_id, message_id, dest_path, tracker=None):
    pyro = await get_pyro_client()
    if not pyro: log.error("Pyrogram not available"); return False
    try:
        msg = await pyro.get_messages(chat_id, message_id)
        await pyro.download_media(msg, file_name=dest_path,
            progress=tracker.update if tracker else None)
        size = os.path.getsize(dest_path)
        state.stats["downloaded"] += size
        log.info("Downloaded: %s (%s)", os.path.basename(dest_path), human_size(size))
        return True
    except Exception as e:
        log.error("Download failed: %s", e); return False

async def _download_thumb(bot, file_id, dest_path):
    try:
        f = await bot.get_file(file_id)
        await f.download_to_drive(dest_path); return True
    except: return False

async def _pyro_upload(pyro, message, dest_channel, file_path, new_name,
                       caption, thumb_path, tracker=None):
    size  = os.path.getsize(file_path)
    ext   = os.path.splitext(file_path)[1].lower()
    thumb = thumb_path if thumb_path and os.path.exists(thumb_path) else None
    prog  = tracker.update if tracker else None
    if ext in {".mp4", ".m4v"}:
        await pyro.send_video(chat_id=dest_channel, video=file_path,
            caption=caption, file_name=new_name, thumb=thumb,
            supports_streaming=True, progress=prog)
    elif ext in {".mp3",".m4a",".flac",".ogg",".opus",".aac",".wav"} or message.audio:
        await pyro.send_audio(chat_id=dest_channel, audio=file_path,
            caption=caption, file_name=new_name, thumb=thumb,
            title=new_name, progress=prog)
    else:
        await pyro.send_document(chat_id=dest_channel, document=file_path,
            caption=caption, file_name=new_name, thumb=thumb,
            force_document=True, progress=prog)
    state.stats["uploaded"] += size
    log.info("Uploaded: %s (%s)", new_name, human_size(size))


# ── Active tasks for /status ───────────────────────────────────

active_task_list: dict[str, dict] = {}
_task_counter = 0

def _new_task_id() -> str:
    global _task_counter
    _task_counter += 1
    return str(_task_counter)


# ── Single task ────────────────────────────────────────────────

async def _process_task(user, message, bot, pyro):
    uid           = user["user_id"]
    dest          = user.get("dest_channel")
    media         = _get_media(message)
    original_name = getattr(media, "file_name", None) or "file"
    file_size     = getattr(media, "file_size", 0) or 0
    file_id       = getattr(media, "file_id", "")
    prefix        = (user.get("file_prefix") or "").strip()
    strip_words   = [w.strip() for w in (user.get("strip_words") or "").split(",") if w.strip()]

    # ── Extract Language + Quality from source caption ─────────
    source_caption = message.caption or ""
    src_languages, src_quality = parse_source_caption(source_caption)
    log.info("Source caption | lang=%r quality=%r", src_languages, src_quality)

    # Fallback to filename detection
    if not src_languages:
        langs = extract_languages(original_name)
        src_languages = ", ".join(langs) if langs else ""
    if not src_quality:
        src_quality = extract_quality(original_name)

    log.info("Final | lang=%r quality=%r | file=%s", src_languages, src_quality, original_name)

    # ── Duplicate check ────────────────────────────────────────
    if file_id and await is_duplicate(uid, file_id):
        log.info("Duplicate skipped | user=%s | %s", user["name"], original_name)
        await log_duplicate(bot, user, original_name)
        try:
            await bot.send_message(chat_id=uid, parse_mode=ParseMode.HTML,
                text=f"⏭ <b>Duplicate Skipped</b>\n\n"
                     f"<code>{original_name}</code>\n\n"
                     f"ℹ️ Same file processed within last 10 minutes.")
        except: pass
        return

    # ── Clean filename + apply prefix ─────────────────────────
    cleaned_name     = clean_original_name(original_name, strip_words)
    name_no_ext, ext = _split_ext(cleaned_name)
    new_name = f"{prefix} {name_no_ext}{ext}".strip() if prefix else cleaned_name

    dl_path        = os.path.join(DOWNLOAD_DIR, f"{uid}_{message.message_id}{ext}")
    processed_path = None
    thumb_dl_path  = None
    progress_msg   = None

    # Register task for /status
    task_id = _new_task_id()
    active_task_list[task_id] = {
        "user":    user["name"],
        "uid":     uid,
        "filename": new_name,
        "size":    human_size(file_size),
        "status":  "⬇️ Downloading",
        "started": time.time(),
        "pct":     0.0,
        "speed":   "",
        "eta":     "",
    }
    state.active_tasks[uid] = state.active_tasks.get(uid, 0) + 1

    try:
        await log_task_start(bot, user, original_name, new_name, human_size(file_size))

        try:
            progress_msg = await bot.send_message(
                chat_id=uid, parse_mode=ParseMode.HTML,
                text=f"⬇️ <b>Downloading</b>\n\n"
                     f"<code>{new_name}</code>\n"
                     f"📦 {human_size(file_size)}")
        except: progress_msg = None

        tracker_dl = ProgressTracker(bot, uid, progress_msg.message_id, "Downloading") if progress_msg else None

        if tracker_dl:
            _orig = tracker_dl.update
            async def _patched(current, total, _o=_orig, _tid=task_id):
                await _o(current, total)
                if _tid in active_task_list:
                    pct     = current/total*100 if total else 0
                    elapsed = time.time() - active_task_list[_tid]["started"]
                    speed   = current/elapsed if elapsed > 0 else 0
                    eta     = (total-current)/speed if speed > 0 else 0
                    active_task_list[_tid].update({
                        "pct": pct, "speed": f"{human_size(int(speed))}/s",
                        "eta": _fmt_eta(eta),
                    })
            tracker_dl.update = _patched

        ok = await _pyro_download(message.chat.id, message.message_id, dl_path, tracker_dl)
        if not ok:
            await increment_stats(uid, failed=True)
            state.stats["failed"] += 1
            await log_task_failed(bot, user, original_name, "Download failed")
            if progress_msg: await progress_msg.edit_text("❌ Download failed.")
            return

        active_task_list[task_id]["status"] = "⚙️ Processing"
        active_task_list[task_id]["pct"]    = 100.0

        # Thumbnail
        thumb_file_id = user.get("thumb")
        if thumb_file_id:
            thumb_dl_path = dl_path + "_thumb.jpg"
            await _download_thumb(bot, thumb_file_id, thumb_dl_path)
        elif is_video(dl_path):
            thumb_dl_path = await extract_thumb_from_video(dl_path)

        # Metadata title
        meta_title_tpl = user.get("metadata_title") or "{newname}"
        try:
            meta_title = meta_title_tpl.format(
                newname=new_name, filename=original_name, name=name_no_ext,
                prefix=prefix, languages=src_languages or "—", quality=src_quality)
        except: meta_title = new_name

        custom_meta = {
            "title":       meta_title,
            "comment":     user.get("metadata_comment") or "",
            "artist":      user.get("metadata_artist") or "",
            "audio_title": user.get("audio_track_title") or "",
        }

        if progress_msg:
            await progress_msg.edit_text("⚙️ <b>Processing metadata...</b>",
                                         parse_mode=ParseMode.HTML)
        processed_path = await embed_metadata(dl_path, thumb_dl_path, meta_title, custom_meta)

        # ── Build caption ──────────────────────────────────────
        caption_tpl = user.get("caption_template") or ""

        if caption_tpl:
            # User has full custom template — use it
            caption = build_custom_caption(
                caption_tpl, new_name, src_languages, src_quality,
                filename=original_name, name=name_no_ext,
                ext=ext, prefix=prefix, size=human_size(file_size),
            )
        else:
            # Default format: filename + Language + Quality + custom footer
            # custom footer = caption_template if it doesn't have placeholders
            # (for simple things like "📢 @AskMovies4")
            caption = build_final_caption(
                new_name    = new_name,
                languages   = src_languages,
                quality     = src_quality,
                custom_footer = "",
            )

        active_task_list[task_id]["status"] = "⬆️ Uploading"
        if progress_msg:
            await progress_msg.edit_text(
                f"⬆️ <b>Uploading</b>\n\n<code>{new_name}</code>",
                parse_mode=ParseMode.HTML)
        tracker_ul = ProgressTracker(bot, uid, progress_msg.message_id, "Uploading") if progress_msg else None

        await _pyro_upload(pyro=pyro, message=message, dest_channel=dest,
            file_path=processed_path, new_name=new_name, caption=caption,
            thumb_path=thumb_dl_path, tracker=tracker_ul)

        if file_id:
            await mark_processed(uid, file_id, original_name)

        await increment_stats(uid)
        state.stats["total"] += 1
        state.stats["by_user"][user["name"]] = state.stats["by_user"].get(user["name"], 0) + 1

        await log_task_done(bot, user, new_name, human_size(file_size),
                            src_languages, src_quality, thumb_dl_path)

        done_lines = [f"✅ <b>Done!</b>\n\n<code>{new_name}</code>\n📦 {human_size(file_size)}"]
        if src_languages: done_lines.append(f"\n🌐 {src_languages}")
        if src_quality:   done_lines.append(f"\n📺 {src_quality}")
        if progress_msg:
            await progress_msg.edit_text("".join(done_lines), parse_mode=ParseMode.HTML)

    except Exception as exc:
        log.error("Error | user=%s: %s", user["name"], exc)
        await increment_stats(uid, failed=True)
        state.stats["failed"] += 1
        await log_task_failed(bot, user, original_name, str(exc))
        if progress_msg:
            try:
                await progress_msg.edit_text(
                    f"❌ <b>Error:</b>\n<code>{str(exc)[:300]}</code>",
                    parse_mode=ParseMode.HTML)
            except: pass
    finally:
        active_task_list.pop(task_id, None)
        to_clean = [dl_path, thumb_dl_path]
        if processed_path and processed_path != dl_path:
            to_clean.append(processed_path)
        _cleanup(*to_clean)
        state.active_tasks[uid] = max(0, state.active_tasks.get(uid, 1) - 1)


# ── Queue worker ───────────────────────────────────────────────

async def queue_worker():
    while True:
        try:
            item = await state.task_queue.get()
            user, message, bot = item
            uid = user["user_id"]
            state.pending_count[uid] = max(0, state.pending_count.get(uid, 1) - 1)
            pyro = await get_pyro_client()
            if not pyro:
                log.error("Pyrogram not available")
                state.task_queue.task_done()
                continue
            async with state.task_semaphore:
                await _process_task(user, message, bot, pyro)
            state.task_queue.task_done()
        except Exception as e:
            log.error("Queue worker error: %s", e)


# ── Channel post handler ───────────────────────────────────────

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post or update.message
    if not message: return
    channel_id = str(message.chat.id)
    media      = _get_media(message)
    if not media: return
    matched = await users_for_source(channel_id)
    if not matched: return
    _ensure_dir()

    for user in matched:
        if not user.get("dest_channel"): continue
        uid       = user["user_id"]
        file_size = getattr(media, "file_size", 0) or 0
        fname     = getattr(media, "file_name", "file")

        await state.task_queue.put((user, message, context.bot))
        state.pending_count[uid] = state.pending_count.get(uid, 0) + 1
        active = sum(state.active_tasks.values())
        q_size = state.task_queue.qsize()

        try:
            await context.bot.send_message(
                chat_id=uid, parse_mode=ParseMode.HTML,
                text=(f"📥 <b>Task Queued</b>\n\n"
                      f"📄 <code>{fname}</code>\n"
                      f"📦 {human_size(file_size)}\n\n"
                      f"🔄 Active: {active}/20 | ⏳ Queue: {q_size}"))
        except: pass


# ── /status command ────────────────────────────────────────────

TASKS_PER_PAGE = 5

def _build_status_text(page: int = 1) -> tuple[str, int]:
    tasks       = list(active_task_list.values())
    q_size      = state.task_queue.qsize()
    total_act   = len(tasks)
    total_pages = max(1, (total_act + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    page        = max(1, min(page, total_pages))

    try:
        import shutil
        disk    = shutil.disk_usage(DOWNLOAD_DIR if os.path.exists(DOWNLOAD_DIR) else "/")
        free_gb = disk.free / (1024**3)
        disk_str = f"{free_gb:.2f} GB"
    except:
        disk_str = "—"

    lines = [
        f"📊 <b>LeechBot Status</b>\n",
        f"• Tasks : {total_act} active | {q_size} queued",
        f"• Done  : {state.stats['total']} | Failed: {state.stats['failed']}",
        f"• Free Disk : {disk_str}",
        f"• DL : {human_size(state.stats['downloaded'])} | UL : {human_size(state.stats['uploaded'])}",
        "",
    ]

    if not tasks:
        lines.append("✅ No active tasks.")
    else:
        start      = (page - 1) * TASKS_PER_PAGE
        end        = start + TASKS_PER_PAGE
        page_tasks = tasks[start:end]

        for i, t in enumerate(page_tasks, start=start+1):
            elapsed  = time.time() - t["started"]
            name_short = t["filename"][:40] + ("…" if len(t["filename"]) > 40 else "")
            lines.append(
                f"<b>{i}. {name_short}</b>\n"
                f"   ├ {t['status']} {t['pct']:.1f}%\n"
                f"   ├ 📦 {t['size']}\n"
                f"   ├ ⚡ {t['speed'] or '—'}\n"
                f"   ├ ⏱ ETA: {t['eta'] or '—'} | ⏳ {_fmt_eta(elapsed)}\n"
                f"   └ 👤 {t['user']}"
            )
            if i < min(end, total_act):
                lines.append("")

    if total_pages > 1:
        lines.append(f"\n📄 Page {page}/{total_pages}")

    return "\n".join(lines), total_pages


def _status_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"status_p_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="status_noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"status_p_{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=f"status_p_{page}"),
        InlineKeyboardButton("❌ Close",   callback_data="status_close"),
    ])
    return InlineKeyboardMarkup(rows)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, total_pages = _build_status_text(1)
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=_status_kb(1, total_pages))


async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    if data == "status_close":
        await query.message.delete(); return
    if data == "status_noop":
        return

    # data = "status_p_2"
    page = int(data.split("_")[-1])
    text, total_pages = _build_status_text(page)
    try:
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=_status_kb(page, total_pages))
    except: pass


# ── Thumbnail handler ──────────────────────────────────────────

async def handle_thumb_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.photo: return
    user_id = message.from_user.id
    if not state.awaiting_thumb.pop(user_id, False): return
    photo = message.photo[-1]
    await update_user(user_id, thumb=photo.file_id)
    await message.reply_text("✅ <b>Thumbnail saved!</b>", parse_mode=ParseMode.HTML)
