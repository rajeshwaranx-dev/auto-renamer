import asyncio, os, re
from config import log

VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".webm",".flv",".ts",".m4v"}
AUDIO_EXTS = {".mp3",".m4a",".flac",".ogg",".opus",".aac",".wav"}

def is_video(path): return os.path.splitext(path)[1].lower() in VIDEO_EXTS
def is_audio(path): return os.path.splitext(path)[1].lower() in AUDIO_EXTS

def human_size(size_bytes):
    for unit in ["B","KB","MB","GB"]:
        if size_bytes < 1024: return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

async def _run(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode(errors="replace")

# ── Language detection ─────────────────────────────────────────

LANG_PATTERNS = [
    ("Tamil",     [r"\btamil\b", r"\btam\b", r"\btgl\b"]),
    ("Telugu",    [r"\btelugu\b", r"\btel\b", r"\btelu\b"]),
    ("Hindi",     [r"\bhindi\b", r"\bhin\b"]),
    ("English",   [r"\benglish\b", r"\beng\b"]),
    ("Malayalam", [r"\bmalayalam\b", r"\bmal\b"]),
    ("Kannada",   [r"\bkannada\b", r"\bkan\b"]),
    ("Bengali",   [r"\bbengali\b", r"\bben\b"]),
    ("Marathi",   [r"\bmarathi\b", r"\bmar\b"]),
    ("Chinese",   [r"\bchinese\b", r"\bchi\b", r"\bchn\b", r"\bmandarin\b"]),
    ("Japanese",  [r"\bjapanese\b", r"\bjpn\b"]),
    ("Korean",    [r"\bkorean\b", r"\bkor\b"]),
    ("Spanish",   [r"\bspanish\b", r"\bspa\b"]),
    ("Arabic",    [r"\barabic\b", r"\bara\b"]),
    ("Russian",   [r"\brussian\b", r"\brus\b"]),
    ("Dual Audio",[r"\bdual\s*audio\b", r"\bdual\b"]),
    ("Multi Audio",[r"\bmulti\s*audio\b", r"\bmulti\b"]),
]

def extract_languages(filename: str) -> list[str]:
    # Normalize: replace _ . - with space
    text = re.sub(r"[_.\-\+\[\]]", " ", filename.lower())
    found = []
    for lang, patterns in LANG_PATTERNS:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                found.append(lang)
                break
    return found

# ── Quality detection ──────────────────────────────────────────
# Returns (resolution, source) separately then combines

RESOLUTION_RULES = [
    (r"\b4k\b|\b2160p\b",           "4K"),
    (r"\b1080p\b|\bfhd\b",          "1080p"),
    (r"\b720p\b|\bhdready\b",       "720p"),
    (r"\b480p\b|\bsd\b(?!.*\d{3}p)","480p"),
    (r"\b360p\b",                   "360p"),
    (r"\b240p\b",                   "240p"),
]

SOURCE_RULES = [
    (r"\bweb[\s\-]?dl\b",                  "WEB-DL"),
    (r"\bweb[\s\-]?rip\b",                 "WEBRip"),
    (r"\bblu[\s\-]?ray\b|\bbdrip\b",       "BluRay"),
    (r"\bhd[\s\-]?rip\b",                  "HDRip"),
    (r"\bhd[\s\-]?cam\b",                  "HDCAM"),
    (r"\bcam[\s\-]?rip\b",                 "CAMRip"),
    (r"\bpre[\s\-]?dvd[\s\-]?rip\b",       "PreDVDRip"),
    (r"\bpre[\s\-]?dvd\b",                 "PreDVD"),
    (r"\bdvd[\s\-]?rip\b",                 "DVDRip"),
    (r"\bdvd[\s\-]?scr\b|\bdvdscr\b",      "DVDScr"),
    (r"\bts\b|\btelesync\b",               "TS"),
    (r"\btc\b|\btele[\s\-]?cine\b",        "TC"),
    (r"\bscr\b|\bscreener\b",              "SCR"),
    (r"\bhq\b",                            "HQ"),
]

CODEC_RULES = [
    (r"\bx265\b|\bhevc\b|\bh\.?265\b",    "x265"),
    (r"\bx264\b|\bavc\b|\bh\.?264\b",     "x264"),
    (r"\bxvid\b",                          "XviD"),
]

def extract_quality(filename: str) -> str:
    """
    Returns combined quality string like:
    '1080p WEB-DL x264' or 'HQ PreDVDRip' or '720p' etc.
    Returns '' if nothing detected.
    """
    text = re.sub(r"[_.\+]", " ", filename.lower())

    # Resolution
    resolution = ""
    for pat, val in RESOLUTION_RULES:
        if re.search(pat, text, re.IGNORECASE):
            resolution = val
            break

    # Source
    source = ""
    for pat, val in SOURCE_RULES:
        if re.search(pat, text, re.IGNORECASE):
            source = val
            break

    # Codec (optional)
    codec = ""
    for pat, val in CODEC_RULES:
        if re.search(pat, text, re.IGNORECASE):
            codec = val
            break

    parts = [p for p in [resolution, source, codec] if p]
    return " ".join(parts)

def extract_source(filename: str) -> str:
    text = re.sub(r"[_.\+]", " ", filename.lower())
    for pat, val in SOURCE_RULES:
        if re.search(pat, text, re.IGNORECASE):
            return val
    return ""

# ── Thumbnail extraction ───────────────────────────────────────

async def extract_thumb_from_video(video_path):
    thumb = video_path + "_thumb.jpg"
    code, _ = await _run(["ffmpeg","-y","-ss","00:00:05","-i",video_path,
                           "-vframes","1","-q:v","2",thumb])
    return thumb if code == 0 and os.path.exists(thumb) else None

async def _count_audio_streams(input_path):
    proc = await asyncio.create_subprocess_exec(
        "ffprobe","-v","error","-select_streams","a",
        "-show_entries","stream=index","-of","csv=p=0",input_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    return len([x for x in stdout.decode().strip().split("\n") if x.strip()])

# ── Main embed ─────────────────────────────────────────────────

async def embed_metadata(input_path, thumb_path, title, custom_metadata=None):
    ext      = os.path.splitext(input_path)[1].lower()
    out_path = input_path + "_processed" + ext
    meta     = custom_metadata or {}

    if is_video(input_path):
        ok = await _embed_video(input_path, out_path, thumb_path, title, meta)
    elif is_audio(input_path):
        ok = await _embed_audio(input_path, out_path, thumb_path, title, meta)
    else:
        return input_path

    return out_path if ok and os.path.exists(out_path) else input_path


async def _embed_video(inp, out, thumb, title, meta):
    n_audio     = await _count_audio_streams(inp)
    audio_title = meta.get("audio_title", "")
    cmd = ["ffmpeg", "-y", "-i", inp]
    if thumb and os.path.exists(thumb):
        cmd += ["-i", thumb, "-map","0","-map","1","-c","copy",
                "-c:v:1","mjpeg","-disposition:v:1","attached_pic"]
    else:
        cmd += ["-map","0","-c","copy"]
    # Strip ALL existing metadata
    cmd += ["-map_metadata","-1","-map_metadata:s","-1"]
    cmd += ["-metadata", f"title={meta.get('title', title)}"]
    if meta.get("comment"): cmd += ["-metadata", f"comment={meta['comment']}"]
    if meta.get("artist"):  cmd += ["-metadata", f"artist={meta['artist']}"]
    # Clear each audio stream title
    for i in range(n_audio):
        cmd += [f"-metadata:s:a:{i}", f"title={audio_title}"]
        cmd += [f"-metadata:s:a:{i}", "handler_name="]
    cmd.append(out)
    code, err = await _run(cmd)
    if code != 0: log.error("ffmpeg video: %s", err[:400]); return False
    return True


async def _embed_audio(inp, out, thumb, title, meta):
    cmd = ["ffmpeg","-y","-i",inp]
    if thumb and os.path.exists(thumb):
        cmd += ["-i",thumb,"-map","0:a","-map","1:v","-c","copy",
                "-id3v2_version","3","-metadata:s:v","title=Album cover",
                "-metadata:s:v","comment=Cover (front)"]
    else:
        cmd += ["-map","0","-c","copy"]
    cmd += ["-map_metadata","-1","-map_metadata:s","-1"]
    cmd += ["-metadata",f"title={meta.get('title',title)}"]
    if meta.get("artist"): cmd += ["-metadata",f"artist={meta['artist']}"]
    cmd.append(out)
    code, err = await _run(cmd)
    if code != 0: log.error("ffmpeg audio: %s", err[:400]); return False
    return True


# ── Admin Command Handlers ─────────────────────────────────────

async def start_command(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        f"I'm an Auto Renamer Bot.\n"
        f"Send me a video or audio file and I'll rename it for you.\n\n"
        f"Use /commands to see all available commands."
    )

async def commands_command(update, context):
    await update.message.reply_text(
        "📋 <b>Available Commands</b>\n\n"
        "<b>Admin Commands:</b>\n"
        "/adduser &lt;user_id&gt; - Add a user\n"
        "/removeuser &lt;user_id&gt; - Remove a user\n"
        "/listusers - List all users\n"
        "/userinfo &lt;user_id&gt; - Get user info\n"
        "/toggleuser &lt;user_id&gt; - Toggle user access\n"
        "/stats - Bot statistics\n"
        "/broadcast &lt;message&gt; - Broadcast to all users\n\n"
        "<b>User Commands:</b>\n"
        "/myinfo - Your info\n"
        "/status - Queue status\n"
        "/settings - Your settings",
        parse_mode="HTML"
    )

async def adduser_command(update, context):
    from config import ADMIN_IDS
    from database import add_user
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    if not context.args:
        return await update.message.reply_text("Usage: /adduser <user_id>")
    try:
        user_id = int(context.args[0])
        await add_user(user_id)
        await update.message.reply_text(f"✅ User {user_id} added successfully.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def removeuser_command(update, context):
    from config import ADMIN_IDS
    from database import remove_user
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    if not context.args:
        return await update.message.reply_text("Usage: /removeuser <user_id>")
    try:
        user_id = int(context.args[0])
        await remove_user(user_id)
        await update.message.reply_text(f"✅ User {user_id} removed successfully.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def listusers_command(update, context):
    from config import ADMIN_IDS
    from database import all_users
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    try:
        users = await all_users()
        if not users:
            return await update.message.reply_text("No users found.")
        text = "👥 <b>Users:</b>\n" + "\n".join([f"• <code>{u}</code>" for u in users])
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def userinfo_command(update, context):
    from config import ADMIN_IDS
    from database import get_user
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    if not context.args:
        return await update.message.reply_text("Usage: /userinfo <user_id>")
    try:
        user_id = int(context.args[0])
        info = await get_user(user_id)
        await update.message.reply_text(f"ℹ️ User info:\n<pre>{info}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def toggleuser_command(update, context):
    from config import ADMIN_IDS
    from database import toggle_user
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    if not context.args:
        return await update.message.reply_text("Usage: /toggleuser <user_id>")
    try:
        user_id = int(context.args[0])
        result = await toggle_user(user_id)
        await update.message.reply_text(f"✅ User {user_id} access toggled. Status: {result}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def stats_command(update, context):
    from config import ADMIN_IDS
    from database import all_users
    import state
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    try:
        users = await all_users()
        total = state.stats.get("total", 0)
        await update.message.reply_text(
            f"📊 <b>Bot Statistics</b>\n\n"
            f"👥 Total Users: {len(users)}\n"
            f"📁 Files Processed: {total}",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def broadcast_command(update, context):
    from config import ADMIN_IDS
    from database import all_users
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not an admin.")
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast <message>")
    msg = " ".join(context.args)
    users = await all_users()
    success, failed = 0, 0
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            success += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Broadcast done.\nSuccess: {success}\nFailed: {failed}")
    
