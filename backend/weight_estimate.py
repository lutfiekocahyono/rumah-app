"""Perkiraan berat (gram) untuk produk yang belum punya berat, dari nama & kategori produk.

Hanya usulan: pemilik melihat pratinjau, bisa mengubah/membuang tiap baris, lalu menyimpan. Produk yang disimpan diberi
tanda weight_estimated=True sampai beratnya diubah manual (editor, edit massal, atau Excel)."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from fastapi import Depends, HTTPException
from pydantic import BaseModel

# (kata kunci di nama, gram kemasan, label) — urutan penting: yang lebih spesifik dulu
NAME_RULES = [
    # small items whose names mention a big appliance ("Rak Kulkas", "Cover TV", "Loyang Microwave")
    (r"\b(cover|sarung|pembersih|aksesoris|tempat tissue|tempat tisu|remote|bracket|breket)\b", 500, "Aksesoris"),
    (r"bantal|guling", 800, "Bantal"),
    (r"\bsapu\b|pel\b|kemoceng", 600, "Sapu/pel"),
    (r"matras yoga|yoga mat", 1500, "Matras yoga"),
    (r"cetakan|loyang", 800, "Cetakan/loyang"),
    (r"panci|wajan|teflon|penggorengan|dandang|kukusan|casserole|dutch oven", 2500, "Panci/wajan"),
    (r"rak\b|rack", 5000, "Rak"),
    (r"speaker.*\b(10|12|15|18)\s*(inch|inci|\")|speaker.*\b(meeting|portable|trolley|aktif|active)\b|meeting speaker", 15000, "Speaker aktif/meeting"),
    (r"dispenser\s*(kulkas|minuman|jus|air minum kaca)|\bjar\b|jug\b", 1500, "Toples/botol"),
    (r"\btissue\b|\btisu\b", 800, "Tisu"),
    (r"kipas.*(industri|plafon|ceiling|gantung)|kipas angin\s*(18|20|24)|industrial fan", 8000, "Kipas angin besar"),
    (r"sofa angin|air lounge|kasur angin|sofa bed angin", 2000, "Sofa/kasur angin"),
    (r"chest freezer|freezer box", 45000, "Chest freezer"),
    (r"\bkulkas\s*(2|dua)\s*pintu|showcase", 60000, "Kulkas 2 pintu / freezer"),
    (r"\bkulkas|refrigerator|lemari es", 35000, "Kulkas"),
    (r"mesin cuci|washing machine", 30000, "Mesin cuci"),
    (r"\bac\b.*(split|pk)|air conditioner|\bac split", 35000, "AC split"),
    (r"air cooler|cooler fan", 9000, "Air cooler"),
    (r"\btv\b.*\b(5[0-9]|6[0-9]|7[0-9])\s*(inch|inci|\")", 20000, "TV 50 inci+"),
    (r"\btv\b.*\b(3[2-9]|4[0-9])\s*(inch|inci|\")", 10000, "TV 32–49 inci"),
    (r"\btv\b|televisi", 6000, "TV kecil"),
    (r"dispenser(?!\s*(sabun|tisu|tissue|odol|pasta))", 8000, "Dispenser"),
    (r"speaker|soundbar|sound bar|salon", 4000, "Speaker"),
    (r"kipas angin.*(berdiri|stand|tornado|dinding|wall)|stand fan|wall fan", 6000, "Kipas angin besar"),
    (r"kipas|fan\b", 3000, "Kipas angin"),
    (r"kompor gas.*(2|dua) tungku|kompor.*tungku", 6000, "Kompor gas"),
    (r"kompor", 3000, "Kompor"),
    (r"oven", 9000, "Oven"),
    (r"microwave", 13000, "Microwave"),
    (r"rice cooker|magic com|penanak nasi", 3500, "Rice cooker"),
    (r"blender|juicer|chopper", 2500, "Blender/juicer"),
    (r"mixer", 3000, "Mixer"),
    (r"setrika", 1500, "Setrika"),
    (r"vacuum|penyedot debu", 4000, "Vacuum cleaner"),
    (r"pompa air|water pump", 8000, "Pompa air"),
    (r"lemari plastik|lemari.*(susun|laci)|rak sepatu|kontainer laci|drawer", 6000, "Lemari/laci plastik"),
    (r"lemari|wardrobe", 25000, "Lemari"),
    (r"kasur|spring ?bed|matras(?! yoga)", 20000, "Kasur"),
    (r"sofa", 30000, "Sofa"),
    (r"meja", 8000, "Meja"),
    (r"kursi|bangku", 4000, "Kursi"),
    (r"galon|ember|baskom|bak\b", 1500, "Ember/galon"),
    (r"piring|mangkok|mangkuk|gelas|cangkir|mug", 700, "Piring/gelas"),
    (r"sendok|garpu|sumpit|spatula|sutil|centong", 300, "Alat makan kecil"),
    (r"toples|lunch box|kotak makan|tempat makan|botol", 600, "Toples/botol"),
    (r"lampu|bohlam", 300, "Lampu"),
    (r"payung", 500, "Payung"),
    (r"kaos|kemeja|celana|baju|jaket|sandal|sepatu", 400, "Pakaian/alas kaki"),
]
CATEGORY_DEFAULT = {  # kalau nama tidak cocok
    "furniture": 8000, "pabrik-lemari-plastik": 6000, "elektronik-rumah-tangga": 4000, "alat-pendingin-ruangan": 8000,
    "audio": 3000, "tv-aksesoris": 1000, "elektronik-lainnya": 1500, "lampu": 300, "peralatan-masak": 2000,
    "peralatan-makan-minum": 700, "peralatan-dapur": 1000, "aksesoris-dapur": 500, "peralatan-baking": 800,
    "penyimpanan-makanan": 700, "tempat-penyimpanan": 1500, "kebutuhan-rumah": 1000, "kebersihan": 1000,
    "perlengkapan-kebersihan": 800, "dekorasi": 800, "kamar-tidur": 3000, "kamar-mandi": 1000, "taman": 1500,
    "hampers-parcel-dan-paket-makanan": 3000, "kemasan-makanan-minuman": 1000, "minuman": 1500, "makanan-jadi": 1000,
    "fashion-pria": 400, "fashion-wanita": 400, "mainan-anak-anak": 800, "alat-tulis": 300, "hiking-camping": 2000,
}
FALLBACK = (1000, "Perkiraan umum")
_RULES = [(re.compile(p, re.I), g, label) for p, g, label in NAME_RULES]
_DUS = re.compile(r"per\s*(dus|karton|lusin|koli)|\(\s*lusin\s*\)", re.I)


# dus/kemasan (P, L, T cm) per jenis — usulan kasar, sama aturan dengan berat
DIMS = {
    "Aksesoris": (20, 15, 5), "Bantal": (45, 35, 15), "Sapu/pel": (120, 10, 10), "Matras yoga": (65, 15, 15),
    "Cetakan/loyang": (30, 25, 8), "Panci/wajan": (35, 35, 20), "Rak": (60, 40, 15), "Speaker aktif/meeting": (50, 45, 75),
    "Kipas angin besar": (70, 25, 70), "Kulkas 2 pintu / freezer": (75, 70, 170), "Chest freezer": (110, 65, 90), "Sofa/kasur angin": (35, 25, 15), "Kulkas": (60, 60, 130), "Mesin cuci": (60, 60, 95),
    "AC split": (95, 35, 40), "Air cooler": (40, 35, 80), "TV 50 inci+": (130, 15, 80), "TV 32–49 inci": (100, 13, 62), "TV kecil": (60, 12, 40),
    "Dispenser": (35, 35, 100), "Speaker": (35, 30, 45), "Kipas angin": (40, 15, 40), "Kompor gas": (75, 45, 15), "Kompor": (45, 40, 15),
    "Oven": (55, 40, 40), "Microwave": (55, 45, 35), "Rice cooker": (35, 35, 30), "Blender/juicer": (25, 25, 40), "Mixer": (30, 20, 25),
    "Setrika": (30, 15, 15), "Vacuum cleaner": (45, 30, 35), "Pompa air": (40, 30, 30), "Lemari/laci plastik": (55, 45, 30),
    "Lemari": (100, 55, 30), "Kasur": (120, 40, 40), "Sofa": (180, 85, 70), "Meja": (100, 60, 12), "Kursi": (50, 50, 60),
    "Ember/galon": (35, 35, 35), "Piring/gelas": (25, 25, 12), "Alat makan kecil": (25, 10, 5), "Toples/botol": (20, 20, 25),
    "Lampu": (12, 12, 15), "Payung": (35, 10, 10), "Pakaian/alas kaki": (30, 25, 8), "Tisu": (25, 15, 12),
}
DIMS_FALLBACK = (25, 20, 15)
_SOFT = re.compile(r"kelambu|sprei|seprai|bendera|karpet|tikar|gorden|gordyn|taplak|selimut|handuk|terpal|banner|kain|plastik sampah|kantong", re.I)
# ukuran tertulis di nama, mis. "(185x120x50Cm)" atau "Uk. 23X24X30" — dus dibuat sedikit lebih besar
_SIZE = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s*[x×]\s*(\d{1,3}(?:[.,]\d)?)\s*[x×]\s*(\d{1,3}(?:[.,]\d)?)(?!\s*(mm|m\b|meter|inch|\"|ml))", re.I)


def _match(p: dict, parent_of: Dict[str, str]) -> tuple[int, str, str, int]:
    """(gram, label, jenis, jumlah isi) — dipakai berat & ukuran dus."""
    name = p.get("name") or ""
    grams, label = next(((g, lab) for rx, g, lab in _RULES if rx.search(name)), (None, ""))
    if grams is None:
        cat = p.get("category") or ""
        for c in (cat, parent_of.get(cat, "")):
            if c in CATEGORY_DEFAULT:
                grams, label = CATEGORY_DEFAULT[c], f"Kategori {c.replace('-', ' ')}"
                break
    if grams is None:
        grams, label = FALLBACK
    m, n = _DUS.search(name), 1  # sold per carton / dozen: bigger parcel ("Isi 40 Pcs" = one pack, not 40 parcels)
    if m:
        n = 12 if "lusin" in m.group(0).lower() else 6
    return grams, label, label, n


def estimate(p: dict, parent_of: Dict[str, str]) -> tuple[int, str]:
    grams, label, _, n = _match(p, parent_of)
    if n > 1:
        grams, label = min(grams * n, max(grams, 30000)), f"{label} × {n} (per dus)"  # a carton of small items stays ≤ 30 kg
    return min(grams, 500000), label


def estimate_dims(p: dict, parent_of: Dict[str, str]) -> tuple[list, str]:
    _, label, kind, n = _match(p, parent_of)
    m = _SIZE.search(p.get("name") or "")
    if m and n == 1 and not _SOFT.search(p.get("name") or ""):  # folded goods ship much smaller than their size
        dims = [min(500, max(1, round(float(x.replace(",", "."))) + 2)) for x in m.groups()[:3]]
        if max(dims) <= 300:
            return dims, "Ukuran dari nama produk"
    base = DIMS.get(kind, DIMS_FALLBACK)
    f = n ** (1 / 3)  # n items in one carton: grow each side
    dims = [min(max(x, 120), max(1, round(x * f))) for x in base]  # cartons of small items stay ≤ 120 cm a side
    return dims, (f"{label} × {n} (per dus)" if n > 1 else label) + ("" if kind in DIMS else " · ukuran umum")


MISSING = {"$or": [{"weight_grams": {"$exists": False}}, {"weight_grams": None}, {"weight_grams": {"$lte": 0}}]}
MISSING_DIMS = {"$or": [{f: {"$in": [None, 0]}} for f in ("length_cm", "width_cm", "height_cm")] + [{"length_cm": {"$exists": False}}]}


class ApplyIn(BaseModel):
    skip: List[str] = []
    overrides: Dict[str, Union[int, List[int]]] = {}


def register(api, db, *, actor, target_store, log_activity):
    KINDS = {"weight": (MISSING, "weight_estimated"), "dims": (MISSING_DIMS, "dims_estimated")}

    def kind_of(kind: str):
        if kind not in KINDS:
            raise HTTPException(status_code=404, detail="Jenis perkiraan tidak dikenal")
        return KINDS[kind]

    @api.get("/product-editor/{kind}/summary")
    async def estimate_summary(kind: str, store_id: Optional[str] = None, ctx=Depends(actor)):
        missing, flag = kind_of(kind)
        store = await target_store(ctx, store_id)
        q = {"store_id": store["store_id"]}
        return {"store_id": store["store_id"], "missing": await db.products.count_documents({**q, **missing}),
                "estimated": await db.products.count_documents({**q, flag: True})}

    @api.post("/product-editor/{kind}/preview")
    async def estimate_preview(kind: str, store_id: Optional[str] = None, ctx=Depends(actor)):
        missing, _ = kind_of(kind)
        store = await target_store(ctx, store_id)
        parent_of = {c["category_id"]: c.get("parent") or "" for c in await db.categories.find({}, {"category_id": 1, "parent": 1}).to_list(5000)}
        items = []
        async for p in db.products.find({"store_id": store["store_id"], **missing}, {"_id": 0, "product_id": 1, "name": 1, "category": 1, "image": 1}):
            row = {"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", "")}
            if kind == "weight":
                row["grams"], row["rule"] = estimate(p, parent_of)
            else:
                row["dims"], row["rule"] = estimate_dims(p, parent_of)
            items.append(row)
        groups: dict = {}
        for i in items:
            key = i["rule"].split(" × ")[0].split(" · ")[0]
            groups[key] = groups.get(key, 0) + 1
        doc = {"preview_id": f"wp_{uuid.uuid4().hex[:10]}", "kind": kind, "store_id": store["store_id"], "items": items, "by": ctx["user"]["user_id"],
               "created_at": datetime.now(timezone.utc), "status": "preview"}
        await db.weight_previews.insert_one({**doc})
        return {"preview_id": doc["preview_id"], "total": len(items), "items": items,
                "groups": sorted([{"rule": k, "count": n} for k, n in groups.items()], key=lambda x: -x["count"])}

    @api.post("/product-editor/{kind}/{preview_id}/apply")
    async def estimate_apply(kind: str, preview_id: str, body: ApplyIn, ctx=Depends(actor)):
        missing, flag = kind_of(kind)
        pre = await db.weight_previews.find_one({"preview_id": preview_id, "kind": {"$in": [kind, None] if kind == "weight" else [kind]}}, {"store_id": 1})
        if not pre:
            raise HTTPException(status_code=400, detail="Pratinjau tidak ditemukan. Buat pratinjau baru")
        await target_store(ctx, pre["store_id"])  # permission first, so a refused user can't use up the preview
        d = await db.weight_previews.find_one_and_update(
            {"preview_id": preview_id, "status": "preview", "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=2)}},
            {"$set": {"status": "applied"}}, projection={"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Pratinjau sudah dipakai atau kedaluwarsa. Buat pratinjau baru")
        skip, saved = set(body.skip), 0
        for i in d["items"]:
            if i["product_id"] in skip:
                continue
            o = body.overrides.get(i["product_id"])
            if kind == "weight":
                g = int(o if isinstance(o, int) else i["grams"])
                if not 1 <= g <= 500000:
                    continue
                upd = {"weight_grams": g}
            else:
                dims = o if isinstance(o, list) and len(o) == 3 else i["dims"]
                if not all(isinstance(x, int) and 1 <= x <= 500 for x in dims):
                    continue
                upd = dict(zip(("length_cm", "width_cm", "height_cm"), dims))
            res = await db.products.update_one({"product_id": i["product_id"], "store_id": d["store_id"], **missing},
                                               {"$set": {**upd, flag: True}})  # no buyer notification: shipping data only
            saved += res.modified_count
        what = "berat" if kind == "weight" else "ukuran dus"
        await log_activity(ctx["user"]["user_id"], "store", f"Mengisi {what} perkiraan {saved} produk")
        return {"saved": saved}
