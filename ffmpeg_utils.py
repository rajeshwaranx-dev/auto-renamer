"""
ffmpeg_utils.py — Embed thumbnail and metadata into media files using ffmpeg.

Supports:
  - Video files (.mp4, .mkv, .avi, .mov, .webm, etc.)
  - Audio files (.mp3, .m4a, .flac, .ogg, etc.)
  - Documents (skipped — no ffmpeg processing)
"""

import asyncio
import os
import shutil
import tempfile
from config import log


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wav"}


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def human_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


async def _run(cmd: list[str]) -> tuple[int, str]:
    """Run a shell command asynchronously. Returns (returncode, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode(errors="replace")


# ──────────────────────────────────────────────────────────────
# THUMBNAIL EXTRACTION FROM VIDEO (if no custom thumb set)
# ──────────────────────────────────────────────────────────────

async def extract_thumb_from_video(video_path: str) -> str | None:
    """Extract a frame from a video as thumbnail. Returns path or None."""
    thumb_path = video_path + "_thumb.jpg"
    cmd = [
        "ffmpeg", "-y",
        "-ss", "00:00:05",          # grab frame at 5 seconds
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path,
    ]
    code, err = await _run(cmd)
    if code == 0 and os.path.exists(thumb_path):
        return thumb_path
    log.warning("Thumb extraction failed: %s", err[:200])
    return None


# ──────────────────────────────────────────────────────────────
# EMBED THUMBNAIL + METADATA INTO VIDEO
# ──────────────────────────────────────────────────────────────

async def process_video(
    input_path: str,
    output_path: str,
    thumb_path: str | None,
    title: str,
) -> bool:
    """
    Embed thumbnail and title metadata into a video file.
    Returns True on success.
    """
    cmd = ["ffmpeg", "-y", "-i", input_path]

    if thumb_path and os.path.exists(thumb_path):
        cmd += ["-i", thumb_path]
        cmd += [
            "-map", "0",          # all streams from input video
            "-map", "1",          # thumbnail stream
            "-c", "copy",         # no re-encode — very fast
            "-c:v:1", "mjpeg",    # encode thumb as jpeg
            "-disposition:v:1", "attached_pic",  # mark as cover art
        ]
    else:
        cmd += ["-map", "0", "-c", "copy"]

    # Embed title metadata
    cmd += [
        "-metadata", f"title={title}",
        "-metadata", f"comment=Processed by LeechBot",
    ]
    cmd.append(output_path)

    code, err = await _run(cmd)
    if code != 0:
        log.error("ffmpeg video processing failed: %s", err[:300])
        return False
    return True


# ──────────────────────────────────────────────────────────────
# EMBED THUMBNAIL + METADATA INTO AUDIO (mp3/m4a)
# ──────────────────────────────────────────────────────────────

async def process_audio(
    input_path: str,
    output_path: str,
    thumb_path: str | None,
    title: str,
) -> bool:
    """
    Embed thumbnail and title metadata into an audio file.
    Returns True on success.
    """
    cmd = ["ffmpeg", "-y", "-i", input_path]

    if thumb_path and os.path.exists(thumb_path):
        cmd += ["-i", thumb_path]
        cmd += [
            "-map", "0:a",
            "-map", "1:v",
            "-c", "copy",
            "-id3v2_version", "3",
            "-metadata:s:v", "title=Album cover",
            "-metadata:s:v", "comment=Cover (front)",
        ]
    else:
        cmd += ["-map", "0", "-c", "copy"]

    cmd += ["-metadata", f"title={title}"]
    cmd.append(output_path)

    code, err = await _run(cmd)
    if code != 0:
        log.error("ffmpeg audio processing failed: %s", err[:300])
        return False
    return True


# ──────────────────────────────────────────────────────────────
# MAIN ENTRY — auto-detect file type and process
# ──────────────────────────────────────────────────────────────

async def embed_metadata(
    input_path: str,
    thumb_path: str | None,
    title: str,
) -> str:
    """
    Embed thumbnail + metadata into a media file.

    Returns:
      - Path to processed output file (may be different from input)
      - Same as input_path if file type is not supported (documents)

    The caller is responsible for deleting both input and output files.
    """
    ext       = os.path.splitext(input_path)[1].lower()
    out_path  = input_path + "_processed" + ext

    if is_video(input_path):
        log.info("📹 Processing video: %s", os.path.basename(input_path))
        ok = await process_video(input_path, out_path, thumb_path, title)
        if ok and os.path.exists(out_path):
            return out_path
        log.warning("Video processing failed — using original file")
        return input_path

    elif is_audio(input_path):
        log.info("🎵 Processing audio: %s", os.path.basename(input_path))
        ok = await process_audio(input_path, out_path, thumb_path, title)
        if ok and os.path.exists(out_path):
            return out_path
        log.warning("Audio processing failed — using original file")
        return input_path

    else:
        # Document — no ffmpeg processing, just rename
        log.info("📄 Document file — skipping ffmpeg processing")
        return input_path
