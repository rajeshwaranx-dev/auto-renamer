"""
handlers.py — Core leech handler.

Full flow per file:
  1. Detect file in source channel
  2. Match to registered user
  3. Download file to /tmp/leech/
  4. Download user's thumbnail (if set)
  5. ffmpeg: embed thumbnail + metadata into file
  6. Rename file with user's prefix
  7. Upload to destination channel with custom caption
  8. Delete all temp files
"""

import os
import asyncio

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import DOWNLOAD_DIR, MAX_BOT_FILE_SIZE, log
from database import users_for_source, increment_stats, update_user
from ffmpeg_utils import embed_metadata, extract_thumb_from_video, human_size, is_video
import state


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


def _get_media(message):
    return (
        message.document
        or message.video
        or message.audio
        or message.voice
    )


def _ensure_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _cleanup(*paths):
    """Delete temp files silently."""
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
                log.info("🗑 Deleted temp: %s", p)
            except Exception as e:
                log.warning("Cleanup failed for %s: %s", p, e)


# ──────────────────────────────────────────────────────────────
# DOWNLOAD HELPER with progress log
# ──────────────────────────────────────────────────────────────

async def _download_file(bot, file_id: str, dest_path: str) -> bool:
    """Download a file from Telegram to dest_path. Returns True on success."""
    try:
        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(dest_path)
        size = os.path.getsize(dest_path)
        log.info("⬇️  Downloaded: %s (%s)", os.path.basename(dest_path), human_size(size))
        state.stats["downloaded"] += size
        return True
    except Exception as e:
        log.error("Download failed: %s", e)
        return False


# ──────────────────────────────────────────────────────────────
# UPLOAD HELPER
# ──────────────────────────────────────────────────────────────

