"""
app/config.py — Configuration du service, lue depuis les variables d'environnement.

Aucune valeur secrète en dur : tout vient de l'environnement (Render → onglet
Environment de ce service). DATABASE_URL reste vide tant que les identifiants
MySQL de l'université n'ont pas été fournis — voir README.md.
"""

import os

# Exemple attendu: mysql+pymysql://user:password@host:3306/pelify_filming
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Protège POST /api/admin/preload-nearby
ADMIN_TOKEN = os.environ.get("FILMING_ADMIN_TOKEN", "")

# Overpass API (OpenStreetMap) — utilisé pour peupler nearby_places.
# Voir nearby_service.py : jamais appelé directement dans le chemin d'une requête
# utilisateur, seulement par le job en arrière-plan.
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# Rayon de recherche des commodités (mètres), avec escalade si pas assez de résultats.
NEARBY_RADIUS_DEFAULT_M = 5_000
NEARBY_RADIUS_FALLBACK_M = 15_000
NEARBY_RADIUS_MAX_M = 30_000

NEARBY_MAX_PER_CATEGORY = 10
NEARBY_MAX_TOURISM_OFFICE = 5

# Limite d'appels Overpass par minute (protection anti-surcharge, cf. cahier des charges §5/§12)
OVERPASS_MAX_CALLS_PER_MINUTE = 20

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "https://pelify.app").split(",")
    if o.strip()
]


def is_configured() -> bool:
    return bool(DATABASE_URL)
