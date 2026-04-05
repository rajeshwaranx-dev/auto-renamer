"""
handlers.py — Smart prefix stripper + queue + per-user settings
"""
import os, re, time, asyncio
from pyrogram import Client as PyroClient
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import DOWNLOAD_DIR, log
from database import users_for_source, increment_stats, update_user, all_users
from ffmpeg_utils import (embed_metadata, extract_thumb_from_video, human_size,
                           is_video, extract_languages, extract_quality, extract_source)
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
                bot_token=bot_token, workdir="/root/leechbot",
                sleep_threshold=60, max_concurrent_transmissions=2)
        else:
            log.warning("No Pyrogram credentials"); return
        await _pyro_client.start()
        me = await _pyro_client.get_me()
        log.info("Pyrogram started as: %s", me.first_name)
        users = await all_users()
        for u in users:
            for ch in (u.get("source_channels") or []):
                try: await _pyro_client.get_chat(int(ch)); log.info("Peer cached: %s", ch)
                except Exception as ex: log.warning("Peer cache failed %s: %s", ch, ex)
            dest = u.get("dest_channel")
            if dest:
                try: await _pyro_client.get_chat(int(dest)); log.info("Peer cached dest: %s", dest)
                except Exception as ex: log.warning("Peer cache dest failed: %s", ex)
    except Exception as e:
        log.error("Pyrogram failed: %s", e); _pyro_client = None

async def stop_pyro_client():
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        await _pyro_client.stop()

# ── Smart filename cleaner ─────────────────────────────────────

# Known movie/show title start indicators — stops stripping before these
TITLE_INDICATORS = re.compile(
    r"\b(S\d{1,2}|EP?\d{1,3}|Season|Episode|Part|\d{4}|"
    r"480p|720p|1080p|4K|WEB|BluRay|HDRip|CAM|HDCAM)\b",
    re.IGNORECASE
)

def _split_ext(filename):
    m = re.match(r"^(.*?)(\.[a-zA-Z0-9]{2,5})$", filename)
    return (m.group(1), m.group(2)) if m else (filename, "")

def clean_original_name(filename: str, strip_words: list[str] = None) -> str:
    """
    Intelligently strip channel prefixes from filenames.

    Handles patterns like:
      CineBase_Harlan_Coben_Lazarus.mkv   → Harlan Coben Lazarus.mkv
      [AskMovies] Title.mkv               → Title.mkv
      @channel - Title.mkv               → Title.mkv
      ChannelName - Title (2024).mkv     → Title (2024).mkv
      Word1_Word2_ACTUAL_TITLE.mkv       → strips only channel-looking prefix
    """
    name, ext = _split_ext(filename)
    original  = name

    # Normalize underscores and dots to spaces
    name = re.sub(r"[_.]", " ", name).strip()

    # 1. User-defined strip words (highest priority)
    if strip_words:
        for word in strip_words:
            word = word.strip()
            if not word: continue
            name = re.sub(
                r"^\s*" + re.escape(word) + r"\s*[-_]?\s*",
                "", name, flags=re.IGNORECASE
            ).strip()

    # 2. Strip [tags] at start
    name = re.sub(r"^\s*\[[^\]]{1,30}\]\s*", "", name).strip()

    # 3. Strip @channel at start
    name = re.sub(r"^\s*@\S+\s*[-]?\s*", "", name).strip()

    # 4. Strip boxed letters (🄰🅂🄺 etc)
    name = re.sub(r"^[\U0001F100-\U0001F9FF\s]+", "", name).strip()

    # 5. AUTO-DETECT channel prefix pattern:
    #    If the name starts with a single "word" that doesn't look like
    #    part of a real title (no spaces before the next word starts with caps),
    #    and the remaining name has a title indicator — strip that first word.
    #
    #    Pattern: "CineBase Harlan Cobens Lazarus 2025 S01..."
    #    The word "CineBase" before "Harlan" (capital letter start) looks like prefix
    words = name.split()
    if len(words) >= 3:
        first_word = words[0]
        rest       = " ".join(words[1:])
        # First word looks like channel name if:
        # - It's a single CamelCase or AllCaps word (no spaces)
        # - It doesn't contain year-like patterns
        # - The rest starts with capital letter or title content
        is_channel_like = (
            re.match(r"^[A-Za-z][A-Za-z0-9]{1,20}$", first_word) and
            not re.match(r"^\d{4}$", first_word) and
            re.match(r"^[A-Z]", rest) and
            TITLE_INDICATORS.search(rest)  # rest looks like actual title
        )
        if is_channel_like:
            name = rest
            log.info("Auto-stripped prefix word: %r", first_word)

    # 6. Clean up extra spaces
    name = re.sub(r"\s+", " ", name).strip()

    log.info("Filename cleaned: %r → %r", original, name)
    return name + ext