async def _upload_file(bot, message, dest_channel: str,
                       file_path: str, new_name: str,
                       caption: str, thumb_path: str | None):
    """Upload processed file to destination channel."""
    size = os.path.getsize(file_path)

    with open(file_path, "rb") as f:
        if message.video:
            # Get video dimensions/duration if available
            video = message.video
            sent = await bot.send_video(
                chat_id    = dest_channel,
                video      = f,
                filename   = new_name,
                caption    = caption,
                parse_mode = ParseMode.HTML,
                thumbnail  = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None,
                duration   = getattr(video, "duration", None),
                width      = getattr(video, "width", None),
                height     = getattr(video, "height", None),
                supports_streaming = True,
            )

        elif message.audio:
            sent = await bot.send_audio(
                chat_id    = dest_channel,
                audio      = f,
                filename   = new_name,
                title      = new_name,
                caption    = caption,
                parse_mode = ParseMode.HTML,
                thumbnail  = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None,
                duration   = getattr(message.audio, "duration", None),
            )

        else:
            # Document (default for all other files)
            sent = await bot.send_document(
                chat_id    = dest_channel,
                document   = f,
                filename   = new_name,
                caption    = caption,
                parse_mode = ParseMode.HTML,
                thumbnail  = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None,
            )

    state.stats["uploaded"] += size
    log.info("⬆️  Uploaded: %s (%s)", new_name, human_size(size))
    return sent


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

    # ── Match to registered users ──────────────────────────────
    matched = await users_for_source(channel_id)
    if not matched:
        return

    _ensure_dir()

    for user in matched:
        dest = user.get("dest_channel")
        if not dest:
            log.warning("User %s has no dest_channel — skipping", user["name"])
            continue

        # ── Check file size ────────────────────────────────────
        file_size = getattr(media, "file_size", 0) or 0
        if file_size > MAX_BOT_FILE_SIZE:
            log.warning(
                "❌ File too large (%s) for user=%s — Bot API limit is 2GB. "
                "Switch to Pyrogram user session for 4GB support.",
                human_size(file_size), user["name"]
            )
            continue

        # ── Track active tasks ─────────────────────────────────
        uid = user["user_id"]
        state.active_tasks[uid] = state.active_tasks.get(uid, 0) + 1

        # Paths
        original_name = getattr(media, "file_name", None) or "file"
        prefix        = (user.get("file_prefix") or "").strip()
        name_no_ext, ext = _split_ext(original_name)

        new_name = f"{prefix} {name_no_ext}{ext}".strip() if prefix else original_name

        dl_path       = os.path.join(DOWNLOAD_DIR, f"{uid}_{message.message_id}{ext}")
        processed_path = None
        thumb_dl_path  = None

        try:
            # ── 1. Download file ───────────────────────────────
            log.info("⬇️  Downloading for user=%s | %s → %s",
                     user["name"], original_name, new_name)
            ok = await _download_file(context.bot, media.file_id, dl_path)
            if not ok:
                await increment_stats(uid, failed=True)
                state.stats["failed"] += 1
                continue

            # ── 2. Get thumbnail ───────────────────────────────
            thumb_file_id = user.get("thumb")
            if thumb_file_id:
                # Download user's custom thumbnail
                thumb_dl_path = dl_path + "_thumb.jpg"
                await _download_file(context.bot, thumb_file_id, thumb_dl_path)
            elif is_video(dl_path):
                # Auto-extract frame from video as thumbnail
                thumb_dl_path = await extract_thumb_from_video(dl_path)

            # ── 3. ffmpeg: embed metadata + thumbnail ──────────
            log.info("⚙️  Processing metadata for user=%s", user["name"])
            processed_path = await embed_metadata(
                input_path = dl_path,
                thumb_path = thumb_dl_path,
                title      = new_name,
            )

            # ── 4. Build caption ───────────────────────────────
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

            # ── 5. Upload to destination ───────────────────────
            log.info("⬆️  Uploading for user=%s | %s", user["name"], new_name)
            await _upload_file(
                bot          = context.bot,
                message      = message,
                dest_channel = dest,
                file_path    = processed_path,
                new_name     = new_name,
                caption      = caption,
                thumb_path   = thumb_dl_path,
            )

            # ── 6. Stats ───────────────────────────────────────
            await increment_stats(uid)
            state.stats["total"] += 1
            state.stats["by_user"][user["name"]] = (
                state.stats["by_user"].get(user["name"], 0) + 1
            )
            log.info("✅ Done | user=%s | %s → %s", user["name"], original_name, new_name)

        except TelegramError as exc:
            err = str(exc)
            log.error("❌ TelegramError for user=%s: %s", user["name"], err)
            await increment_stats(uid, failed=True)
            state.stats["failed"] += 1

        except Exception as exc:
            log.error("❌ Unexpected error for user=%s: %s", user["name"], exc)
            await increment_stats(uid, failed=True)
            state.stats["failed"] += 1

        finally:
            # ── 7. Cleanup ALL temp files ──────────────────────
            to_clean = [dl_path, thumb_dl_path]
            if processed_path and processed_path != dl_path:
                to_clean.append(processed_path)
            _cleanup(*to_clean)
            state.active_tasks[uid] = max(0, state.active_tasks.get(uid, 1) - 1)


# ──────────────────────────────────────────────────────────────
# THUMBNAIL PHOTO HANDLER
# ──────────────────────────────────────────────────────────────

async def handle_thumb_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves a photo sent in private chat as user's thumbnail."""
    message = update.message
    if not message or not message.photo:
        return

    user_id = message.from_user.id
    if not state.awaiting_thumb.pop(user_id, False):
        return

    photo   = message.photo[-1]   # highest resolution
    file_id = photo.file_id

    await update_user(user_id, thumb=file_id)
    await message.reply_text(
        "✅ <b>Thumbnail saved!</b>\n\n"
        "All future leeched files will have this thumbnail embedded.\n"
        "Use /removethumb to clear it.",
        parse_mode=ParseMode.HTML,
    )
    log.info("Thumbnail saved for user_id=%s", user_id)
