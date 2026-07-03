"""app/schemas.py — Modèles de réponse Pydantic pour l'API publique."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class MovieOut(BaseModel):
    id: int
    wikidata_id: str | None
    tmdb_id: int | None
    title: str
    original_title: str | None
    type: Literal["film", "series"]
    release_date: date | None
    release_year: int | None
    country: str | None
    poster_url: str | None
    description: str | None
    locations_count: int

    class Config:
        from_attributes = True


class FilmingLocationOut(BaseModel):
    id: int
    movie_id: int
    name: str
    description: str | None
    scene_description: str | None
    country: str | None
    region: str | None
    city: str | None
    address: str | None
    latitude: float
    longitude: float
    is_verified: bool

    class Config:
        from_attributes = True


class NearbyPlaceOut(BaseModel):
    id: int
    name: str
    subcategory: str | None
    address: str | None
    latitude: float
    longitude: float
    website: str | None
    phone: str | None
    opening_hours: str | None
    distance_meters: int
    travel_time_minutes: int | None
    is_closest: bool
    blurb: str


class NearbyReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    location_id: int
    categories: dict[str, list[NearbyPlaceOut]]


class NearbyProcessingResponse(BaseModel):
    status: Literal["processing"] = "processing"
    message: str = "Les lieux proches sont en cours de préparation."


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database_configured: bool
