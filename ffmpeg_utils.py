"""
ffmpeg_utils.py — Embed thumbnail, FULLY strip old metadata, set new metadata.
"""
import asyncio, os, re
from config import log

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wav"}

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

# ── Language / Quality detection ───────────────────────────────

LANG_MAP = {
    "tamil":"Tamil","tam":"Tamil","tgl":"Tamil",
    "telugu":"Telugu","tel":"Telugu",
    "hindi":"Hindi","hin":"Hindi",
    "english":"English","eng":"English",
    "malayalam":"Malayalam","mal":"Malayalam",
    "kannada":"Kannada","kan":"Kannada",
    "bengali":"Bengali","ben":"Bengali",
    "marathi":"Marathi","mar":"Marathi",
}
QUALITY_MAP = {
    "4k":"4K","2160p":"4K","1080p":"1080p","fhd":"1080p",
    "720p":"720p","hd":"720p","480p":"480p","360p":"360p",
    "hdrip":"HDRip","webrip":"WEBRip","web-dl":"WEB-DL",
    "webdl":"WEB-DL","bluray":"BluRay","blu-ray":"BluRay",
    "hdcam":"HDCAM","camrip":"CAMRip",
}
SOURCE_MAP = {
    "web-dl":"WEB-DL","webdl":"WEB-DL","webrip":"WEBRip",
    "hdrip":"HDRip","bluray":"BluRay","blu-ray":"BluRay",
    "hdcam":"HDCAM","camrip":"CAMRip","dvdrip":"DVDRip",
}

def extract_languages(filename):
    lower = filename.lower().replace("_"," ").replace("-"," ")
    found = []
    for key, name in LANG_MAP.items():
        if re.search(r'\b' + re.escape(key) + r'\b', lower) and name not in found:
            found.append(name)
    return found

def extract_quality(filename):
    lower = filename.lower()
    for key, val in QUALITY_MAP.items():
        if key in lower: return val
    return ""

def extract_source(filename):
    lower = filename.lower()
    for key, val in SOURCE_MAP.items():
        if key in lower: return val
    return ""

# ── Thumbnail extraction ───────────────────────────────────────

async def extract_thumb_from_video(video_path):
    thumb_path = video_path + "_thumb.jpg"
    cmd = ["ffmpeg","-y","-ss","00:00:05","-i",video_path,
           "-vframes","1","-q:v","2",thumb_path]
    code, _ = await _run(cmd)
    if code == 0 and os.path.exists(thumb_path):
        return thumb_path
    return None

# ── Count audio streams ────────────────────────────────────────

async def _count_audio_streams(input_path):
    cmd = ["ffprobe","-v","error","-select_streams","a",
           "-show_entries","stream=index","-of","csv=p=0",input_path]
    proc = await asyncio.create_subprocess_exec(*cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    streams = [x for x in stdout.decode().strip().split("\n") if x.strip()]
    return len(streams)

# ── Main embed ─────────────────────────────────────────────────

async def embed_metadata(input_path, thumb_path, title, custom_metadata=None):
    ext      = os.path.splitext(input_path)[1].lower()
    out_path = input_path + "_processed" + ext

    if is_video(input_path):
        ok = await _process_video(input_path, out_path, thumb_path, title, custom_metadata)
    elif is_audio(input_path):
        ok = await _process_audio(input_path, out_path, thumb_path, title, custom_metadata)
    else:
        return input_path

    if ok and os.path.exists(out_path):
        return out_path
    log.warning("ffmpeg failed — using original")
    return input_path


async def _process_video(input_path, output_path, thumb_path, title, custom_metadata):
    meta         = custom_metadata or {}
    audio_count  = await _count_audio_streams(input_path)
    audio_title  = meta.get("audio_title", "")

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if thumb_path and os.path.exists(thumb_path):
        cmd += ["-i", thumb_path]
        cmd += ["-map","0","-map","1"]
        cmd += ["-c","copy","-c:v:1","mjpeg","-disposition:v:1","attached_pic"]
    else:
        cmd += ["-map","0","-c","copy"]

    # ── Strip ALL global metadata ──────────────────────────────
    cmd += ["-map_metadata", "-1"]

    # ── Strip ALL stream metadata ──────────────────────────────
    cmd += ["-map_metadata:s", "-1"]

    # ── Set new global title ───────────────────────────────────
    cmd += ["-metadata", f"title={meta.get('title', title)}"]
    if meta.get("comment"):
        cmd += ["-metadata", f"comment={meta['comment']}"]
    if meta.get("artist"):
        cmd += ["-metadata", f"artist={meta['artist']}"]

    # ── Set each audio stream title (wipes old channel names) ──
    for i in range(audio_count):
        cmd += [f"-metadata:s:a:{i}", f"title={audio_title}"]
        cmd += [f"-metadata:s:a:{i}", "handler_name="]

    cmd.append(output_path)
    code, err = await _run(cmd)
    if code != 0:
        log.error("ffmpeg video error: %s", err[:400])
        return False
    return True


async def _process_audio(input_path, output_path, thumb_path, title, custom_metadata):
    meta = custom_metadata or {}
    cmd  = ["ffmpeg", "-y", "-i", input_path]
    if thumb_path and os.path.exists(thumb_path):
        cmd += ["-i", thumb_path,
                "-map","0:a","-map","1:v","-c","copy",
                "-id3v2_version","3",
                "-metadata:s:v","title=Album cover",
                "-metadata:s:v","comment=Cover (front)"]
    else:
        cmd += ["-map","0","-c","copy"]

    cmd += ["-map_metadata","-1","-map_metadata:s","-1"]
    cmd += ["-metadata", f"title={meta.get('title', title)}"]
    if meta.get("artist"):
        cmd += ["-metadata", f"artist={meta['artist']}"]
    cmd.append(output_path)
    code, err = await _run(cmd)
    if code != 0:
        log.error("ffmpeg audio error: %s", err[:400])
        return False
    return True
