"""
KOVKA boti — sotuv/qarz bazasi (ijaradan farqli: kunlik hisob, ombor, qaytarish YO'Q).

Model:
  mijozlar    : id, ism, tel, izoh
  mahsulotlar : id, mijoz_id, nom, narx, dona, sana   (satr = narx * dona)
  tolovlar    : id, mijoz_id, summa, sana, izoh
Qarz = SUM(narx*dona) - SUM(tolovlar.summa).
"""
import os
import sqlite3
from datetime import datetime, date

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))
except Exception:
    _TZ = None

DATA_DIR = os.getenv("DATA_DIR", "/data")
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
except Exception:
    OWNER_ID = 0
DB_PATH = os.path.join(DATA_DIR, "kovka.db")


def now_tk():
    return datetime.now(_TZ).replace(tzinfo=None) if _TZ else datetime.now()


def today_tk():
    return now_tk().date()


def clean_phone(t):
    if not t:
        return None
    d = "".join(c for c in str(t) if c.isdigit())
    return d or None


def _con():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = _con()
    con.execute("""CREATE TABLE IF NOT EXISTS mijozlar(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ism TEXT, tel TEXT, izoh TEXT, created TEXT)""")
    try:
        con.execute("ALTER TABLE mijozlar ADD COLUMN muddat TEXT")
    except Exception:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS mahsulotlar(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mijoz_id INTEGER, nom TEXT, narx REAL, dona REAL DEFAULT 1,
        sana TEXT, created TEXT)""")
    for col in ("eni REAL", "boyi REAL", "valyuta TEXT DEFAULT 'usd'"):
        try:
            con.execute(f"ALTER TABLE mahsulotlar ADD COLUMN {col}")
        except Exception:
            pass
    con.execute("""CREATE TABLE IF NOT EXISTS tolovlar(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mijoz_id INTEGER, summa REAL, sana TEXT, izoh TEXT, created TEXT)""")
    try:
        con.execute("ALTER TABLE tolovlar ADD COLUMN valyuta TEXT DEFAULT 'usd'")
    except Exception:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS ruxsat(
        uid INTEGER PRIMARY KEY, ism TEXT, qoshildi TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS ruxsat_sorov(
        uid INTEGER PRIMARY KEY, ism TEXT, sana TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS adminlar(
        uid INTEGER PRIMARY KEY, ism TEXT, qoshildi TEXT)""")
    con.commit()
    con.close()


# ---------------- Mijoz ----------------
def mijoz_qosh(ism, tel=None, izoh=None):
    con = _con()
    cur = con.execute("INSERT INTO mijozlar(ism,tel,izoh,created) VALUES(?,?,?,?)",
                      (ism, clean_phone(tel), izoh, now_tk().isoformat()))
    con.commit()
    mid = cur.lastrowid
    con.close()
    return mid


def mijoz_get(mid):
    con = _con()
    r = con.execute("SELECT * FROM mijozlar WHERE id=?", (mid,)).fetchone()
    con.close()
    return dict(r) if r else None


def mijoz_tahrir(mid, ism=None, tel=None, izoh=None):
    con = _con()
    con.execute("UPDATE mijozlar SET ism=COALESCE(?,ism), tel=COALESCE(?,tel), izoh=COALESCE(?,izoh) WHERE id=?",
                (ism, clean_phone(tel), izoh, mid))
    con.commit()
    con.close()


def mijoz_ochir(mid):
    con = _con()
    con.execute("DELETE FROM mahsulotlar WHERE mijoz_id=?", (mid,))
    con.execute("DELETE FROM tolovlar WHERE mijoz_id=?", (mid,))
    con.execute("DELETE FROM mijozlar WHERE id=?", (mid,))
    con.commit()
    con.close()


def mijoz_qidir(nom):
    con = _con()
    rows = con.execute("SELECT * FROM mijozlar WHERE lower(ism) LIKE ? OR tel LIKE ? ORDER BY id DESC",
                       (f"%{(nom or '').lower()}%", f"%{clean_phone(nom) or ''}%")).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---------------- Mahsulot / To'lov ----------------
