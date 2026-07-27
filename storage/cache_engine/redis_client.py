# storage/cache_engine/redis_client.py
#
# Substitut à Upstash Redis basé sur Postgres (Neon), utilisé après
# l'épuisement du quota gratuit Upstash (500k commandes REST/mois).
#
# Le reste du code (cache_manager.py, lock_manager.py, app.py) parle à
# un objet retourné par get_redis() en utilisant les mêmes méthodes que
# le client `upstash_redis` : get/set/setex/delete/scan/scan_iter/ttl/
# dbsize/eval/ping. Cette classe NeonKV réimplémente ces méthodes
# au-dessus d'une simple table clé/valeur Postgres, donc AUCUN autre
# fichier n'a besoin d'être modifié.
#
# Variable d'environnement attendue (au choix) :
#   NEON_DATABASE_URL — chaîne de connexion Postgres Neon
#   DATABASE_URL       — fallback si NEON_DATABASE_URL n'est pas définie
#
# Format attendu, ex :
#   postgresql://user:password@ep-xxx.eu-central-1.aws.neon.tech/dbname?sslmode=require

import os
import time
import random
from typing import Optional, List, Tuple

import psycopg2
import psycopg2.extensions

NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

_client: Optional["NeonKV"] = None
_available: bool = False
_last_attempt: float = 0.0
_RETRY_INTERVAL: int = 30


class NeonKV:
    """
    Client clé-valeur minimal au-dessus de Postgres, avec la même
    interface que le client REST Upstash utilisé précédemment.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None
        self._connect()
        self._ensure_schema()

    def _connect(self):
        self._conn = psycopg2.connect(self._dsn, connect_timeout=5)
        self._conn.autocommit = True

    def _ensure_conn(self):
        try:
            if self._conn is None or self._conn.closed:
                self._connect()
        except Exception:
            self._connect()

    def _execute(self, query: str, params: tuple = ()):
        """Exécute une requête, en réessayant une fois après reconnexion
        si la connexion a été coupée (fréquent avec Neon en veille)."""
        for attempt in (1, 2):
            try:
                self._ensure_conn()
                with self._conn.cursor() as cur:
                    cur.execute(query, params)
                    if cur.description:
                        return cur.fetchall()
                    return cur.rowcount
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                if attempt == 2:
                    raise
                self._connect()

    def _ensure_schema(self):
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at DOUBLE PRECISION
            )
            """
        )
        self._execute("CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store (expires_at)")

    def _maybe_cleanup(self):
        # Purge opportuniste (~2% des appels) des clés expirées, pour ne
        # pas laisser grossir la table indéfiniment (pas d'expiration
        # automatique côté Postgres contrairement à Redis).
        if random.random() < 0.02:
            try:
                self._execute("DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < %s", (time.time(),))
            except Exception:
                pass

    def ping(self) -> bool:
        self._execute("SELECT 1")
        return True

    def get(self, key: str) -> Optional[str]:
        rows = self._execute("SELECT value, expires_at FROM kv_store WHERE key = %s", (key,))
        if not rows:
            return None

        value, expires_at = rows[0]

        if expires_at is not None and expires_at < time.time():
            self._execute("DELETE FROM kv_store WHERE key = %s", (key,))
            return None

        return value

    def set(self, key: str, value: str, nx: bool = False, ex: Optional[int] = None):
        expires_at = (time.time() + ex) if ex else None
        self._maybe_cleanup()

        if nx:
            # Purge d'abord une éventuelle clé expirée du même nom, pour
            # que l'INSERT ON CONFLICT DO NOTHING se comporte comme un
            # SET NX Redis (qui ignore les clés expirées).
            self._execute(
                "DELETE FROM kv_store WHERE key = %s AND expires_at IS NOT NULL AND expires_at < %s",
                (key, time.time()),
            )
            rowcount = self._execute(
                "INSERT INTO kv_store (key, value, expires_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO NOTHING",
                (key, value, expires_at),
            )
            return True if rowcount else None

        self._execute(
            """
            INSERT INTO kv_store (key, value, expires_at) VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
            """,
            (key, value, expires_at),
        )
        return True

    def setex(self, key: str, ttl: int, value: str):
        return self.set(key, value, ex=ttl)

    def delete(self, key: str) -> int:
        rowcount = self._execute("DELETE FROM kv_store WHERE key = %s", (key,))
        return rowcount or 0

    def eval(self, script: str, keys: List[str], args: List[str]):
        """
        N'exécute pas réellement le script Lua : on ne reproduit que le
        comportement précis utilisé par lock_manager.py (unlock atomique
        "si value == token alors delete").
        """
        key = keys[0]
        token = args[0]
        rowcount = self._execute("DELETE FROM kv_store WHERE key = %s AND value = %s", (key, token))
        return 1 if rowcount else 0

    def scan(self, cursor: int, match: Optional[str] = None, count: int = 200) -> Tuple[int, List[str]]:
        pattern = match.replace("*", "%") if match else "%"
        rows = self._execute(
            "SELECT key FROM kv_store WHERE key LIKE %s AND (expires_at IS NULL OR expires_at > %s)",
            (pattern, time.time()),
        )
        keys = [r[0] for r in rows] if rows else []
        # Pas de pagination réelle : on renvoie tout en un seul lot et un
        # curseur à 0 pour signaler la fin (comportement compatible avec
        # la boucle "while cursor != 0" de redis_scan dans cache_manager.py).
        return 0, keys

    def scan_iter(self, match: Optional[str] = None, count: int = 200):
        _, keys = self.scan(0, match=match, count=count)
        return iter(keys)

    def ttl(self, key: str) -> int:
        rows = self._execute("SELECT expires_at FROM kv_store WHERE key = %s", (key,))
        if not rows:
            return -2
        expires_at = rows[0][0]
        if expires_at is None:
            return -1
        remaining = expires_at - time.time()
        return max(int(remaining), 0)

    def dbsize(self) -> int:
        rows = self._execute(
            "SELECT COUNT(*) FROM kv_store WHERE expires_at IS NULL OR expires_at > %s",
            (time.time(),),
        )
        return rows[0][0] if rows else 0


def get_redis() -> Optional[NeonKV]:
    """
    Retourne un client NeonKV prêt à l'emploi, ou None si indisponible.
    Conserve la même signature/le même comportement que l'ancienne
    version Upstash pour rester compatible sans modification ailleurs.
    """
    global _client, _available, _last_attempt

    if _available and _client is not None:
        return _client

    now = time.time()
    if (now - _last_attempt) < _RETRY_INTERVAL:
        return None

    _last_attempt = now

    if not NEON_DATABASE_URL:
        return None

    try:
        client = NeonKV(NEON_DATABASE_URL)
        client.ping()

        _client = client
        _available = True
        print("✅ Neon Postgres (cache KV) connecté", flush=True)
        return _client

    except Exception as e:
        _client = None
        _available = False
        print(f"⚠️ Neon Postgres (cache KV) indisponible ({e})", flush=True)
        return None


def redis_is_available() -> bool:
    return _available