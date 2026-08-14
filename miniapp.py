"""KOVKA Mini App — aiohttp API (sotuv/qarz)."""
import os
import json
import time
import hmac
import hashlib
from urllib.parse import parse_qsl

from aiohttp import web

import db

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")

_admins = [x.strip() for x in (os.getenv("KOVKA_ADMINS", "") or "").split(",") if x.strip()]
ADMINS = set(int(x) for x in _admins if x.lstrip("-").isdigit())


def make_token(uid, bot_token, kun=30):
    exp = int(time.time()) + kun * 24 * 3600
    xom = f"{uid}.{exp}"
    imzo = hmac.new(bot_token.encode(), xom.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{xom}.{imzo}"


def read_token(token, bot_token):
    try:
        uid_s, exp_s, imzo = (token or "").split(".")
        xom = f"{uid_s}.{exp_s}"
        kutilgan = hmac.new(bot_token.encode(), xom.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(kutilgan, imzo):
            return None
        if int(exp_s) < time.time():
            return None
        return int(uid_s)
    except Exception:
        return None


def validate_init_data(init_data, bot_token):
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None
    got = pairs.pop("hash", None)
    if not got:
        return None
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        return None
    try:
        return int(json.loads(pairs.get("user", "{}"))["id"])
    except Exception:
        return None


def _allowed(uid):
    if uid in ADMINS:
        return True
    if db.OWNER_ID:            # ega belgilangan — faqat ruxsat berilganlar
        return db.ruxsat_bormi(uid)
    return not ADMINS         # ega yo'q va admin yo'q — ochiq (eski holat)


def make_web_app(bot_token):

    def check(request):
        uid = validate_init_data(request.headers.get("X-Init-Data", ""), bot_token)
        if uid is None:
            uid = read_token(request.headers.get("X-Token", ""), bot_token)
        if uid is None:
            dbg = os.getenv("DEBUG_USER_ID")
            uid = int(dbg) if dbg else None
        if uid is None:
            return None, web.json_response({"xato": "Telegram ichida oching"}, status=401)
        if not _allowed(uid):
            return None, web.json_response({"xato": "Ruxsat yo'q"}, status=403)
        return uid, None

    async def index(request):
        return web.FileResponse(INDEX, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate"})

    # -------- Mijozlar --------
    async def api_mijozlar(request):
        uid, err = check(request)
        if err:
            return err
        return web.json_response({"mijozlar": db.mijozlar()})

    async def api_qarzdorlar(request):
        uid, err = check(request)
        if err:
            return err
        return web.json_response({"mijozlar": db.qarzdorlar()})

    async def api_mijoz(request):
        uid, err = check(request)
        if err:
            return err
        try:
            mid = int(request.query.get("id", ""))
        except Exception:
            return web.json_response({"xato": "id kerak"}, status=400)
        d = db.mijoz_hisob(mid)
        if not d:
            return web.json_response({"xato": "topilmadi"}, status=404)
        return web.json_response(d)

    async def api_mijoz_qosh(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        ism = (b.get("ism") or "").strip()
        if not ism:
            return web.json_response({"xato": "Ism kerak"}, status=400)
        mid = db.mijoz_qosh(ism, b.get("tel"), b.get("izoh"))
        return web.json_response({"ok": True, "id": mid})

    async def api_mijoz_tahrir(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        db.mijoz_tahrir(int(b.get("id")), b.get("ism"), b.get("tel"), b.get("izoh"))
        return web.json_response({"ok": True})

    async def api_mijoz_ochir(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        db.mijoz_ochir(int(b.get("id")))
        return web.json_response({"ok": True})

    # -------- Mahsulot / To'lov --------
    async def api_mahsulot_qosh(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        try:
            mid = int(b.get("mijoz_id"))
        except Exception:
            return web.json_response({"xato": "mijoz_id kerak"}, status=400)
        nom = (b.get("nom") or "").strip()
        if not nom:
            return web.json_response({"xato": "Nom kerak"}, status=400)
        try:
            narx = float(str(b.get("narx") or 0).replace(" ", ""))
        except Exception:
            narx = 0
        try:
            dona = float(str(b.get("dona") or 1).replace(" ", "")) or 1
        except Exception:
            dona = 1
        db.mahsulot_qosh(mid, nom, narx, dona, b.get("sana"),
                         eni=b.get("eni"), boyi=b.get("boyi"), valyuta=b.get("valyuta"))
        d = db.mijoz_hisob(mid)
        return web.json_response({"ok": True, "qarz": d["qarz"] if d else 0})

    async def api_mahsulot_ochir(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        db.mahsulot_ochir(int(b.get("id")))
        return web.json_response({"ok": True})

    async def api_tolov_qosh(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        try:
            mid = int(b.get("mijoz_id"))
            summa = float(str(b.get("summa") or 0).replace(" ", ""))
        except Exception:
            return web.json_response({"xato": "summa kerak"}, status=400)
        if summa == 0:
            return web.json_response({"xato": "Summa 0 bo'lmasin"}, status=400)
        tur = "skidka" if str(b.get("tur") or "tolov").lower() == "skidka" else "tolov"
        db.tolov_qosh(mid, summa, b.get("sana"), b.get("izoh"),
                      valyuta=b.get("valyuta"), tur=tur)
        d = db.mijoz_hisob(mid)
        return web.json_response({"ok": True, "qarz": d["qarz"] if d else 0})

    async def api_muddat(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        try:
            mid = int(b.get("id"))
        except Exception:
            return web.json_response({"xato": "id kerak"}, status=400)
        db.mijoz_muddat(mid, b.get("muddat"))
        return web.json_response({"ok": True})

    async def api_tolov_ochir(request):
        uid, err = check(request)
        if err:
            return err
        b = await request.json()
        db.tolov_ochir(int(b.get("id")))
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/api/mijozlar", api_mijozlar)
    app.router.add_get("/api/qarzdorlar", api_qarzdorlar)
    app.router.add_get("/api/mijoz", api_mijoz)
    app.router.add_post("/api/mijoz_qosh", api_mijoz_qosh)
    app.router.add_post("/api/mijoz_tahrir", api_mijoz_tahrir)
    app.router.add_post("/api/mijoz_ochir", api_mijoz_ochir)
    app.router.add_post("/api/mahsulot_qosh", api_mahsulot_qosh)
    app.router.add_post("/api/mahsulot_ochir", api_mahsulot_ochir)
    app.router.add_post("/api/tolov_qosh", api_tolov_qosh)
    app.router.add_post("/api/tolov_ochir", api_tolov_ochir)
    app.router.add_post("/api/muddat", api_muddat)
    return app
