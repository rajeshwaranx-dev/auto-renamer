"""
commands_user.py — Commands for registered users.
"""

import functools
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import DEFAULT_CAPTION, log
from database import get_user, update_user, add_source_channel, remove_source_channel
import state


def user_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid  = update.effective_user.id if update.effective_user else None
        user = await get_user(uid)
        if not user:
            await update.message.reply_text(
                "⛔ You are not registered.\nAsk an admin to add you with /adduser."
            )
            return
        if not user.get("active"):
            await update.message.reply_text("⛔ Your account is currently disabled.")
            return
        return await func(update, context)
    return wrapper


@user_only
async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = await get_user(uid)
    sources = "\n".join(
        f"   • <code>{s}</code>" for s in (user.get("source_channels") or [])
    ) or "   None"
    caption_preview = (user.get("caption_template") or "—")[:120]
    text = (
        f"👤 <b>Your Configuration</b>\n\n"
        f"Name:      <b>{user['name']}</b>\n"
        f"Status:    🟢 Active\n\n"
        f"📥 <b>Source channels:</b>\n{sources}\n\n"
        f"📤 <b>Dest channel:</b>  <code>{user.get('dest_channel') or '—'}</code>\n"
        f"🏷 <b>Prefix:</b>        <code>{user.get('file_prefix') or '—'}</code>\n"
        f"🖼 <b>Thumbnail:</b>     {'✅ Set' if user.get('thumb') else '❌ Not set'}\n"
        f"📝 <b>Caption:</b>\n<code>{caption_preview}</code>\n\n"
        f"📊 <b>Posts:</b> {user.get('stats', {}).get('total', 0)} | "
        f"Failed: {user.get('stats', {}).get('failed', 0)}\n\n"
        f"<b>Caption placeholders:</b>\n"
        f"<code>{{filename}}</code> · <code>{{newname}}</code> · <code>{{name}}</code> · "
        f"<code>{{ext}}</code> · <code>{{prefix}}</code> · <code>{{size}}</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@user_only
async def setsource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/setsource &lt;channel_id&gt;</code>\n\n"
            "💡 Forward any message from your channel to @userinfobot to get the ID.\n"
            "Looks like: <code>-1001234567890</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return
    channel_id = args[0].strip()
    if not channel_id.lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ Channel ID must be a number like <code>-1001234567890</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    uid = update.effective_user.id
    ok  = await add_source_channel(uid, channel_id)
    if ok:
        await update.message.reply_text(
            f"✅ Source channel added: <code>{channel_id}</code>\n\n"
            f"⚠️ Make sure the bot is a <b>member</b> of that channel.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"⚠️ <code>{channel_id}</code> already in your sources.",
            parse_mode=ParseMode.HTML,
        )


@user_only
async def removesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/removesource &lt;channel_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    channel_id = args[0].strip()
    uid = update.effective_user.id
    ok  = await remove_source_channel(uid, channel_id)
    msg = (f"✅ Removed: <code>{channel_id}</code>" if ok
           else f"⚠️ <code>{channel_id}</code> not found in your sources.")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@user_only
async def setchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/setchannel &lt;channel_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    channel_id = args[0].strip()
    if not channel_id.lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ Channel ID must be a number like <code>-1001234567890</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    uid = update.effective_user.id
    await update_user(uid, dest_channel=channel_id)
    await update.message.reply_text(
        f"✅ Destination channel set: <code>{channel_id}</code>\n\n"
        f"⚠️ Make sure bot is <b>admin with post permission</b> in that channel.",
        parse_mode=ParseMode.HTML,
    )


@user_only
async def setprefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/setprefix &lt;text&gt;</code>\n\n"
            "Examples:\n"
            "<code>/setprefix @AskMovies4</code>\n"
            "<code>/setprefix [AskMovies]</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    prefix  = " ".join(args).strip()
    uid     = update.effective_user.id
    await update_user(uid, file_prefix=prefix)
    example = f"{prefix} Movie.Name.2024.1080p.mkv"
    await update.message.reply_text(
        f"✅ Prefix set: <code>{prefix}</code>\n\n"
        f"📄 Example: <code>{example}</code>",
        parse_mode=ParseMode.HTML,
    )


@user_only
async def removeprefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update_user(uid, file_prefix="")
    await update.message.reply_text("✅ Prefix cleared.")


@user_only
async def setcaption_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/setcaption &lt;template&gt;</code>\n\n"
            "<b>Placeholders:</b>\n"
            "<code>{filename}</code> — original filename\n"
            "<code>{newname}</code>  — renamed filename\n"
            "<code>{name}</code>     — name without extension\n"
            "<code>{ext}</code>      — extension\n"
            "<code>{prefix}</code>   — your prefix\n"
            "<code>{size}</code>     — file size\n\n"
            "<b>Example:</b>\n"
            "<code>/setcaption 🎬 &lt;b&gt;{newname}&lt;/b&gt;\n📦 {size}\n\n📢 @AskMovies4</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    template = " ".join(args).strip()
    uid      = update.effective_user.id
    await update_user(uid, caption_template=template)
    await update.message.reply_text(
        f"✅ Caption saved:\n\n<code>{template}</code>",
        parse_mode=ParseMode.HTML,
    )


@user_only
async def resetcaption_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update_user(uid, caption_template=DEFAULT_CAPTION)
    await update.message.reply_text(
        f"✅ Caption reset to default:\n<code>{DEFAULT_CAPTION}</code>",
        parse_mode=ParseMode.HTML,
    )


@user_only
async def setthumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state.awaiting_thumb[uid] = True
    await update.message.reply_text(
        "🖼 <b>Send me a photo</b> to use as thumbnail.\n\n"
        "• Recommended: 320×320 px\n"
        "• Send as <b>photo</b>, not as file\n"
        "• This will be embedded into every processed file's metadata",
        parse_mode=ParseMode.HTML,
    )


@user_only
async def removethumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update_user(uid, thumb=None)
    state.awaiting_thumb.pop(uid, None)
    await update.message.reply_text(
        "✅ Thumbnail removed.\n"
        "Videos will use auto-extracted frame as thumbnail."
    )
