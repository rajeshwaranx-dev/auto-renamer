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
