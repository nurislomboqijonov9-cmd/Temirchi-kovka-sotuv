"""KOVKA boti — Mini App ishga tushiruvchi (sotuv/qarz)."""
import os
import asyncio
import logging

from aiohttp import web as aioweb
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

import db
from miniapp import make_web_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kovka")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = db.OWNER_ID


def webapp_url():
    base = os.getenv("WEBAPP_URL") or ""
    if not base:
        dom = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        base = f"https://{dom}" if dom else ""
    return base.split("?")[0].rstrip("/") if base else ""


def _app_kb():
    url = webapp_url()
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "🔨 Ilovani ochish", web_app=WebAppInfo(url=url))]]) if url else None


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    uid = u.id
    # Ruxsat bor (ega yoki tasdiqlangan) — ilovani ochamiz
    if (not OWNER_ID) or db.ruxsat_bormi(uid):
        await update.message.reply_text(
            "🔨 *KOVKA — sotuv hisobi*\n\n"
            "Mijozlar, mahsulotlar (darvoza, eshik, reshotka…), narx, to'lov va qarz.\n"
            "Ilovani oching:",
            parse_mode="Markdown", reply_markup=_app_kb())
        return
    # Ruxsat yo'q — egaga so'rov yuboramiz
    ism = (u.full_name or u.username or str(uid))
    yangi = db.sorov_qosh(uid, ism)
    await update.message.reply_text(
        "🔒 Sizda hali ruxsat yo'q.\n"
        "So'rovingiz egaga yuborildi — tasdiqlangach /start bosing.")
    if OWNER_ID and yangi:
        uname = f" (@{u.username})" if u.username else ""
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ruxsat", callback_data=f"ruxsat:{uid}"),
            InlineKeyboardButton("❌ Rad", callback_data=f"rad:{uid}")]])
        try:
            await ctx.bot.send_message(
                OWNER_ID,
                f"🔔 Yangi xodim kirmoqchi:\n\n👤 *{ism}*{uname}\n🆔 `{uid}`",
                parse_mode="Markdown", reply_markup=kb)
        except Exception:
            log.exception("egaga so'rov yuborilmadi")


async def adminlar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ega uchun: ruxsatli xodimlar ro'yxati."""
    if update.effective_user.id != OWNER_ID:
        return
    lines = ["👑 *Doim adminlar (kodda):*"]
    for a in sorted(db.DOIM_ADMIN):
        belgi = " (ega)" if a == OWNER_ID else (" (Xusan aka)" if a == 2088026663 else "")
        lines.append(f"  • `{a}`{belgi}")
    ruxsatli = db.ruxsatlilar()
    lines.append("\n✅ *Tasdiqlangan xodimlar:*")
    if ruxsatli:
        for r in ruxsatli:
            ism = r.get("ism") or "—"
            lines.append(f"  • {ism} — `{r['uid']}`")
    else:
        lines.append("  (hozircha yo'q)")
    lines.append("\n_Qo'shish:_ `/ruxsat <id> [ism]`\n_O'chirish:_ `/ochir <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def ruxsat_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ega: /ruxsat <id> [ism] — qo'lda ruxsat berish."""
    if update.effective_user.id != OWNER_ID:
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("Foydalanish: `/ruxsat <id> [ism]`", parse_mode="Markdown")
        return
    try:
        uid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak.")
        return
    ism = " ".join(args[1:]) if len(args) > 1 else None
    db.ruxsat_qosh(uid, ism)
    await update.message.reply_text(f"✅ Ruxsat berildi: `{uid}`" + (f" — {ism}" if ism else ""),
                                    parse_mode="Markdown")
    try:
        await ctx.bot.send_message(uid, "✅ Sizga ruxsat berildi! /start bosing.")
    except Exception:
        pass


async def ochir_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ega: /ochir <id> — ruxsatni olib tashlash."""
    if update.effective_user.id != OWNER_ID:
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("Foydalanish: `/ochir <id>`", parse_mode="Markdown")
        return
    try:
        uid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak.")
        return
    if uid in db.DOIM_ADMIN:
        await update.message.reply_text("⛔ Bu ID kodda 'doim admin' — o'chirib bo'lmaydi.")
        return
    db.ruxsat_ochir(uid)
    await update.message.reply_text(f"🗑 Ruxsat olib tashlandi: `{uid}`", parse_mode="Markdown")


async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != OWNER_ID:
        await q.answer("Faqat ega tasdiqlaydi", show_alert=True)
        return
    data = q.data or ""
    if data.startswith("ruxsat:"):
        uid = int(data.split(":")[1])
        db.ruxsat_qosh(uid)
        await q.edit_message_text(f"✅ Ruxsat berildi: `{uid}`", parse_mode="Markdown")
        try:
            await ctx.bot.send_message(uid, "✅ Sizga ruxsat berildi! /start bosing.")
        except Exception:
            pass
    elif data.startswith("rad:"):
        uid = int(data.split(":")[1])
        db.sorov_ochir(uid)
        await q.edit_message_text(f"❌ Rad etildi: `{uid}`", parse_mode="Markdown")


async def run():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN yo'q — Railway Variables'ga qo'ying.")
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("adminlar", adminlar))
    app.add_handler(CommandHandler("ruxsat", ruxsat_cmd))
    app.add_handler(CommandHandler("ochir", ochir_cmd))
    app.add_handler(CallbackQueryHandler(on_cb))

    port = int(os.getenv("PORT", "8080"))
    runner = aioweb.AppRunner(make_web_app(BOT_TOKEN))
    await runner.setup()
    site = aioweb.TCPSite(runner, "0.0.0.0", port)

    await app.initialize()
    await app.start()
    await site.start()

    url = webapp_url()
    if url:
        try:
            await app.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🔨 Hisob", web_app=WebAppInfo(url=url)))
            log.info("Mini App: %s", url)
        except Exception:
            log.exception("menyu tugmasi")

    await app.updater.start_polling()
    log.info("Kovka boti + Mini App ishga tushdi (port %s)", port)
    await asyncio.Event().wait()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
