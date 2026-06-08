"""
poi_proxy.py — À coller dans ton api.py FastAPI
Proxy Nominatim avec cache mémoire 24h.
Évite les rate-limits et protège la clé User-Agent.
"""

import asyncio
import time
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

# ── Cache mémoire simple ──────────────────────────────────────────────────────
_poi_cache: dict = {}          # key → {"data": [...], "ts": float}
_POI_CACHE_TTL = 86400         # 24h en secondes
_POI_NOMINATIM_DELAY = 1.1     # Respecter la politique 1 req/s de Nominatim

_nominatim_lock = asyncio.Lock()
_last_nominatim_call = 0.0


async def _nominatim_search(q: str, viewbox: str, limit: int = 5) -> list:
    """Appel Nominatim avec rate-limit global (1 req/s)."""
    global _last_nominatim_call

    async with _nominatim_lock:
        now = time.time()
        wait = _POI_NOMINATIM_DELAY - (now - _last_nominatim_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_nominatim_call = time.time()

        url = (
            f"https://nominatim.openstreetmap.org/search"
            f"?format=json&limit={limit}&viewbox={viewbox}&bounded=1&q={q}"
        )
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "ShadowFrame/1.0 (quelfilm.app; contact@quelfilm.app)",
                    "Accept-Language": "fr,en;q=0.9",
                }
            )
            resp.raise_for_status()
            return resp.json()


@router.get("/api/poi")
async def get_poi(
    lat: float = Query(...),
    lng: float = Query(...),
    type: str = Query("hotel"),   # hotel | restaurant | transport | service
    radius_deg: float = 0.008,    # ≈ 800m
):
    """
    Proxy POI via Nominatim.
    Retourne max 5 POI du type demandé autour de (lat, lng).
    Cache 24h côté serveur.
    """
    allowed_types = {"hotel", "restaurant", "transport", "service"}
    if type not in allowed_types:
        raise HTTPException(400, f"type must be one of {allowed_types}")

    cache_key = f"{type}_{lat:.3f}_{lng:.3f}"
    now = time.time()

    # Hit cache
    if cache_key in _poi_cache:
        entry = _poi_cache[cache_key]
        if now - entry["ts"] < _POI_CACHE_TTL:
            return {"type": type, "results": entry["data"], "cached": True}

    # Query Nominatim
    q_map = {
        "hotel":      "hotel",
        "restaurant": "restaurant",
        "transport":  "gare station",
        "service":    "hôpital police",
    }
    viewbox = f"{lng - radius_deg},{lat + radius_deg},{lng + radius_deg},{lat - radius_deg}"

    try:
        items = await _nominatim_search(q_map[type], viewbox, limit=5)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Nominatim error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(502, f"POI fetch failed: {e}")

    results = [
        {
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "name": item.get("display_name", "").split(",")[0],
            "type": type,
        }
        for item in items
        if item.get("lat") and item.get("lon")
    ]

    _poi_cache[cache_key] = {"data": results, "ts": now}
    return {"type": type, "results": results, "cached": False}


@router.get("/api/poi/auto")
async def get_poi_auto(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_deg: float = 0.008,
):
    """
    Charge les 4 types de POI en une seule requête (utilisé par _autoLoadPOIsAround).
    Retourne tous les POI regroupés.
    """
    types = ["hotel", "restaurant", "transport", "service"]
    tasks = [
        get_poi(lat=lat, lng=lng, type=t, radius_deg=radius_deg)
        for t in types
    ]
    results_by_type = await asyncio.gather(*tasks, return_exceptions=True)

    all_poi = []
    for i, res in enumerate(results_by_type):
        if isinstance(res, Exception):
            continue
        all_poi.extend(res.get("results", []))

    return {"results": all_poi}