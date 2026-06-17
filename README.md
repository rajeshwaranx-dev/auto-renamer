<div align="center">

<img src="https://graph.org/file/95d62e76561c535607bc3-8d068525a907f613ff.jpg" width="150" height="150" style="border-radius: 50%;" alt="Ask Auto Renamer Logo"/>

# 🎬 Ask Auto Renamer Bot

**Automatically rename, thumbnail & deliver files to your Telegram channel — hands free.**

[![Python](https://img.shields.io/badge/Python-3.12.3-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Pyrofork](https://img.shields.io/badge/Pyrofork-2.3.69-00B2FF?style=for-the-badge&logo=telegram&logoColor=white)](https://github.com/TeamPGM/Pyrogram)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://mongodb.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)
[![Telegram](https://img.shields.io/badge/Channel-AskBotz-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/AskBotz)

</div>

---

## ✨ What It Does

Upload any file to your **log channel** — the bot automatically:

- 🏷️ **Renames** the file with your custom format
- 🖼️ **Applies** your custom thumbnail
- 📝 **Adds** prefix, caption & metadata
- 📤 **Delivers** it clean to your destination channel

No manual steps. No repeated work. Just upload and done.

---

## 📁 Supported File Types

| Type | Formats |
|------|---------|
| 🎬 Video | `.mp4`, `.mkv`, `.m4v` |
| 🎵 Audio | `.mp3`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.aac`, `.wav` |
| 📄 Document | `.pdf`, `.zip`, `.rar` and all other formats |

---

## ⚙️ Features

- ✅ Auto rename on upload — no commands needed
- ✅ Custom thumbnail support
- ✅ Prefix & caption injection
- ✅ Metadata editing
- ✅ Queue system with active task tracking
- ✅ Progress updates during upload
- ✅ Supports all file types
- ✅ Systemd service — runs 24/7 on VPS

---

## 🚀 Deployment Guide

### Prerequisites

- Ubuntu VPS (DigitalOcean / any provider)
- Python 3.10+
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- Bot token from [@BotFather](https://t.me/BotFather)

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/rajeshwaranx-dev/auto-renamer
cd auto-renamer
```

---

### Step 2 — Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in your values:

```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
LOG_CHANNEL=your_log_channel_id
DEST_CHANNEL=your_destination_channel_id
MONGO_URI=your_mongodb_uri
```

---

### Step 3 — Run setup script

```bash
bash setup.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Register and start the systemd service automatically

---

### Step 4 — Verify it's running

```bash
systemctl status auto-renamer
```

---

## 🛠️ Manual Commands

```bash
# Start the bot
systemctl start auto-renamer

# Stop the bot
systemctl stop auto-renamer

# Restart the bot
systemctl restart auto-renamer

# View live logs
journalctl -u auto-renamer -f
```

---

## 📦 Dependencies

| Package | Version |
|---------|---------|
| pyrofork | 2.3.69 |
| TgCrypto | 1.2.5 |
| python-telegram-bot | 21.6 |
| motor | 3.6.0 |
| pymongo | 4.10.1 |
| aiohttp | 3.13.5 |
| aiofiles | 25.1.0 |
| Pillow | 12.2.0 |
| hachoir | 3.3.0 |
| requests | 2.32.3 |

---

## 📂 Project Structure

```
auto-renamer/
├── main.py               # Entry point
├── handlers.py           # Core rename & upload logic
├── commands_admin.py     # Admin commands
├── commands_user.py      # User commands
├── config.py             # Config loader
├── database.py           # MongoDB operations
├── ffmpeg_utils.py       # FFmpeg thumbnail & metadata
├── bsettings.py          # Bot settings
├── settings.py           # Global settings
├── state.py              # Task queue & state
├── logger.py             # Logging setup
├── .env.example          # Environment template
├── requirements.txt      # Pinned dependencies
├── auto-renamer.service  # Systemd service file
└── setup.sh              # One-command deployment
```

---

## 👤 Author & Support

<div align="center">

Made with ❤️ by **AskBotz**

[![Telegram Channel](https://img.shields.io/badge/Join%20Channel-AskBotz-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/AskBotz)
[![Telegram Admin](https://img.shields.io/badge/Contact%20Admin-@YourUsername-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/YourUsername)

</div>

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">
⭐ Star this repo if it helped you!
</div>

