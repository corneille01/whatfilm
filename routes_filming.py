"""
routes_filming.py v4 — Routes FastAPI pour le catalogue des lieux de tournage.
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
    Retourne toutes les années et tous les lieux de tournage présents
    dans le catalogue complet (22 000+ films), sans pagination.

    Utilisé par le frontend pour peupler les filtres Année et Lieu.
    Mis en cache en mémoire après le premier appel.

    Réponse :
    {
      "years":     [2024, 2023, ..., 1896],
      "locations": ["Aalborg", "Amsterdam", "Paris", "Tokyo", ...]
    }
    """
    global _meta_cache
    if _meta_cache is not None:
        return JSONResponse(content=_meta_cache)

    # Chercher le fichier catalogue JSON
    catalogue = None
    catalogue_paths = [
        "filming_catalogue.json",
        "data/filming_catalogue.json",
        "core/filming_catalogue.json",
    ]
    for path in catalogue_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                catalogue = json.load(f)
            break

    # Fallback : utiliser le module filming_catalogue déjà chargé
    if catalogue is None:
        try:
            from core import filming_catalogue as fc
            # Essayer get_catalogue() ou l'attribut _catalogue
            if hasattr(fc, "get_catalogue"):
                catalogue = fc.get_catalogue()
            elif hasattr(fc, "_catalogue"):
                catalogue = fc._catalogue
            else:
                # Dernier recours : appeler get_filming_catalogue sans filtre
                raw = await get_filming_catalogue(
                    page=1, per_page=99999, country="", city="",
                    media_type="", q="", sort="count_locations", lang="fr",
                )
                catalogue = raw.get("results", [])
        except Exception as e:
            print(f"⚠️ filming_meta fallback KO: {e}", flush=True)
            return JSONResponse(content={"years": [], "locations": []})

    years_set = set()
    locs_set  = set()

    _SKIP = {"Inconnu", "Non spécifié", ""}

    for film in catalogue:
        yr = film.get("year")
        if yr:
            try:
                years_set.add(int(yr))
            except (ValueError, TypeError):
                pass

        for loc in film.get("locations", []):
            # country est toujours "Inconnu" dans ce catalogue —
            # le vrai nom du lieu est dans le champ "name"
            country_val = (loc.get("country") or "").strip()
            name_val    = (loc.get("name")    or "").strip()

            if country_val and country_val not in _SKIP:
                locs_set.add(country_val)
            elif name_val and name_val not in _SKIP:
                locs_set.add(name_val)

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
    media_type: str = Query("",  regex="^(movie|tv|)$"),
    q:          str = Query("",  max_length=100),
    sort:       str = Query("count_locations", regex="^(count_locations|rating|year|title)$"),
    lang:       str = Query("fr", max_length=10),
    year:       str = Query("",  max_length=4),
):
    result = await get_filming_catalogue(
        page=page, per_page=per_page,
        country=country.strip(), city=city.strip(),
        media_type=media_type.strip(), q=q.strip(),
        sort=sort, lang=lang,
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
    """
    Retourne les villes disponibles pour un pays donné,
    triées par nombre de films décroissant.
    """
    if not country.strip():
        return JSONResponse(content={"cities": []})
    result = await get_filming_cities(country=country.strip())
    return JSONResponse(content=result)