def _build_caption(template, **kwargs):
    try:
        return template.format(**kwargs)
    except Exception:
        return kwargs.get("newname", "")

def _get_media(message):
    return message.document or message.video or message.audio or message.voice

def _ensure_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def _cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try: os.remove(p); log.info("Deleted: %s", p)
            except Exception as e: log.warning("Cleanup %s: %s", p, e)

def _fmt_eta(s):
    if s < 60: return f"{int(s)}s"
    elif s < 3600: return f"{int(s//60)}m {int(s%60)}s"
    else: return f"{int(s//3600)}h {int((s%3600)//60)}m"

# ── Progress ───────────────────────────────────────────────────

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
            speed   = current/elapsed if elapsed>0 else 0
            eta     = (total-current)/speed if speed>0 else 0
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
        except Exception: pass

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

async def _pyro_upload(pyro, message, dest_channel, file_path, new_name, caption, thumb_path, tracker=None):
    size  = os.path.getsize(file_path)
    ext   = os.path.splitext(file_path)[1].lower()
    thumb = thumb_path if thumb_path and os.path.exists(thumb_path) else None
    prog  = tracker.update if tracker else None
    if ext in {".mp4",".m4v"}:
        await pyro.send_video(chat_id=dest_channel, video=file_path, caption=caption,
            file_name=new_name, thumb=thumb, supports_streaming=True, progress=prog)
    elif ext in {".mp3",".m4a",".flac",".ogg",".opus",".aac",".wav"} or message.audio:
        await pyro.send_audio(chat_id=dest_channel, audio=file_path, caption=caption,
            file_name=new_name, thumb=thumb, title=new_name, progress=prog)
    else:
        await pyro.send_document(chat_id=dest_channel, document=file_path, caption=caption,
            file_name=new_name, thumb=thumb, force_document=True, progress=prog)
    state.stats["uploaded"] += size
    log.info("Uploaded: %s (%s)", new_name, human_size(size))

# ── Single task ────────────────────────────────────────────────

