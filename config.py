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

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
MONGO_URL    = os.getenv("MONGO_URL", "")
MONGO_DB     = os.getenv("MONGO_DB_NAME", "leech_bot")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/leech")

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
