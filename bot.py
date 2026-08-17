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
        for aid in _admin_royxati():
            try:
                await ctx.bot.send_message(
                    aid,
                    f"🔔 Yangi xodim kirmoqchi:\n\n👤 *{ism}*{uname}\n🆔 `{uid}`",
                    parse_mode="Markdown", reply_markup=kb)
            except Exception:
                log.exception("so'rov yuborilmadi")


async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not db.is_admin(q.from_user.id):
        await q.answer("Faqat ega yoki admin tasdiqlaydi", show_alert=True)
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


def _admin_royxati():
    idlar = set()
    if OWNER_ID:
        idlar.add(OWNER_ID)
    for a in db.adminlar():
        idlar.add(int(a["uid"]))
    return idlar


# ---------- Admin boshqaruvi (faqat ega) ----------
async def admin_qosh_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Faqat ega admin qo'sha oladi.")
        return
    args = ctx.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "👑 Admin qo'shish: `/admin_qosh 123456789 Xusan aka`\n"
            "_(ID ni bilish: o'sha odam botga /start yozsin.)_", parse_mode="Markdown")
        return
    uid = int(args[0])
    ism = " ".join(args[1:]).strip() or None
    db.admin_qosh(uid, ism)
    await update.message.reply_text(f"✅ 👑 Admin qo'shildi: *{ism or uid}* (`{uid}`)\n"
                                    "Endi u odam qo'sha/tasdiqlay oladi.", parse_mode="Markdown")
    try:
        await ctx.bot.send_message(uid, "👑 Sizga *admin* huquqi berildi! /start bosing.", parse_mode="Markdown")
    except Exception:
        pass


async def admin_ochir_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Faqat ega o'chira oladi.")
        return
    args = ctx.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await update.message.reply_text("O'chirish: `/admin_ochir 123456789`", parse_mode="Markdown")
        return
    n = db.admin_ochir(int(args[0]))
    await update.message.reply_text("✅ Adminlikdan olindi." if n else "❌ Bunday admin yo'q.")


async def adminlar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    lst = db.adminlar()
    q = [f"👑 *Adminlar*\n\n• Ega: `{OWNER_ID}`"]
    for a in lst:
        q.append(f"• {a.get('ism') or 'Admin'}: `{a['uid']}`")
    q.append("\n_Qo'shish (ega):_ `/admin_qosh <id> <ism>`")
    await update.message.reply_text("\n".join(q), parse_mode="Markdown")


# ---------- Xodim (ruxsat) boshqaruvi — admin ----------
async def xodimlar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    lst = db.ruxsatlilar()
    adm = {int(a["uid"]) for a in db.adminlar()}
    q = [f"👥 *Xodimlar (ruxsatli)* — {len(lst)} ta\n"]
    for r in lst:
        rol = " 👑" if int(r["uid"]) in adm else ""
        q.append(f"• {r.get('ism') or 'Xodim'}: `{r['uid']}`{rol}")
    q.append("\n_Qo'shish:_ `/xodim_qosh <id> <ism>` · _O'chirish:_ `/ochir <id>`")
    await update.message.reply_text("\n".join(q), parse_mode="Markdown")


async def xodim_qosh_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    args = ctx.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await update.message.reply_text("👤 Qo'shish: `/xodim_qosh 123456789 Ism`", parse_mode="Markdown")
        return
    uid = int(args[0])
    ism = " ".join(args[1:]).strip() or None
    db.ruxsat_qosh(uid, ism)
    await update.message.reply_text(f"✅ Xodim qo'shildi: *{ism or uid}* (`{uid}`)", parse_mode="Markdown")
    try:
        await ctx.bot.send_message(uid, "✅ Sizga ruxsat berildi! /start bosing.")
    except Exception:
        pass


async def ochir_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    args = ctx.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await update.message.reply_text("O'chirish: `/ochir 123456789`", parse_mode="Markdown")
        return
    uid = int(args[0])
    if uid == OWNER_ID:
        await update.message.reply_text("🔒 Egani o'chirib bo'lmaydi.")
        return
    if db.is_admin(uid) and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🔒 Adminni faqat ega o'chira oladi.")
        return
    db.ruxsat_ochir(uid)
    db.admin_ochir(uid)
    await update.message.reply_text(f"✅ O'chirildi: `{uid}`", parse_mode="Markdown")


async def muddat_loop(app):
    """Har kuni: muddati 2 kun (yoki kamroq) qolgan mijozlar haqida ega+adminlarga xabar."""
    import datetime as _dt
    while True:
        try:
            now = db.now_tk()
            kun = now.strftime("%Y-%m-%d")
            if now.hour >= 9 and db.get_sozlama("muddat_oxirgi_kun") != kun:
                db.set_sozlama("muddat_oxirgi_kun", kun)
                lst = [x for x in db.muddat_royxati() if x["kun_qoldi"] <= 2]
                if lst:
                    yaqin = [x for x in lst if x["kun_qoldi"] >= 0]
                    oshgan = [x for x in lst if x["kun_qoldi"] < 0]
                    q = ["🗓 *Ish muddatlari — eslatma*\n"]
                    for x in yaqin:
                        tel = f" · {x['tel']}" if x.get("tel") else ""
                        kq = "bugun tugaydi" if x["kun_qoldi"] == 0 else f"{x['kun_qoldi']} kun qoldi"
                        q.append(f"🟡 *{x['ism']}*{tel} — {kq} ({x['muddat']})")
                    for x in oshgan:
                        tel = f" · {x['tel']}" if x.get("tel") else ""
                        q.append(f"🔴 *{x['ism']}*{tel} — {-x['kun_qoldi']} kun oshib ketdi ({x['muddat']})")
                    matn = "\n".join(q)
                    for uid in _admin_royxati():
                        try:
                            await app.bot.send_message(uid, matn, parse_mode="Markdown")
                        except Exception:
                            pass
        except Exception:
            log.exception("muddat_loop")
        await asyncio.sleep(60)


async def run():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN yo'q — Railway Variables'ga qo'ying.")
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin_qosh", admin_qosh_cmd))
    app.add_handler(CommandHandler("admin_ochir", admin_ochir_cmd))
    app.add_handler(CommandHandler("adminlar", adminlar_cmd))
    app.add_handler(CommandHandler("xodimlar", xodimlar_cmd))
    app.add_handler(CommandHandler("xodim_qosh", xodim_qosh_cmd))
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
    asyncio.create_task(muddat_loop(app))
    log.info("Kovka boti + Mini App ishga tushdi (port %s)", port)
    await asyncio.Event().wait()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
