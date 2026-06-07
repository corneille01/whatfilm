"""
routes_filming.py — Routes FastAPI pour le catalogue des lieux de tournage.

Intégration dans app.py :
    1. En haut avec les imports :
           from routes_filming import router as filming_router
    2. Juste après app = FastAPI(...) :
           app.include_router(filming_router)
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.filming_catalogue import (
    get_filming_catalogue,
    get_filming_stats,
    get_filming_countries,
)

router = APIRouter()


@router.get("/films-tournes")
async def films_tournes(
    page:       int = Query(1,   ge=1),
    per_page:   int = Query(24,  ge=1, le=48),
    country:    str = Query("",  max_length=100),
    city:       str = Query("",  max_length=100),
    media_type: str = Query("",  regex="^(movie|tv|)$"),
    q:          str = Query("",  max_length=100),
    sort:       str = Query("count_locations", regex="^(count_locations|rating|year|title)$"),
    lang:       str = Query("fr", max_length=10),
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