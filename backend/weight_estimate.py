"""Perkiraan berat (gram) untuk produk yang belum punya berat, dari nama & kategori produk.

Hanya usulan: pemilik melihat pratinjau, bisa mengubah/membuang tiap baris, lalu menyimpan. Produk yang disimpan diberi
tanda weight_estimated=True sampai beratnya diubah manual (editor, edit massal, atau Excel)."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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
    (r"speaker.*\b(10|12|15|18)\s*(inch|inci|\")|speaker\s*(meeting|portable|trolley|aktif|active)|meeting speaker", 15000, "Speaker aktif/meeting"),
    (r"kipas.*(industri|plafon|ceiling|gantung)|kipas angin\s*(18|20|24)|industrial fan", 8000, "Kipas angin besar"),
    (r"\bkulkas\s*(2|dua)\s*pintu|showcase|chest freezer|freezer box", 60000, "Kulkas 2 pintu / freezer"),
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
_DUS = re.compile(r"per\s*(dus|karton|lusin|pack|koli)|isi\s*(\d+)\s*(lusin)?", re.I)


def estimate(p: dict, parent_of: Dict[str, str]) -> tuple[int, str]:
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
    m = _DUS.search(name)  # sold per carton / dozen: heavier parcel
    if m:
        n = int(m.group(2)) * (12 if m.group(3) else 1) if m.group(2) else (12 if "lusin" in m.group(0).lower() else 6)
        grams, label = grams * max(2, min(n, 48)), f"{label} × {max(2, min(n, 48))} (per dus/isi)"
    return min(grams, 500000), label


MISSING = {"$or": [{"weight_grams": {"$exists": False}}, {"weight_grams": None}, {"weight_grams": {"$lte": 0}}]}


class ApplyIn(BaseModel):
    skip: List[str] = []
    overrides: Dict[str, int] = {}


def register(api, db, *, actor, target_store, log_activity):

    @api.get("/product-editor/weight/summary")
    async def weight_summary(store_id: Optional[str] = None, ctx=Depends(actor)):
        store = await target_store(ctx, store_id)
        q = {"store_id": store["store_id"]}
        return {"store_id": store["store_id"], "missing": await db.products.count_documents({**q, **MISSING}),
                "estimated": await db.products.count_documents({**q, "weight_estimated": True})}

    @api.post("/product-editor/weight/preview")
    async def weight_preview(store_id: Optional[str] = None, ctx=Depends(actor)):
        store = await target_store(ctx, store_id)
        parent_of = {c["category_id"]: c.get("parent") or "" for c in await db.categories.find({}, {"category_id": 1, "parent": 1}).to_list(5000)}
        items = []
        async for p in db.products.find({"store_id": store["store_id"], **MISSING}, {"_id": 0, "product_id": 1, "name": 1, "category": 1, "image": 1}):
            g, label = estimate(p, parent_of)
            items.append({"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""), "grams": g, "rule": label})
        groups: dict = {}
        for i in items:
            key = i["rule"].split(" × ")[0]
            groups[key] = groups.get(key, 0) + 1
        doc = {"preview_id": f"wp_{uuid.uuid4().hex[:10]}", "store_id": store["store_id"], "items": items, "by": ctx["user"]["user_id"],
               "created_at": datetime.now(timezone.utc), "status": "preview"}
        await db.weight_previews.insert_one({**doc})
        return {"preview_id": doc["preview_id"], "total": len(items), "items": items,
                "groups": sorted([{"rule": k, "count": n} for k, n in groups.items()], key=lambda x: -x["count"])}

    @api.post("/product-editor/weight/{preview_id}/apply")
    async def weight_apply(preview_id: str, body: ApplyIn, ctx=Depends(actor)):
        pre = await db.weight_previews.find_one({"preview_id": preview_id}, {"store_id": 1})
        if pre:
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
            g = int(body.overrides.get(i["product_id"], i["grams"]))
            if not 1 <= g <= 500000:
                continue
            res = await db.products.update_one({"product_id": i["product_id"], "store_id": d["store_id"], **MISSING},
                                               {"$set": {"weight_grams": g, "weight_estimated": True}})  # no buyer notification: weight only
            saved += res.modified_count
        await log_activity(ctx["user"]["user_id"], "store", f"Mengisi berat perkiraan {saved} produk")
        return {"saved": saved}
