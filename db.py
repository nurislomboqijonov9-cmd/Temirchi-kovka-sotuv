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
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))
except Exception:
    _TZ = None

DATA_DIR = os.getenv("DATA_DIR", "/data")
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
    con.execute("""CREATE TABLE IF NOT EXISTS mahsulotlar(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mijoz_id INTEGER, nom TEXT, narx REAL, dona REAL DEFAULT 1,
        sana TEXT, created TEXT)""")
    for col in ("eni REAL", "boyi REAL"):
        try:
            con.execute(f"ALTER TABLE mahsulotlar ADD COLUMN {col}")
        except Exception:
            pass
    con.execute("""CREATE TABLE IF NOT EXISTS tolovlar(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mijoz_id INTEGER, summa REAL, sana TEXT, izoh TEXT, created TEXT)""")
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
def mahsulot_qosh(mijoz_id, nom, narx, dona=1, sana=None, eni=None, boyi=None):
    con = _con()
    try:
        eni = float(eni) if eni not in (None, "") else None
        boyi = float(boyi) if boyi not in (None, "") else None
    except Exception:
        eni = boyi = None
    if eni and boyi:
        dona = round(eni * boyi, 3)   # kvadrat = eni * bo'yi; narx = 1 m^2 narxi
    cur = con.execute(
        "INSERT INTO mahsulotlar(mijoz_id,nom,narx,dona,eni,boyi,sana,created) VALUES(?,?,?,?,?,?,?,?)",
        (mijoz_id, nom, float(narx or 0), float(dona or 1), eni, boyi,
         str(sana or today_tk())[:10], now_tk().isoformat()))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def mahsulot_ochir(rid):
    con = _con()
    con.execute("DELETE FROM mahsulotlar WHERE id=?", (rid,))
    con.commit()
    con.close()


def tolov_qosh(mijoz_id, summa, sana=None, izoh=None):
    con = _con()
    cur = con.execute("INSERT INTO tolovlar(mijoz_id,summa,sana,izoh,created) VALUES(?,?,?,?,?)",
                      (mijoz_id, float(summa or 0), str(sana or today_tk())[:10], izoh, now_tk().isoformat()))
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
    """Bitta mijozning to'liq holati: mahsulotlar, to'lovlar, jami, to'langan, qarz."""
    m = mijoz_get(mid)
    if not m:
        return None
    mahs = mahsulotlar_of(mid)
    tolovlar = tolovlar_of(mid)
    for r in mahs:
        r["jami"] = round((r.get("narx") or 0) * (r.get("dona") or 1))
    jami = sum(r["jami"] for r in mahs)
    tolangan = sum(t.get("summa") or 0 for t in tolovlar)
    return {
        "id": m["id"], "ism": m["ism"], "tel": m.get("tel"), "izoh": m.get("izoh"),
        "mahsulotlar": mahs, "tolovlar": tolovlar,
        "jami": round(jami), "tolangan": round(tolangan), "qarz": round(jami - tolangan),
    }


def mijozlar():
    """Barcha mijozlar — qarzi bilan (ro'yxat uchun)."""
    con = _con()
    rows = con.execute("""
        SELECT m.id, m.ism, m.tel,
          COALESCE((SELECT SUM(narx*dona) FROM mahsulotlar WHERE mijoz_id=m.id),0) AS jami,
          COALESCE((SELECT SUM(summa) FROM tolovlar WHERE mijoz_id=m.id),0) AS tolangan
        FROM mijozlar m ORDER BY m.id DESC""").fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["qarz"] = round((d["jami"] or 0) - (d["tolangan"] or 0))
        d["jami"] = round(d["jami"] or 0)
        d["tolangan"] = round(d["tolangan"] or 0)
        out.append(d)
    return out


def qarzdorlar():
    """Qarzi bor mijozlar (ko'pdan kamga)."""
    return [m for m in mijozlar() if m["qarz"] > 0]
