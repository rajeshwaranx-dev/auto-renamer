import functools
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import ADMIN_IDS, log
from database import get_user, all_users, add_user, remove_user, toggle_user
from ffmpeg_utils import human_size
import state

def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if uid not in ADMIN_IDS:
            await update.message.reply_text("⛔ Admin only.")
            return
        return await func(update, context)
    return wrapper

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    is_admin = uid in ADMIN_IDS
    text = (
        "🤖 <b>LeechBot</b>\n\n"
        "Auto-rename & leech bot.\n\n"
        + ("You are <b>admin</b>. Use /commands." if is_admin
           else "Use /settings to configure.")
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    is_admin = uid in ADMIN_IDS
    user_cmds = (
        "👤 <b>User Commands</b>\n"
        "/settings — Leech settings\n"
        "/myinfo — Your config\n"
        "/status — Active tasks\n"
        "/setsource &lt;id&gt; — Add source channel\n"
        "/removesource &lt;id&gt; — Remove source channel\n"
        "/setchannel &lt;id&gt; — Set destination\n"
        "/setprefix &lt;text&gt; — Set prefix\n"
        "/setthumb — Set thumbnail\n"
        "/removethumb — Remove thumbnail\n"
        "/setcaption &lt;template&gt; — Set caption\n"
        "/resetcaption — Reset caption\n"
    )
    admin_cmds = (
        "\n🔑 <b>Admin Commands</b>\n"
        "/adduser &lt;user_id&gt; &lt;name&gt; — Add user\n"
        "/removeuser &lt;user_id&gt; — Remove user\n"
        "/listusers — List all users\n"
        "/userinfo &lt;user_id&gt; — User details\n"
        "/toggleuser &lt;user_id&gt; — Enable/disable\n"
        "/stats — Bot statistics\n"
        "/broadcast &lt;text&gt; — Message all users\n"
        "/bsettings — Admin settings\n"
    )
    await update.message.reply_text(
        user_cmds + (admin_cmds if is_admin else ""),
        parse_mode=ParseMode.HTML)

@admin_only
async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /adduser <user_id> <name>"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/adduser &lt;user_id&gt; &lt;name&gt;</code>\n\n"
            "Example: <code>/adduser 1234567890 Rajesh</code>",
            parse_mode=ParseMode.HTML)
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ user_id must be a number.\n\n"
            "Example: <code>/adduser 1234567890 Rajesh</code>",
            parse_mode=ParseMode.HTML)
        return
    name = " ".join(args[1:])
    try:
        created = await add_user(user_id, name)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error: <code>{e}</code>", parse_mode=ParseMode.HTML)
        return
    if created:
        await update.message.reply_text(
            f"✅ <b>User added!</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Name: <b>{name}</b>\n\n"
            f"They can now use /settings to configure.",
            parse_mode=ParseMode.HTML)
        log.info("Added user %s (%s)", name, user_id)
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{user_id}</code> already exists.",
            parse_mode=ParseMode.HTML)

@admin_only
async def removeuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/removeuser &lt;user_id&gt;</code>",
            parse_mode=ParseMode.HTML)
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id must be a number.")
        return
    ok = await remove_user(user_id)
    if ok:
        await update.message.reply_text(
            f"🗑 User <code>{user_id}</code> removed.",
            parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{user_id}</code> not found.",
            parse_mode=ParseMode.HTML)

@admin_only
async def listusers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await all_users()
    if not users:
        await update.message.reply_text("No users registered yet.")
        return
    lines = ["👥 <b>Registered Users</b>\n"]
    for u in users:
        status  = "🟢" if u.get("active") else "🔴"
        sources = len(u.get("source_channels") or [])
        dest    = u.get("dest_channel") or "—"
        total   = u.get("stats", {}).get("total", 0)
        lines.append(
            f"{status} <b>{u['name']}</b> (<code>{u['user_id']}</code>)\n"
            f"   Sources: {sources} | Dest: <code>{dest}</code> | Posts: {total}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

@admin_only
async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/userinfo &lt;user_id&gt;</code>",
            parse_mode=ParseMode.HTML)
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id must be a number.")
        return
    u = await get_user(user_id)
    if not u:
        await update.message.reply_text(
            f"User <code>{user_id}</code> not found.", parse_mode=ParseMode.HTML)
        return
    sources = "\n".join(
        f"   • <code>{s}</code>" for s in (u.get("source_channels") or [])
    ) or "   None"
    await update.message.reply_text(
        f"👤 <b>User Info</b>\n\n"
        f"Name:        <b>{u['name']}</b>\n"
        f"ID:          <code>{u['user_id']}</code>\n"
        f"Status:      {'🟢 Active' if u.get('active') else '🔴 Disabled'}\n"
        f"Added:       {u.get('added_at', '—')[:10]}\n\n"
        f"📥 Sources:\n{sources}\n\n"
        f"📤 Dest:     <code>{u.get('dest_channel') or '—'}</code>\n"
        f"🏷 Prefix:   <code>{u.get('file_prefix') or '—'}</code>\n"
        f"🧹 Strip:    <code>{u.get('strip_words') or '—'}</code>\n"
        f"🖼 Thumb:    {'✅ Set' if u.get('thumb') else '❌ Not set'}\n"
        f"📊 Posts:    {u.get('stats',{}).get('total',0)} | "
        f"Failed: {u.get('stats',{}).get('failed',0)}",
        parse_mode=ParseMode.HTML)

@admin_only
async def toggleuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/toggleuser &lt;user_id&gt;</code>",
            parse_mode=ParseMode.HTML)
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id must be a number.")
        return
    new_state = await toggle_user(user_id)
    if new_state is None:
        await update.message.reply_text(
            f"⚠️ User <code>{user_id}</code> not found.", parse_mode=ParseMode.HTML)
    else:
        emoji = "🟢 Enabled" if new_state else "🔴 Disabled"
        await update.message.reply_text(
            f"User <code>{user_id}</code> is now <b>{emoji}</b>.",
            parse_mode=ParseMode.HTML)

@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users    = await all_users()
    active   = sum(1 for u in users if u.get("active"))
    db_total = sum(u.get("stats", {}).get("total", 0) for u in users)
    db_fail  = sum(u.get("stats", {}).get("failed", 0) for u in users)
    by_user  = "".join(
        f"  • {u['name']}: {u.get('stats',{}).get('total',0)}\n"
        for u in sorted(users,
                        key=lambda x: x.get("stats", {}).get("total", 0),
                        reverse=True)
    )
    await update.message.reply_text(
        f"📊 <b>LeechBot Stats</b>\n\n"
        f"👥 Users: {active} active / {len(users)} total\n\n"
        f"<b>Session:</b>\n"
        f"📦 Processed: {state.stats['total']}\n"
        f"❌ Failed: {state.stats['failed']}\n"
        f"⬇️ Downloaded: {human_size(state.stats['downloaded'])}\n"
        f"⬆️ Uploaded: {human_size(state.stats['uploaded'])}\n\n"
        f"<b>All time:</b>\n"
        f"📦 Total: {db_total} | ❌ Failed: {db_fail}\n\n"
        f"<b>Per user:</b>\n{by_user or '  None'}",
        parse_mode=ParseMode.HTML)

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/broadcast &lt;message&gt;</code>",
            parse_mode=ParseMode.HTML)
        return
    text  = " ".join(args)
    users = await all_users()
    sent = failed = 0
    for u in users:
        if not u.get("active"):
            continue
        try:
            await context.bot.send_message(
                chat_id=u["user_id"], text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 Broadcast done.\n✅ Sent: {sent} | ❌ Failed: {failed}")
    
