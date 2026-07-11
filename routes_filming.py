"""
routes_filming.py v5 — Routes FastAPI pour le catalogue des lieux de tournage.
"""

import json
import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.filming_catalogue import (
    get_filming_catalogue,
    get_filming_stats,
    get_filming_countries,
    get_filming_cities,
)

router = APIRouter()

# ── Cache mémoire pour /films-tournes/meta ────────────────────
_meta_cache: dict | None = None


@router.get("/films-tournes/meta")
async def filming_meta():
    """
    Retourne toutes les années et tous les lieux (noms) présents
    dans le catalogue complet, sans pagination.
    Mis en cache en mémoire après le premier appel.
    """
    global _meta_cache
    if _meta_cache is not None:
        return JSONResponse(content=_meta_cache)

    # Utiliser le catalogue déjà en RAM (chargé au démarrage)
    from core.filming_catalogue import _catalogue, _FALLBACK
    source = _catalogue if _catalogue else _FALLBACK

    if not source:
        # Lire le fichier JSON directement si RAM encore vide
        for fname in [
            "catalogue_filming.json",
            "filming_catalogue.json",
            "data/catalogue_filming.json",
            "core/catalogue_filming.json",
        ]:
            if os.path.exists(fname):
                with open(fname, "r", encoding="utf-8") as f:
                    source = json.load(f)
                break

    if not source:
        return JSONResponse(content={"years": [], "locations": []})

    years_set = set()
    locs_set  = set()
    SKIP = {"Inconnu", "Non spécifié", ""}

    for film in source:
        yr = film.get("year")
        if yr:
            try:
                years_set.add(int(yr))
            except (ValueError, TypeError):
                pass
        # country="Inconnu" toujours → vrai nom dans locations[].name
        for loc in film.get("locations", []):
            name = (loc.get("name") or "").strip()
            if name and name not in SKIP:
                locs_set.add(name)

    _meta_cache = {
        "years":     sorted(years_set, reverse=True),
        "locations": sorted(locs_set, key=lambda x: x.lower()),
    }
    print(
        f"✅ filming_meta: {len(_meta_cache['years'])} années, "
        f"{len(_meta_cache['locations'])} lieux",
        flush=True,
    )
    return JSONResponse(content=_meta_cache)


@router.get("/films-tournes")
async def films_tournes(
    page:       int = Query(1,   ge=1),
    per_page:   int = Query(24,  ge=1, le=500),
    country:    str = Query("",  max_length=100),
    city:       str = Query("",  max_length=100),
    media_type: str = Query("",  pattern="^(movie|tv|)$"),
    q:          str = Query("",  max_length=100),
    sort:       str = Query("count_locations", pattern="^(count_locations|rating|year|title)$"),
    lang:       str = Query("fr", max_length=10),
    year:       str = Query("",  max_length=4),
):
    # get_filming_catalogue ne supporte pas year nativement
    # → on charge plus de résultats et on filtre en post-traitement
    fetch_per_page = per_page if not year.strip() else 9999

    result = await get_filming_catalogue(
        page=1,
        per_page=fetch_per_page,
        country=country.strip(),
        city=city.strip(),
        media_type=media_type.strip(),
        q=q.strip(),
        sort=sort,
        lang=lang,
    )

    # Filtre année côté serveur
    if year.strip() and result.get("results"):
        try:
            yr_int = int(year.strip())
            result["results"] = [
                f for f in result["results"]
                if f.get("year") == yr_int
            ]
        except ValueError:
            pass
        total = len(result["results"])
        result["total"] = total
        result["total_pages"] = max(1, -(-total // per_page))
        offset = (page - 1) * per_page
        result["results"] = result["results"][offset: offset + per_page]
        result["page"] = page
    elif not year.strip():
        # Pagination normale
        result = await get_filming_catalogue(
            page=page,
            per_page=per_page,
            country=country.strip(),
            city=city.strip(),
            media_type=media_type.strip(),
            q=q.strip(),
            sort=sort,
            lang=lang,
        )

    return JSONResponse(content=result)


@router.get("/films-tournes/stats")
async def filming_stats():
    result = await get_filming_stats()
    return JSONResponse(content=result)


@router.get("/films-tournes/pays")
async def filming_pays():
    result = await get_filming_countries()
    return JSONResponse(content=result)


@router.get("/films-tournes/villes")
async def filming_villes(
    country: str = Query("", max_length=100),
):
    if not country.strip():
        return JSONResponse(content={"cities": []})
    result = await get_filming_cities(country=country.strip())
    return JSONResponse(content=result)