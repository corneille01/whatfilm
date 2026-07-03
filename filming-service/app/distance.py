"""
app/distance.py — Calcul de distance et bounding box, sans dépendance spatiale MySQL.

MVP volontairement simple (cf. cahier des charges §10) : filtrer par bounding
box en SQL (rapide, utilise les index lat/lng), puis calculer la distance
exacte en Python avec Haversine sur le sous-ensemble déjà filtré — jamais sur
toute la table.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """Retourne (lat_min, lat_max, lng_min, lng_max) pour un filtre SQL grossier avant Haversine exact."""
    lat_delta = radius_m / 111_320  # ~mètres par degré de latitude, constant
    lng_delta = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


def estimate_travel_time_minutes(distance_m: float, walking_speed_kmh: float = 4.5) -> int:
    """Estimation simple à pied — pas d'appel à un service de routing externe pour le MVP."""
    hours = (distance_m / 1000) / walking_speed_kmh
    return max(1, round(hours * 60))
