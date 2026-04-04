"""
handlers.py — Leech handler.
Download via Pyrogram + Upload via Pyrogram (no size limits).
"""

import os
from pyrogram import Client as PyroClient
from pyrogram.types import Message as PyroMessage
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import DOWNLOAD_DIR, log
from database import users_for_source, increment_stats, update_user
from ffmpeg_utils import embed_metadata, extract_thumb_from_video, human_size, is_video
import state

# ──────────────────────────────────────────────────────────────
# PYROGRAM CLIENT
# ──────────────────────────────────────────────────────────────

_pyro_client: PyroClient | None = None


async def get_pyro_client() -> PyroClient | None:
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        return _pyro_client
    return None


async def init_pyro_client(api_id: int, api_hash: str,
                            session_string: str = "", bot_token: str = ""):
    global _pyro_client
    try:
        if session_string:
            _pyro_client = PyroClient(
                "leech_user",
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                in_memory=True,
            )
        elif bot_token:
            _pyro_client = PyroClient(
                "leech_bot_pyro",
                api_id=api_id,
                api_hash=api_hash,
                bot_token=bot_token,
                in_memory=True,
            )
        else:
            log.warning("⚠️  No Pyrogram credentials — large file support disabled")
            return

        await _pyro_client.start()
        me = await _pyro_client.get_me()
        log.info("✅ Pyrogram started as: %s", me.first_name)

    


async def stop_pyro_client():
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        await _pyro_client.stop()
        log.info("Pyrogram client stopped.")


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _split_ext(filename: str) -> tuple[str, str]:
    import re
    m = re.match(r"^(.*?)(\.[a-zA-Z0-9]{2,5})$", filename)
    if m:
        return m.group(1), m.group(2)
    return filename, ""


