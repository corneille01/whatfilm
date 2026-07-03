"""
app/main.py — API du service ciné-tourisme (indépendant de pelify.app, cf. README.md).

Démarre même sans DATABASE_URL configurée (/api/health répond, le reste
renvoie une 503 explicite) — permet de déployer le squelette sur Render dès
maintenant et de brancher la base dès que les identifiants sont connus.
"""

from __future__ import annotations

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.config import ADMIN_TOKEN, CORS_ALLOWED_ORIGINS, is_configured
from app.db import get_session
from app.models import AnalyticsEvent, EventType, FilmingLocation, JobStatus, Movie
from app.nearby_service import ensure_job, get_cached_nearby, run_nearby_job
from app.schemas import (
    FilmingLocationOut,
    HealthResponse,
    MovieOut,
    NearbyProcessingResponse,
    NearbyReadyResponse,
)

app = FastAPI(title="Pelify Filming Locations", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def require_db():
    if not is_configured():
        raise HTTPException(503, "Service pas encore configuré (DATABASE_URL manquante).")


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(database_configured=is_configured())


@app.get("/api/movies", response_model=list[MovieOut], dependencies=[Depends(require_db)])
async def list_movies(
    type: str | None = Query(None, pattern="^(film|series)$"),
    country: str | None = None,
    region: str | None = None,
    year: int | None = None,
    search: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    with get_session() as session:
        stmt = select(Movie, func.count(FilmingLocation.id).label("locations_count")).outerjoin(
            FilmingLocation, FilmingLocation.movie_id == Movie.id
        )
        if type:
            stmt = stmt.where(Movie.type == type)
        if country:
            stmt = stmt.where(Movie.country == country)
        if year:
            stmt = stmt.where(Movie.release_year == year)
        if search:
            stmt = stmt.where(Movie.title.ilike(f"%{search}%"))
        if region:
            stmt = stmt.join(FilmingLocation, FilmingLocation.movie_id == Movie.id).where(
                FilmingLocation.region == region
            )
        stmt = stmt.group_by(Movie.id).limit(limit).offset(offset)

        rows = session.execute(stmt).all()
        return [
            MovieOut.model_validate({**movie.__dict__, "locations_count": count})
            for movie, count in rows
        ]


@app.get(
    "/api/movies/{movie_id}/locations",
    response_model=list[FilmingLocationOut],
    dependencies=[Depends(require_db)],
)
async def movie_locations(movie_id: int, background_tasks: BackgroundTasks):
    with get_session() as session:
        movie = session.get(Movie, movie_id)
        if movie is None:
            raise HTTPException(404, "Film ou série introuvable.")
        locations = session.execute(
            select(FilmingLocation).where(FilmingLocation.movie_id == movie_id)
        ).scalars().all()

        session.add(AnalyticsEvent(event_type=EventType.movie_view, movie_id=movie_id, country=movie.country))
        return locations


@app.get(
    "/api/locations/{location_id}/nearby",
    response_model=NearbyReadyResponse | NearbyProcessingResponse,
    dependencies=[Depends(require_db)],
)
async def location_nearby(location_id: int, background_tasks: BackgroundTasks):
    with get_session() as session:
        location = session.get(FilmingLocation, location_id)
        if location is None:
            raise HTTPException(404, "Lieu de tournage introuvable.")

        cached = get_cached_nearby(session, location_id)
        session.add(AnalyticsEvent(
            event_type=EventType.location_click,
            filming_location_id=location_id,
            country=location.country,
            region=location.region,
            city=location.city,
        ))

        if cached is not None:
            return NearbyReadyResponse(location_id=location_id, categories=cached)

        ensure_job(session, location_id)

    # le vrai travail (appel Overpass) se fait après la réponse HTTP, jamais dans le chemin utilisateur
    background_tasks.add_task(run_nearby_job, get_session, location_id)
    return NearbyProcessingResponse()


@app.post("/api/admin/preload-nearby", dependencies=[Depends(require_db)])
async def preload_nearby(
    background_tasks: BackgroundTasks,
    country: str | None = None,
    region: str | None = None,
    movie_id: int | None = None,
    limit: int = Query(100, le=1000),
    x_admin_token: str = Header(...),
):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Token admin invalide ou non configuré (FILMING_ADMIN_TOKEN).")

    with get_session() as session:
        stmt = select(FilmingLocation)
        if country:
            stmt = stmt.where(FilmingLocation.country == country)
        if region:
            stmt = stmt.where(FilmingLocation.region == region)
        if movie_id:
            stmt = stmt.where(FilmingLocation.movie_id == movie_id)
        stmt = stmt.limit(limit)

        locations = session.execute(stmt).scalars().all()
        queued = 0
        for loc in locations:
            if get_cached_nearby(session, loc.id) is None and ensure_job(session, loc.id):
                queued += 1

    for loc in locations:
        background_tasks.add_task(run_nearby_job, get_session, loc.id)

    return {"queued": queued, "checked": len(locations)}