async def _process_task(user, message, bot, pyro):
    uid           = user["user_id"]
    dest          = user.get("dest_channel")
    media         = _get_media(message)
    original_name = getattr(media, "file_name", None) or "file"
    file_size     = getattr(media, "file_size", 0) or 0
    prefix        = (user.get("file_prefix") or "").strip()
    strip_words   = [w.strip() for w in (user.get("strip_words") or "").split(",") if w.strip()]

    # Clean filename + apply prefix
    cleaned_name     = clean_original_name(original_name, strip_words)
    name_no_ext, ext = _split_ext(cleaned_name)
    new_name = f"{prefix} {name_no_ext}{ext}".strip() if prefix else cleaned_name

    # Extract file info
    languages = extract_languages(original_name)
    quality   = extract_quality(original_name)
    source    = extract_source(original_name)
    lang_str  = ", ".join(languages) if languages else "—"

    dl_path        = os.path.join(DOWNLOAD_DIR, f"{uid}_{message.message_id}{ext}")
    processed_path = None
    thumb_dl_path  = None
    progress_msg   = None

    state.active_tasks[uid] = state.active_tasks.get(uid, 0) + 1

    try:
        try:
            progress_msg = await bot.send_message(
                chat_id=uid, parse_mode=ParseMode.HTML,
                text=f"⬇️ <b>Downloading</b>\n\n<code>{new_name}</code>\n📦 {human_size(file_size)}")
        except: progress_msg = None

        tracker_dl = ProgressTracker(bot, uid, progress_msg.message_id, "Downloading") if progress_msg else None

        ok = await _pyro_download(message.chat.id, message.message_id, dl_path, tracker_dl)
        if not ok:
            await increment_stats(uid, failed=True); state.stats["failed"] += 1
            if progress_msg: await progress_msg.edit_text("❌ Download failed."); return

        thumb_file_id = user.get("thumb")
        if thumb_file_id:
            thumb_dl_path = dl_path + "_thumb.jpg"
            await _download_thumb(bot, thumb_file_id, thumb_dl_path)
        elif is_video(dl_path):
            thumb_dl_path = await extract_thumb_from_video(dl_path)

        # Build metadata
        meta_title_tpl = user.get("metadata_title") or "{newname}"
        try:
            meta_title = meta_title_tpl.format(
                newname=new_name, filename=original_name, name=name_no_ext,
                prefix=prefix, languages=lang_str, quality=quality, source=source)
        except: meta_title = new_name

        custom_meta = {
            "title":       meta_title,
            "comment":     user.get("metadata_comment") or "",
            "artist":      user.get("metadata_artist") or "",
            "audio_title": user.get("audio_track_title") or "",
        }

        if progress_msg:
            await progress_msg.edit_text("⚙️ <b>Processing metadata...</b>", parse_mode=ParseMode.HTML)
        processed_path = await embed_metadata(dl_path, thumb_dl_path, meta_title, custom_meta)

        # Build caption
        caption_tpl = user.get("caption_template") or (
            "<b>{newname}</b>\n\nLanguage : {languages}\nQuality : {quality}"
        )
        caption = _build_caption(caption_tpl,
            filename=original_name, newname=new_name, name=name_no_ext,
            ext=ext, prefix=prefix, size=human_size(file_size),
            languages=lang_str, quality=quality, source=source)

        if progress_msg:
            await progress_msg.edit_text(f"⬆️ <b>Uploading</b>\n\n<code>{new_name}</code>", parse_mode=ParseMode.HTML)
        tracker_ul = ProgressTracker(bot, uid, progress_msg.message_id, "Uploading") if progress_msg else None

        await _pyro_upload(pyro=pyro, message=message, dest_channel=dest,
            file_path=processed_path, new_name=new_name, caption=caption,
            thumb_path=thumb_dl_path, tracker=tracker_ul)

        await increment_stats(uid)
        state.stats["total"] += 1
        state.stats["by_user"][user["name"]] = state.stats["by_user"].get(user["name"], 0) + 1
        log.info("Done | user=%s | %s", user["name"], new_name)

        if progress_msg:
            await progress_msg.edit_text(
                f"✅ <b>Done!</b>\n\n<code>{new_name}</code>\n"
                f"📦 {human_size(file_size)}\n"
                f"🌐 Language : {lang_str}\n"
                f"📺 Quality : {quality or '—'}",
                parse_mode=ParseMode.HTML)

    except Exception as exc:
        log.error("Error | user=%s: %s", user["name"], exc)
        await increment_stats(uid, failed=True); state.stats["failed"] += 1
        if progress_msg:
            try: await progress_msg.edit_text(f"❌ <b>Error:</b>\n<code>{str(exc)[:300]}</code>", parse_mode=ParseMode.HTML)
            except: pass
    finally:
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
                log.error("Pyrogram not available — dropping task")
                state.task_queue.task_done(); continue
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
        q_size = state.task_queue.qsize()
        active = sum(state.active_tasks.values())

        try:
            await context.bot.send_message(
                chat_id=uid, parse_mode=ParseMode.HTML,
                text=(f"📥 <b>Task queued!</b>\n\n"
                      f"📄 <code>{fname}</code>\n"
                      f"📦 {human_size(file_size)}\n\n"
                      f"🔄 Active: {active}/20 | ⏳ Queue: {q_size}"))
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