def mahsulot_qosh(mijoz_id, nom, narx, dona=1, sana=None, eni=None, boyi=None, valyuta="usd"):
    con = _con()
    try:
        eni = float(eni) if eni not in (None, "") else None
        boyi = float(boyi) if boyi not in (None, "") else None
    except Exception:
        eni = boyi = None
    if eni and boyi:
        dona = round(eni * boyi, 3)   # kvadrat = eni * bo'yi; narx = 1 m^2 narxi
    val = "som" if str(valyuta).lower() in ("som", "so'm", "uzs") else "usd"
    cur = con.execute(
        "INSERT INTO mahsulotlar(mijoz_id,nom,narx,dona,eni,boyi,valyuta,sana,created) VALUES(?,?,?,?,?,?,?,?,?)",
        (mijoz_id, nom, float(narx or 0), float(dona or 1), eni, boyi, val,
         str(sana or today_tk())[:10], now_tk().isoformat()))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def mahsulot_tahrir(rid, nom=None, narx=None, eni=None, boyi=None, valyuta=None):
    """Mahsulot nom/narx/o'lchov/valyutasini tahrirlaydi (bo'sh maydonlar o'zgarmaydi)."""
    con = _con()
    r = con.execute("SELECT * FROM mahsulotlar WHERE id=?", (rid,)).fetchone()
    if not r:
        con.close()
        return {"ok": False}
    r = dict(r)
    if nom not in (None, ""):
        r["nom"] = nom
    if valyuta:
        r["valyuta"] = "som" if str(valyuta).lower() in ("som", "so'm", "uzs") else "usd"
    try:
        eni = float(eni) if eni not in (None, "") else r.get("eni")
    except Exception:
        eni = r.get("eni")
    try:
        boyi = float(boyi) if boyi not in (None, "") else r.get("boyi")
    except Exception:
        boyi = r.get("boyi")
    try:
        if narx not in (None, ""):
            r["narx"] = float(narx)
    except Exception:
        pass
    dona = round(eni * boyi, 3) if (eni and boyi) else (r.get("dona") or 1)
    con.execute("UPDATE mahsulotlar SET nom=?, narx=?, dona=?, eni=?, boyi=?, valyuta=? WHERE id=?",
                (r["nom"], r["narx"], dona, eni, boyi, r.get("valyuta") or "usd", rid))
    con.commit()
    con.close()
    return {"ok": True}


def mahsulot_ochir(rid):
    con = _con()
    con.execute("DELETE FROM mahsulotlar WHERE id=?", (rid,))
    con.commit()
    con.close()


def tolov_qosh(mijoz_id, summa, sana=None, izoh=None, valyuta="usd"):
    con = _con()
    val = "som" if str(valyuta).lower() in ("som", "so'm", "uzs") else "usd"
    cur = con.execute("INSERT INTO tolovlar(mijoz_id,summa,sana,izoh,valyuta,created) VALUES(?,?,?,?,?,?)",
                      (mijoz_id, float(summa or 0), str(sana or today_tk())[:10], izoh, val, now_tk().isoformat()))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def tolov_ochir(rid):
    con = _con()
    con.execute("DELETE FROM tolovlar WHERE id=?", (rid,))
    con.commit()
    con.close()


