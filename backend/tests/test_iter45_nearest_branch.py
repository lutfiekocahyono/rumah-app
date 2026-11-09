# Iteration 45: Cabang Terdekat - GET /api/branches/nearest (GPS nearest official branch)
import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def nearest(lat, lng):
    return requests.get(f"{API}/branches/nearest", params={"lat": lat, "lng": lng}, timeout=20)


# Nearest branch picked by GPS position
@pytest.mark.parametrize("lat,lng,expected", [
    (-8.17, 113.69, "pgs-jember"),
    (-7.45, 112.71, "pgs-official"),
    (-7.55, 112.24, "pgs-jombang"),
    (-7.257, 112.752, "pgs-official"),   # Surabaya -> Sidoarjo
    (-8.219, 114.369, "pgs-jember"),     # Banyuwangi -> Jember
    (-7.817, 112.012, "pgs-jombang"),    # Kediri -> Jombang
])
def test_nearest_branch(lat, lng, expected):
    r = nearest(lat, lng)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nearest"]["store_id"] == expected
    assert d["nearest"] == d["stores"][0]
    assert "_id" not in d["nearest"]


def test_sorted_by_distance_and_shape():
    d = nearest(-8.17, 113.69).json()
    ids = [s["store_id"] for s in d["stores"]]
    assert set(ids) == {"pgs-official", "pgs-jombang", "pgs-jember"}
    dist = [s["distance_km"] for s in d["stores"]]
    assert dist == sorted(dist)
    for s in d["stores"]:
        assert isinstance(s["distance_km"], (int, float)) and s["name"]
    assert d["stores"][0]["distance_km"] < 2  # ~1.1 km from Jember centre
    assert ids == ["pgs-jember", "pgs-official", "pgs-jombang"]


def test_names():
    d = nearest(-8.17, 113.69).json()
    assert "Jember" in d["nearest"]["name"]
    d = nearest(-7.45, 112.71).json()
    assert "Sidoarjo" in d["nearest"]["name"]


# Validation
@pytest.mark.parametrize("params", [{"lat": 91, "lng": 112}, {"lat": -91, "lng": 112}, {"lat": -7, "lng": 181}, {"lat": -7, "lng": -181}])
def test_invalid_coords_400(params):
    r = requests.get(f"{API}/branches/nearest", params=params, timeout=20)
    assert r.status_code == 400
    assert r.json()["detail"] == "Koordinat tidak valid"


@pytest.mark.parametrize("params", [{}, {"lat": -7}, {"lng": 112}, {"lat": "abc", "lng": 112}])
def test_missing_or_bad_params_422(params):
    r = requests.get(f"{API}/branches/nearest", params=params, timeout=20)
    assert r.status_code == 422


def test_boundary_ok():
    assert nearest(90, 180).status_code == 200
    assert nearest(-90, -180).status_code == 200


def test_nan_rejected():
    r = requests.get(f"{API}/branches/nearest", params={"lat": "nan", "lng": "nan"}, timeout=20)
    assert r.status_code in (400, 422), f"NaN accepted: {r.status_code} {r.text[:200]}"