def _build_caption(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return kwargs.get("newname", kwargs.get("filename", ""))


def _get_media(await _pyro_client.start()
        me = await _pyro_client.get_me()
        log.info("✅ Pyrogram started as: %s", me.first_name)

        # Warm up all channel peers from DB
        from database import all_users
        users = await all_users()
        for u in users:
            for ch in (u.get("source_channels") or []):
                try:
                    await _pyro_client.get_chat(int(ch))
                    log.info("✅ Peer cached: %s", ch)
                except Exception as ex:
                    log.warning("Peer cache failed %s: %s", ch, ex)
            dest = u.get("dest_channel")
            if dest:
                try:
                    await _pyro_client.get_chat(int(dest))
                    log.info("✅ Peer cached dest: %s", dest)
                except Exception as ex:
                    log.warning("Peer cache failed dest %s: %s", dest, ex)message):
    return (
        message.document
        or message.video
        or message.audio
        or message.voice
    )


def _ensure_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
                log.info("🗑 Deleted: %s", p)
            except Exception as e:
                log.warning("Cleanup failed %s: %s", p, e)


# ──────────────────────────────────────────────────────────────
# DOWNLOAD via Pyrogram
# ──────────────────────────────────────────────────────────────

async def _pyro_download(chat_id: int, message_id: int, dest_path: str) -> bool:
    pyro = await get_pyro_client()
    if not pyro:
        log.error("❌ Pyrogram client not available")
        return False
    try:
        log.info("⬇️  Downloading → %s", os.path.basename(dest_path))
        msg = await pyro.get_messages(chat_id, message_id)
        await pyro.download_media(msg, file_name=dest_path)
        size = os.path.getsize(dest_path)
        state.stats["downloaded"] += size
        log.info("⬇️  Downloaded: %s (%s)", os.path.basename(dest_path), human_size(size))
        return True
    except Exception as e:
        log.error("❌ Download failed: %s", e)
        return False


# ──────────────────────────────────────────────────────────────
# DOWNLOAD thumbnail via PTB (thumbnails are small, PTB is fine)
# ──────────────────────────────────────────────────────────────

async def _download_thumb(bot, file_id: str, dest_path: str) -> bool:
    try:
        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(dest_path)
        return True
    except Exception as e:
        log.warning("Thumb download failed: %s", e)
        return False


# ──────────────────────────────────────────────────────────────
# UPLOAD via Pyrogram (no size limit!)
# ──────────────────────────────────────────────────────────────

async def _pyro_upload(pyro: PyroClient, message,
                       dest_channel: str, file_path: str,
                       new_name: str, caption: str,
                       thumb_path: str | None):
    """Upload file to destination channel via Pyrogram."""
    size = os.path.getsize(file_path)
    ext  = os.path.splitext(file_path)[1].lower()
    thumb = thumb_path if thumb_path and os.path.exists(thumb_path) else None

    VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v"}
    AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wav"}

    if ext in VIDEO_EXTS or message.video:
        await pyro.send_video(
            chat_id            = dest_channel,
            video              = file_path,
            caption            = caption,
            file_name          = new_name,
            thumb              = thumb,
            supports_streaming = True,
        )
    elif ext in AUDIO_EXTS or message.audio:
        await pyro.send_audio(
            chat_id   = dest_channel,
            audio     = file_path,
            caption   = caption,
            file_name = new_name,
            thumb     = thumb,
            title     = new_name,
            duration  = getattr(getattr(message, "audio", None), "duration", None),
        )
    else:
        await pyro.send_document(
            chat_id   = dest_channel,
            document  = file_path,
            caption   = caption,
            file_name = new_name,
            thumb     = thumb,
            force_document = True,
        )

    state.stats["uploaded"] += size
    log.info("⬆️  Uploaded: %s (%s)", new_name, human_size(size))


# ──────────────────────────────────────────────────────────────
# MAIN HANDLER
# ──────────────────────────────────────────────────────────────

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post or update.message
    if not message:
        return

    channel_id = str(message.chat.id)
    media      = _get_media(message)
    if not media:
        return

    matched = await users_for_source(channel_id)
    if not matched:
        return

    _ensure_dir()

    pyro = await get_pyro_client()
    if not pyro:
        log.error("❌ Pyrogram not available — cannot process files")
        return

    for user in matched:
        dest = user.get("dest_channel")
        if not dest:
            log.warning("User %s has no dest_channel — skipping", user["name"])
            continue

        uid           = user["user_id"]
        original_name = getattr(media, "file_name", None) or "file"
        prefix        = (user.get("file_prefix") or "").strip()
        name_no_ext, ext = _split_ext(original_name)
        new_name      = f"{prefix} {name_no_ext}{ext}".strip() if prefix else original_name
        file_size     = getattr(media, "file_size", 0) or 0

        dl_path        = os.path.join(DOWNLOAD_DIR, f"{uid}_{message.message_id}{ext}")
        processed_path = None
        thumb_dl_path  = None

        state.active_tasks[uid] = state.active_tasks.get(uid, 0) + 1

        try:
            # 1. Download
            log.info("⬇️  Downloading | user=%s | %s (%s)",
                     user["name"], original_name, human_size(file_size))
            ok = await _pyro_download(message.chat.id, message.message_id, dl_path)
            if not ok:
                await increment_stats(uid, failed=True)
                state.stats["failed"] += 1
                continue

            # 2. Thumbnail
            thumb_file_id = user.get("thumb")
            if thumb_file_id:
                thumb_dl_path = dl_path + "_thumb.jpg"
                await _download_thumb(context.bot, thumb_file_id, thumb_dl_path)
            elif is_video(dl_path):
                thumb_dl_path = await extract_thumb_from_video(dl_path)

            # 3. ffmpeg embed
            log.info("⚙️  Embedding metadata | user=%s", user["name"])
            processed_path = await embed_metadata(
                input_path = dl_path,
                thumb_path = thumb_dl_path,
                title      = new_name,
            )

            # 4. Caption
            caption_tpl = user.get("caption_template") or "<b>{newname}</b>"
            caption = _build_caption(
                caption_tpl,
                filename = original_name,
                newname  = new_name,
                name     = name_no_ext,
                ext      = ext,
                prefix   = prefix,
                size     = human_size(file_size),
            )

            # 5. Upload via Pyrogram
            log.info("⬆️  Uploading | user=%s | %s", user["name"], new_name)
            await _pyro_upload(
                pyro         = pyro,
                message      = message,
                dest_channel = dest,
                file_path    = processed_path,
                new_name     = new_name,
                caption      = caption,
                thumb_path   = thumb_dl_path,
            )

            # 6. Stats
            await increment_stats(uid)
            state.stats["total"] += 1
            state.stats["by_user"][user["name"]] = (
                state.stats["by_user"].get(user["name"], 0) + 1
            )
            log.info("✅ Done | user=%s | %s → %s", user["name"], original_name, new_name)

        except Exception as exc:
            log.error("❌ Error | user=%s: %s", user["name"], exc)
            await increment_stats(uid, failed=True)
            state.stats["failed"] += 1

        finally:
            to_clean = [dl_path, thumb_dl_path]
            if processed_path and processed_path != dl_path:
                to_clean.append(processed_path)
            _cleanup(*to_clean)
            state.active_tasks[uid] = max(0, state.active_tasks.get(uid, 1) - 1)


# ──────────────────────────────────────────────────────────────
# THUMBNAIL PHOTO HANDLER
# ──────────────────────────────────────────────────────────────

async def handle_thumb_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.photo:
        return
    user_id = message.from_user.id
    if not state.awaiting_thumb.pop(user_id, False):
        return
    photo   = message.photo[-1]
    file_id = photo.file_id
    await update_user(user_id, thumb=file_id)
    await message.reply_text(
        "✅ <b>Thumbnail saved!</b>\n\nAll future files will have this thumbnail embedded.\n"
        "Use /removethumb to clear it.",
        parse_mode=ParseMode.HTML,
    )
    log.info("Thumbnail saved for user_id=%s", user_id)
  