# ---------------- Hisob ----------------
def mahsulotlar_of(mid):
    con = _con()
    rows = con.execute("SELECT * FROM mahsulotlar WHERE mijoz_id=? ORDER BY id DESC", (mid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def tolovlar_of(mid):
    con = _con()
    rows = con.execute("SELECT * FROM tolovlar WHERE mijoz_id=? ORDER BY id DESC", (mid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def mijoz_hisob(mid):
    """Bitta mijozning holati — valyuta bo'yicha ($ va so'm alohida)."""
    m = mijoz_get(mid)
    if not m:
        return None
    mahs = mahsulotlar_of(mid)
    tolovlar = tolovlar_of(mid)
    for r in mahs:
        r["jami"] = round((r.get("narx") or 0) * (r.get("dona") or 1))
        r["valyuta"] = r.get("valyuta") or "usd"
    for t in tolovlar:
        t["valyuta"] = t.get("valyuta") or "usd"
    val = {"usd": {"jami": 0, "tolangan": 0, "qarz": 0},
           "som": {"jami": 0, "tolangan": 0, "qarz": 0}}
    for r in mahs:
        val[r["valyuta"]]["jami"] += r["jami"]
    for t in tolovlar:
        val[t["valyuta"]]["tolangan"] += round(t.get("summa") or 0)
    for v in val.values():
        v["qarz"] = round(v["jami"] - v["tolangan"])
    return {
        "id": m["id"], "ism": m["ism"], "tel": m.get("tel"), "izoh": m.get("izoh"),
        "muddat": m.get("muddat"), "kun_qoldi": _kun_qoldi(m.get("muddat")),
        "mahsulotlar": mahs, "tolovlar": tolovlar,
        "usd": val["usd"], "som": val["som"],
        # eski moslik (asosan usd):
        "jami": val["usd"]["jami"], "tolangan": val["usd"]["tolangan"], "qarz": val["usd"]["qarz"],
    }


def mijozlar():
    """Barcha mijozlar — qarzi bilan (valyuta bo'yicha $ va so'm)."""
    con = _con()
    rows = con.execute("""
        SELECT m.id, m.ism, m.tel, m.muddat,
          COALESCE((SELECT SUM(narx*dona) FROM mahsulotlar WHERE mijoz_id=m.id AND COALESCE(valyuta,'usd')='usd'),0) AS jami_usd,
          COALESCE((SELECT SUM(summa)     FROM tolovlar    WHERE mijoz_id=m.id AND COALESCE(valyuta,'usd')='usd'),0) AS tol_usd,
          COALESCE((SELECT SUM(narx*dona) FROM mahsulotlar WHERE mijoz_id=m.id AND valyuta='som'),0) AS jami_som,
          COALESCE((SELECT SUM(summa)     FROM tolovlar    WHERE mijoz_id=m.id AND valyuta='som'),0) AS tol_som
        FROM mijozlar m ORDER BY m.id DESC""").fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        qu = round((d["jami_usd"] or 0) - (d["tol_usd"] or 0))
        qs = round((d["jami_som"] or 0) - (d["tol_som"] or 0))
        out.append({"id": d["id"], "ism": d["ism"], "tel": d["tel"],
                    "qarz_usd": qu, "qarz_som": qs,
                    "muddat": d.get("muddat"), "kun_qoldi": _kun_qoldi(d.get("muddat")),
                    "qarz": qu, "jami": round(d["jami_usd"] or 0), "tolangan": round(d["tol_usd"] or 0)})
    return out


def qarzdorlar():
    """Qarzi bor mijozlar ($ yoki so'm bo'yicha)."""
    return [m for m in mijozlar() if (m.get("qarz_usd") or 0) > 0 or (m.get("qarz_som") or 0) > 0]


# ---------------- Ruxsat (kirish nazorati) ----------------
def ruxsat_bormi(uid):
    try:
        uid = int(uid)
    except Exception:
        return False
    if OWNER_ID and uid == OWNER_ID:
        return True
    con = _con()
    r = con.execute("SELECT 1 FROM ruxsat WHERE uid=?", (uid,)).fetchone()
    con.close()
    return bool(r)


def ruxsat_qosh(uid, ism=None):
    con = _con()
    con.execute("INSERT OR REPLACE INTO ruxsat(uid,ism,qoshildi) VALUES(?,?,?)",
                (int(uid), ism, now_tk().isoformat()))
    con.execute("DELETE FROM ruxsat_sorov WHERE uid=?", (int(uid),))
    con.commit()
    con.close()


def ruxsat_ochir(uid):
    con = _con()
    con.execute("DELETE FROM ruxsat WHERE uid=?", (int(uid),))
    con.commit()
    con.close()


def sorov_qosh(uid, ism=None):
    """So'rov qo'shadi. Yangi bo'lsa True (takror bo'lsa False)."""
    con = _con()
    ex = con.execute("SELECT 1 FROM ruxsat_sorov WHERE uid=?", (int(uid),)).fetchone()
    con.execute("INSERT OR REPLACE INTO ruxsat_sorov(uid,ism,sana) VALUES(?,?,?)",
                (int(uid), ism, now_tk().isoformat()))
    con.commit()
    con.close()
    return not ex


def sorov_ochir(uid):
    con = _con()
    con.execute("DELETE FROM ruxsat_sorov WHERE uid=?", (int(uid),))
    con.commit()
    con.close()


def ruxsatlilar():
    con = _con()
    rows = con.execute("SELECT * FROM ruxsat ORDER BY qoshildi").fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---------------- Admin (odam qo'sha oladiganlar) ----------------
def is_admin(uid):
    try:
        uid = int(uid)
    except Exception:
        return False
    if OWNER_ID and uid == OWNER_ID:
        return True
    con = _con()
    try:
        r = con.execute("SELECT 1 FROM adminlar WHERE uid=?", (uid,)).fetchone()
    except Exception:
        r = None
    con.close()
    return bool(r)


def admin_qosh(uid, ism=None):
    con = _con()
    con.execute("INSERT OR REPLACE INTO adminlar(uid,ism,qoshildi) VALUES(?,?,?)",
                (int(uid), ism, now_tk().isoformat()))
    # admin ham ruxsatli bo'lsin (ilovaga kira olsin)
    con.execute("INSERT OR REPLACE INTO ruxsat(uid,ism,qoshildi) VALUES(?,?,?)",
                (int(uid), ism, now_tk().isoformat()))
    con.execute("DELETE FROM ruxsat_sorov WHERE uid=?", (int(uid),))
    con.commit()
    con.close()


def admin_ochir(uid):
    con = _con()
    cur = con.execute("DELETE FROM adminlar WHERE uid=?", (int(uid),))
    con.commit()
    n = cur.rowcount
    con.close()
    return n


def adminlar():
    con = _con()
    try:
        rows = con.execute("SELECT * FROM adminlar ORDER BY qoshildi").fetchall()
    except Exception:
        rows = []
    con.close()
    return [dict(r) for r in rows]


# ---------------- Muddat (ish bitirilishi kerak bo'lgan sana) ----------------
def _kun_qoldi(muddat):
    if not muddat:
        return None
    try:
        d = date.fromisoformat(str(muddat)[:10])
    except Exception:
        return None
    return (d - today_tk()).days


def set_muddat(mid, sana):
    """Mijozga ish bitirilish sanasini qo'yish/o'chirish (sana=None -> o'chirish)."""
    con = _con()
    con.execute("UPDATE mijozlar SET muddat=? WHERE id=?",
                ((str(sana)[:10] if sana else None), int(mid)))
    con.commit()
    con.close()
    return {"ok": True}


def muddat_royxati():
    """Muddati bor mijozlar — kun_qoldi bilan (kam qolgan birinchi)."""
    con = _con()
    rows = con.execute("SELECT id, ism, tel, muddat FROM mijozlar WHERE muddat IS NOT NULL AND muddat<>''").fetchall()
    con.close()
    res = []
    for r in rows:
        kq = _kun_qoldi(r["muddat"])
        if kq is None:
            continue
        res.append({"id": r["id"], "ism": r["ism"], "tel": r["tel"],
                    "muddat": r["muddat"], "kun_qoldi": kq})
    res.sort(key=lambda x: x["kun_qoldi"])
    return res


# ---------------- Sozlama (kalit-qiymat) ----------------
def _sozlama_jadval(con):
    con.execute("CREATE TABLE IF NOT EXISTS sozlama(kalit TEXT PRIMARY KEY, qiymat TEXT)")


def get_sozlama(kalit, default=None):
    con = _con()
    _sozlama_jadval(con)
    r = con.execute("SELECT qiymat FROM sozlama WHERE kalit=?", (kalit,)).fetchone()
    con.close()
    return r["qiymat"] if r else default


def set_sozlama(kalit, qiymat):
    con = _con()
    _sozlama_jadval(con)
    con.execute("INSERT OR REPLACE INTO sozlama(kalit,qiymat) VALUES(?,?)", (kalit, str(qiymat)))
    con.commit()
    con.close()
