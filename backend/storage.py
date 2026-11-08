"""Emergent Object Storage helpers (banner images). Key stays on the backend only."""
import logging
import os

import requests

log = logging.getLogger("storage")

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "pusat-grosir-sidoarjo"
_storage_key = None


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _call(method: str, path: str, **kw) -> requests.Response:
    global _storage_key
    for attempt in range(2):
        resp = requests.request(method, f"{STORAGE_URL}/objects/{path}",
                                headers={"X-Storage-Key": init_storage(), **kw.pop("headers", {})}, **kw)
        if resp.status_code == 503 and attempt == 0:  # stale key -> re-init once
            _storage_key = None
            continue
        return resp
    return resp


def put_object(path: str, data: bytes, content_type: str) -> dict:
    resp = _call("PUT", path, headers={"Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    resp = _call("GET", path, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
