# storage/cache_engine/redis_client.py
#
# Client Redis basé sur le protocole REST (HTTPS) d'Upstash plutôt que le
# protocole TCP/RESP classique.
#
# Pourquoi ce changement : le client TCP classique (lib `redis`) ouvre une
# connexion persistante qui se fait fermer de façon répétée par l'infra
# Render/Upstash ("Connection closed by server"), malgré un usage très
# faible (quelques centaines de commandes/mois sur un quota de 500k).
# Le client REST Upstash transforme chaque commande en une requête HTTPS
# indépendante — pas de connexion à maintenir, donc pas de fermeture
# inattendue à gérer, et plus besoin de keepalive applicatif.
#
# Variables d'environnement attendues (au lieu de REDIS_URL) :
#   UPSTASH_REDIS_REST_URL   — ex: https://inviting-pelican-81014.upstash.io
#   UPSTASH_REDIS_REST_TOKEN — le token (pas le mot de passe TCP)
# Ces deux valeurs sont visibles dans l'onglet "REST" du dashboard Upstash.

import os
import time
from typing import Optional

from upstash_redis import Redis as UpstashRedis

UPSTASH_REDIS_REST_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_client: Optional[UpstashRedis] = None
_available: bool = False
_last_attempt: float = 0.0
_RETRY_INTERVAL: int = 30


def get_redis() -> Optional[UpstashRedis]:
    """
    Retourne un client Upstash REST prêt à l'emploi, ou None si indisponible.
    Conserve la même signature que l'ancienne version TCP pour rester
    compatible avec cache_manager.py sans modification.
    """
    global _client, _available, _last_attempt

    if _available and _client is not None:
        return _client

    now = time.time()
    if (now - _last_attempt) < _RETRY_INTERVAL:
        return None

    _last_attempt = now

    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return None

    try:
        client = UpstashRedis(
            url=UPSTASH_REDIS_REST_URL,
            token=UPSTASH_REDIS_REST_TOKEN,
        )
        # Vérifie que la connexion REST répond réellement avant de la
        # déclarer disponible (évite de propager une config invalide).
        client.ping()

        _client = client
        _available = True
        print("✅ Upstash Redis (REST) connecté", flush=True)
        return _client

    except Exception as e:
        _client = None
        _available = False
        print(f"⚠️ Upstash Redis (REST) indisponible ({e})", flush=True)
        return None


def redis_is_available() -> bool:
    return _available