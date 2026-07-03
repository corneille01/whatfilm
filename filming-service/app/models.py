"""
app/models.py — Modèles SQLAlchemy, miroir exact de sql/schema.sql.

Toute modification doit être répercutée dans les deux fichiers (pas de
migration automatique en place pour ce MVP — Alembic pourra être ajouté
plus tard si besoin).
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    film = "film"
    series = "series"


class PlaceCategory(str, enum.Enum):
    accommodation = "accommodation"
    restaurant = "restaurant"
    transport = "transport"
    tourism_office = "tourism_office"
    activity = "activity"
    safety = "safety"  # police, hôpital, pharmacie...


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class EventType(str, enum.Enum):
    movie_view = "movie_view"
    location_click = "location_click"
    nearby_place_click = "nearby_place_click"
    filter_country = "filter_country"
    filter_date = "filter_date"
    filter_type = "filter_type"


class Movie(Base):
    __tablename__ = "filming_pelify_movies"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    tmdb_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(500))
    type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    country: Mapped[str | None] = mapped_column(String(150))
    poster_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    locations: Mapped[list["FilmingLocation"]] = relationship(back_populates="movie", cascade="all, delete-orphan")


class FilmingLocation(Base):
    __tablename__ = "filming_pelify_filming_locations"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    movie_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("filming_pelify_movies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scene_description: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(150))
    region: Mapped[str | None] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    # NB: la colonne géospatiale `geom` (POINT SRID 4326) existe côté SQL mais
    # n'est pas mappée ici — les requêtes de distance MVP utilisent lat/lng
    # (Haversine en Python, cf. distance.py), pas de fonctions spatiales MySQL.

    movie: Mapped["Movie"] = relationship(back_populates="locations")


class NearbyPlace(Base):
    __tablename__ = "filming_pelify_nearby_places"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_nearby_places_external"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[PlaceCategory] = mapped_column(Enum(PlaceCategory), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(150))
    region: Mapped[str | None] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(50))
    opening_hours: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LocationNearbyCache(Base):
    __tablename__ = "filming_pelify_location_nearby_cache"
    __table_args__ = (UniqueConstraint("filming_location_id", "nearby_place_id", name="uq_location_nearby"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    filming_location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filming_pelify_filming_locations.id", ondelete="CASCADE"), nullable=False
    )
    nearby_place_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filming_pelify_nearby_places.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[PlaceCategory] = mapped_column(Enum(PlaceCategory), nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_time_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    place: Mapped["NearbyPlace"] = relationship()


class ApiJob(Base):
    __tablename__ = "filming_pelify_api_jobs"
    __table_args__ = (UniqueConstraint("filming_location_id", name="uq_api_jobs_location"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    filming_location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filming_pelify_filming_locations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AnalyticsEvent(Base):
    __tablename__ = "filming_pelify_analytics_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    movie_id: Mapped[int | None] = mapped_column(BigInteger)
    filming_location_id: Mapped[int | None] = mapped_column(BigInteger)
    country: Mapped[str | None] = mapped_column(String(150))
    region: Mapped[str | None] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
