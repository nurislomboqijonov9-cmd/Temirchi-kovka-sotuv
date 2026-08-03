"""KOVKA boti — Mini App ishga tushiruvchi (sotuv/qarz)."""
import os
import asyncio
import logging

from aiohttp import web as aioweb
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import db
from miniapp import make_web_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kovka")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def webapp_url():
    base = os.getenv("WEBAPP_URL") or ""
    if not base:
        dom = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        base = f"https://{dom}" if dom else ""
    return base.split("?")[0].rstrip("/") if base else ""


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = webapp_url()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🔨 Ilovani ochish", web_app=WebAppInfo(url=url))]]) if url else None
    await update.message.reply_text(
        "🔨 *KOVKA — sotuv hisobi*\n\n"
        "Mijozlar, mahsulotlar (darvoza, eshik, reshotka…), narx, to'lov va qarz.\n"
        "Ilovani oching:",
        parse_mode="Markdown", reply_markup=kb)


async def run():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN yo'q — Railway Variables'ga qo'ying.")
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

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
