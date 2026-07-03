"""
app/nearby_service.py — Logique cache-first pour les commodités proches d'un lieu de tournage.

Flux (cf. cahier des charges §4) :
  1. get_cached_nearby()  → lecture MySQL, retour immédiat si présent.
  2. Si absent : ensure_job() crée un job (ou réutilise celui déjà en cours,
     contrainte UNIQUE sur filming_location_id → jamais deux jobs actifs pour
     le même lieu) et l'API répond "processing" sans jamais appeler
     l'extérieur dans le chemin de la requête utilisateur.
  3. run_nearby_job() est le worker qui fait le vrai travail (appelé en
     tâche de fond FastAPI pour ce MVP — un vrai job queue/Celery pourra
     remplacer ça plus tard sans changer l'API publique).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import (
    NEARBY_MAX_PER_CATEGORY,
    NEARBY_MAX_TOURISM_OFFICE,
    NEARBY_RADIUS_DEFAULT_M,
    NEARBY_RADIUS_FALLBACK_M,
    NEARBY_RADIUS_MAX_M,
    OVERPASS_MAX_CALLS_PER_MINUTE,
    OVERPASS_URL,
)
from app.distance import bounding_box, estimate_travel_time_minutes, haversine_meters
from app.models import ApiJob, FilmingLocation, JobStatus, LocationNearbyCache, NearbyPlace, PlaceCategory

# Tags OSM/Overpass par catégorie. "safety" couvre police + hôpitaux (demande explicite).
OVERPASS_TAGS: dict[PlaceCategory, list[str]] = {
    PlaceCategory.accommodation: ['["tourism"~"^(hotel|guest_house|hostel|apartment)$"]'],
    PlaceCategory.restaurant: ['["amenity"~"^(restaurant|cafe)$"]'],
    PlaceCategory.transport: [
        '["railway"="station"]',
        '["amenity"="bus_station"]',
        '["highway"="bus_stop"]',
    ],
    PlaceCategory.tourism_office: ['["tourism"="information"]["information"="office"]'],
    PlaceCategory.activity: ['["tourism"~"^(attraction|museum)$"]', '["leisure"="park"]'],
    PlaceCategory.safety: ['["amenity"~"^(police|hospital|pharmacy)$"]'],
}


# ── Rate limiter global process (protection anti-surcharge, §5/§12) ──────────
class _MinuteRateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            while self._calls and now - self._calls[0] > 60:
                self._calls.popleft()
            if len(self._calls) >= self.max_per_minute:
                wait = 60 - (now - self._calls[0])
                await asyncio.sleep(max(wait, 0))
            self._calls.append(time.time())


_overpass_limiter = _MinuteRateLimiter(OVERPASS_MAX_CALLS_PER_MINUTE)

# Empêche deux workers in-process de traiter le même lieu en parallèle
# (en plus de la contrainte UNIQUE côté DB qui protège entre plusieurs instances/process).
_locations_in_flight: set[int] = set()


def get_cached_nearby(session: Session, filming_location_id: int) -> dict[str, list[dict]] | None:
    rows = (
        session.execute(
            select(LocationNearbyCache, NearbyPlace)
            .join(NearbyPlace, LocationNearbyCache.nearby_place_id == NearbyPlace.id)
            .where(LocationNearbyCache.filming_location_id == filming_location_id)
            .order_by(LocationNearbyCache.category, LocationNearbyCache.rank_position)
        )
        .all()
    )
    if not rows:
        return None

    grouped: dict[str, list[dict]] = defaultdict(list)
    for cache_row, place in rows:
        grouped[cache_row.category.value].append({
            "id": place.id,
            "name": place.name,
            "subcategory": place.subcategory,
            "address": place.address,
            "latitude": float(place.latitude),
            "longitude": float(place.longitude),
            "website": place.website,
            "phone": place.phone,
            "opening_hours": place.opening_hours,
            "distance_meters": cache_row.distance_meters,
            "travel_time_minutes": cache_row.travel_time_minutes,
            "is_closest": cache_row.is_closest,
            "blurb": _blurb(cache_row.category.value, place.name, cache_row.distance_meters),
        })
    # garantit toutes les catégories dans la réponse, même vides
    for cat in PlaceCategory:
        grouped.setdefault(cat.value, [])
    return dict(grouped)


def _blurb(category: str, name: str, distance_m: int) -> str:
    """Phrase automatique décrivant la commodité la plus proche (cf. cahier des charges §8)."""
    templates = {
        "accommodation": f"{name} est situé à {distance_m} mètres de ce lieu de tournage. "
                          "C'est l'hébergement le plus proche autour de ce point.",
        "restaurant": f"{name} est situé à {distance_m} mètres de ce lieu de tournage. "
                       "C'est le restaurant le plus proche pour prolonger la visite.",
        "transport": f"{name} est situé à {distance_m} mètres. "
                     "C'est le point de transport le plus proche du lieu de tournage.",
        "tourism_office": f"L'office de tourisme le plus proche ({name}) se trouve à {distance_m} mètres. "
                           "Il peut accompagner les visiteurs dans la découverte du territoire.",
        "activity": f"{name} est situé à {distance_m} mètres autour du lieu de tournage.",
        "safety": f"{name} est situé à {distance_m} mètres de ce lieu de tournage.",
    }
    return templates.get(category, f"{name} est situé à {distance_m} mètres de ce lieu de tournage.")


def ensure_job(session: Session, filming_location_id: int) -> bool:
    """Crée un job pending s'il n'en existe pas déjà un actif pour ce lieu. Retourne True si créé."""
    existing = session.execute(
        select(ApiJob).where(ApiJob.filming_location_id == filming_location_id)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == JobStatus.failed and existing.attempt_count < 5:
            existing.status = JobStatus.pending
            return True
        return False
    session.add(ApiJob(filming_location_id=filming_location_id, status=JobStatus.pending))
    return True


async def _query_overpass(client: httpx.AsyncClient, lat: float, lng: float, radius_m: int) -> dict[PlaceCategory, list[dict]]:
    clauses = []
    for category, tag_filters in OVERPASS_TAGS.items():
        for tf in tag_filters:
            clauses.append(f'node{tf}(around:{radius_m},{lat},{lng});')
            clauses.append(f'way{tf}(around:{radius_m},{lat},{lng});')
    query = f"[out:json][timeout:25];({''.join(clauses)});out center tags;"

    await _overpass_limiter.acquire()
    resp = await client.post(OVERPASS_URL, data={"data": query}, timeout=30.0)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    by_category: dict[PlaceCategory, list[dict]] = defaultdict(list)
    for el in elements:
        tags = el.get("tags", {})
        lat_el = el.get("lat") or el.get("center", {}).get("lat")
        lng_el = el.get("lon") or el.get("center", {}).get("lon")
        if lat_el is None or lng_el is None or not tags.get("name"):
            continue
        category, subcategory = _classify(tags)
        if category is None:
            continue
        by_category[category].append({
            "external_id": f"{el['type']}/{el['id']}",
            "name": tags["name"],
            "subcategory": subcategory,
            "address": _format_address(tags),
            "latitude": lat_el,
            "longitude": lng_el,
            "website": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "opening_hours": tags.get("opening_hours"),
        })
    return by_category


def _classify(tags: dict) -> tuple[PlaceCategory | None, str | None]:
    if tags.get("tourism") in {"hotel", "guest_house", "hostel", "apartment"}:
        return PlaceCategory.accommodation, tags["tourism"]
    if tags.get("amenity") in {"restaurant", "cafe"}:
        return PlaceCategory.restaurant, tags["amenity"]
    if tags.get("railway") == "station" or tags.get("amenity") == "bus_station" or tags.get("highway") == "bus_stop":
        return PlaceCategory.transport, tags.get("railway") or tags.get("amenity") or tags.get("highway")
    if tags.get("tourism") == "information" and tags.get("information") == "office":
        return PlaceCategory.tourism_office, "office"
    if tags.get("tourism") in {"attraction", "museum"} or tags.get("leisure") == "park":
        return PlaceCategory.activity, tags.get("tourism") or tags.get("leisure")
    if tags.get("amenity") in {"police", "hospital", "pharmacy"}:
        return PlaceCategory.safety, tags["amenity"]
    return None, None


def _format_address(tags: dict) -> str | None:
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else None


async def run_nearby_job(session_factory, filming_location_id: int) -> None:
    """
    Worker de fond (appelé via FastAPI BackgroundTasks pour ce MVP).
    session_factory: le context manager get_session() de app.db, passé pour éviter
    un import circulaire et pour que ce module reste testable indépendamment.
    """
    if filming_location_id in _locations_in_flight:
        return
    _locations_in_flight.add(filming_location_id)
    try:
        with session_factory() as session:
            job = session.execute(
                select(ApiJob).where(ApiJob.filming_location_id == filming_location_id)
            ).scalar_one_or_none()
            if job is None or job.status not in (JobStatus.pending,):
                return
            job.status = JobStatus.running
            job.attempt_count += 1
            location = session.get(FilmingLocation, filming_location_id)
            if location is None:
                job.status = JobStatus.failed
                job.last_error = "filming_location introuvable"
                return
            lat, lng = float(location.latitude), float(location.longitude)

        results: dict[PlaceCategory, list[dict]] = defaultdict(list)
        async with httpx.AsyncClient(headers={"User-Agent": "PelifyFilmingBot/1.0 (https://pelify.app)"}) as client:
            for radius in (NEARBY_RADIUS_DEFAULT_M, NEARBY_RADIUS_FALLBACK_M, NEARBY_RADIUS_MAX_M):
                found = await _query_overpass(client, lat, lng, radius)
                for cat, items in found.items():
                    if not results[cat]:
                        results[cat] = items
                # arrête l'escalade si toutes les catégories ont au moins un résultat
                if all(results.get(c) for c in PlaceCategory):
                    break

        with session_factory() as session:
            for category, items in results.items():
                limit = NEARBY_MAX_TOURISM_OFFICE if category == PlaceCategory.tourism_office else NEARBY_MAX_PER_CATEGORY
                scored = sorted(
                    (
                        {**item, "distance_meters": round(haversine_meters(lat, lng, item["latitude"], item["longitude"]))}
                        for item in items
                    ),
                    key=lambda x: x["distance_meters"],
                )[:limit]

                for rank, item in enumerate(scored, start=1):
                    place = session.execute(
                        select(NearbyPlace).where(
                            NearbyPlace.source == "overpass",
                            NearbyPlace.external_id == item["external_id"],
                        )
                    ).scalar_one_or_none()
                    if place is None:
                        place = NearbyPlace(
                            external_id=item["external_id"],
                            name=item["name"],
                            category=category,
                            subcategory=item["subcategory"],
                            country=location.country,
                            region=location.region,
                            city=location.city,
                            address=item["address"],
                            latitude=item["latitude"],
                            longitude=item["longitude"],
                            website=item["website"],
                            phone=item["phone"],
                            opening_hours=item["opening_hours"],
                            source="overpass",
                        )
                        session.add(place)
                        session.flush()  # récupère place.id

                    cache_entry = session.execute(
                        select(LocationNearbyCache).where(
                            LocationNearbyCache.filming_location_id == filming_location_id,
                            LocationNearbyCache.nearby_place_id == place.id,
                        )
                    ).scalar_one_or_none()
                    if cache_entry is None:
                        cache_entry = LocationNearbyCache(
                            filming_location_id=filming_location_id,
                            nearby_place_id=place.id,
                            category=category,
                        )
                        session.add(cache_entry)
                    cache_entry.distance_meters = item["distance_meters"]
                    cache_entry.travel_time_minutes = estimate_travel_time_minutes(item["distance_meters"])
                    cache_entry.rank_position = rank
                    cache_entry.is_closest = rank == 1

            job = session.execute(
                select(ApiJob).where(ApiJob.filming_location_id == filming_location_id)
            ).scalar_one_or_none()
            if job:
                job.status = JobStatus.done
    except Exception as e:  # noqa: BLE001 — on ne doit jamais laisser planter le worker de fond
        with session_factory() as session:
            job = session.execute(
                select(ApiJob).where(ApiJob.filming_location_id == filming_location_id)
            ).scalar_one_or_none()
            if job:
                job.status = JobStatus.failed
                job.last_error = str(e)[:2000]
    finally:
        _locations_in_flight.discard(filming_location_id)
