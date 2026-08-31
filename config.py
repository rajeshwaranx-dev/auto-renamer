"""
config.py — Environment variables and constants.

Environment Variables:
  BOT_TOKEN      = Telegram bot token
  ADMIN_IDS      = Comma-separated admin Telegram user IDs
  MONGO_URL      = MongoDB connection string
  MONGO_DB_NAME  = MongoDB database name (default: leech_bot)
  DOWNLOAD_DIR   = Temp directory for downloads (default: /tmp/leech)
"""

import os
import logging

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("leechbot")

BOT_TOKEN    = os.getenv("BOT_TOKEN", "8361529441:AAGL0lmdJMTQs3QhxSLFCD-UKA1Qk9NVJKg")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "7246154050").split(",") if x.strip()]
MONGO_URL    = os.getenv("MONGO_URL", "mongodb+srv://Askrss:Askrssx@cluster0.1mqswlh.mongodb.net/?appName=Cluster0")
MONGO_DB     = os.getenv("MONGO_DB_NAME", "Askrss")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/leech")
# Pyrogram — for large file downloads
API_ID         = int(os.getenv("API_ID", "23361081") or "0")
API_HASH       = os.getenv("API_HASH", "0605c5395b91ead763072251e20c3417")
SESSION_STRING = os.getenv("SESSION_STRING", "")   # optional user session for 4GB
# Bot-wide log channel (set by admin via /bsettings)
# Can also be set in .env as fallback
BOT_LOG_CHANNEL = os.getenv("BOT_LOG_CHANNEL", "")

# Default caption template placeholders:
#   {filename}  original filename
#   {newname}   renamed filename (prefix + name)
#   {name}      name without extension
#   {ext}       file extension
#   {prefix}    user's prefix
#   {size}      human-readable file size
DEFAULT_CAPTION = "<b>{newname}</b>"

# Max file size bot API supports (2 GB)
MAX_BOT_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB in bytes
