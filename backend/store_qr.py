"""Kode QR halaman toko cabang: PNG atau PDF A4 siap cetak (nama toko, logo, QR ke /shop/{id})."""
import io
from typing import Optional

import httpx
import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

BRAND = (241, 90, 36)  # PGS orange, same in light & dark: this is a printed sticker


def _font(size: int, bold: bool = False):
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/liberation/{name}", size)
    except OSError:
        return ImageFont.load_default(size=size)


async def fetch_logo(url: str) -> Optional[Image.Image]:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(url if url.startswith("http") else f"http://localhost:8001{url}")
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None
    return None


def _round_logo(logo: Image.Image, size: int) -> Image.Image:
    logo = logo.copy()
    logo.thumbnail((size, size))
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    canvas.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(canvas, (0, 0), mask)
    return out


def _qr(url: str, px: int, logo: Optional[Image.Image]) -> Image.Image:
    q = qrcode.QRCode(error_correction=ERROR_CORRECT_H, border=2, box_size=10)
    q.add_data(url)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("RGBA").resize((px, px), Image.NEAREST)
    if logo:  # small logo in the middle; level H keeps the code readable
        s = px // 5
        ring = Image.new("RGBA", (s + 16, s + 16), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, s + 15, s + 15), fill=(255, 255, 255, 255))
        img.paste(ring, ((px - s - 16) // 2, (px - s - 16) // 2), ring)
        lg = _round_logo(logo, s)
        img.paste(lg, ((px - s) // 2, (px - s) // 2), lg)
    return img


def _center(d: ImageDraw.ImageDraw, w: int, y: int, text: str, font, fill) -> int:
    box = d.textbbox((0, 0), text, font=font)
    d.text(((w - (box[2] - box[0])) // 2, y), text, font=font, fill=fill)
    return y + (box[3] - box[1])


def render(url: str, name: str, city: str, address: str, logo: Optional[Image.Image], fmt: str) -> bytes:
    """A4 portrait at 150 dpi (1240x1754) for print; PNG is the same poster."""
    W, H = 1240, 1754
    page = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(page)
    d.rectangle((0, 0, W, 260), fill=BRAND)
    y = 70
    if logo:
        lg = _round_logo(logo, 170)
        page.paste(lg, ((W - 170) // 2, 175), lg)
        y = 380
    else:
        y = 330
    _center(d, W, 90 if not logo else 60, "Pusat Grosir Sidoarjo", _font(44, True), "white")
    y = _center(d, W, y, name, _font(72, True), (30, 30, 30)) + 24
    if city:
        y = _center(d, W, y, city, _font(40), (90, 90, 90)) + 10
    y += 40
    qr = _qr(url, 820, logo)
    page.paste(qr, ((W - 820) // 2, y), qr)
    y += 820 + 40
    y = _center(d, W, y, "Scan untuk belanja di toko ini", _font(52, True), BRAND) + 24
    if address:
        _center(d, W, y, address[:70], _font(32), (90, 90, 90))
    _center(d, W, H - 90, url.replace("https://", "").replace("http://", "")[:80], _font(28), (120, 120, 120))
    buf = io.BytesIO()
    if fmt == "pdf":
        page.save(buf, "PDF", resolution=150)
    else:
        page.save(buf, "PNG", optimize=True)
    return buf.getvalue()
