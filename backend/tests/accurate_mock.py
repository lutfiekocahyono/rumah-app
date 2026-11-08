"""Tiny fake Accurate data-host for tests: item list (per-warehouse stock) + sales-invoice save. Run: python accurate_mock.py 9911"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ITEMS = [{"id": 1, "no": "SGCTK7CKGD", "name": "Cetakan 7 Lubang", "unitPrice": 920000, "itemType": "INVENTORY", "unit1Name": "DUS"},
         {"id": 2, "no": "ACC-NEW-001", "name": "Barang Baru Accurate", "unitPrice": 15000, "itemType": "INVENTORY", "unit1Name": "PCS"}]
STOCK = {"GUDANG SIDOARJO": {"SGCTK7CKGD": 7}, "GUDANG JOMBANG": {"SGCTK7CKGD": 3}}
INVOICES = []


class H(BaseHTTPRequestHandler):
    def _send(self, body):
        b = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.endswith("/item/list.do"):
            wh = q.get("warehouseName")
            d = [{**i, "availableToSell": STOCK.get(wh, {}).get(i["no"], 0) if wh else 10} for i in ITEMS]
            return self._send({"s": True, "d": d, "sp": {"page": 1, "pageCount": 1, "rowCount": len(d)}})
        if u.path.endswith("/_invoices"):
            return self._send(INVOICES)
        self._send({"s": False, "d": ["unknown"]})

    def do_POST(self):
        u = urlparse(self.path)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()).items()}
        if u.path.endswith("/sales-invoice/save.do"):
            if any(i["number"] == form.get("number") for i in INVOICES):
                return self._send({"s": False, "d": ["Nomor faktur sudah dipakai"]})
            INVOICES.append(form)
            return self._send({"s": True, "d": ["Berhasil"], "r": {"id": len(INVOICES), "number": form.get("number")}})
        self._send({"s": False, "d": ["unknown"]})


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1] if len(sys.argv) > 1 else 9911)), H).serve_forever()
