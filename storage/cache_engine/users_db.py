# storage/cache_engine/users_db.py
#
# Couche "comptes" pour la monétisation de Pelify : utilisateurs (magic
# link, pas de mot de passe), sessions, abonnements Stripe, et quota
# d'essai gratuit journalier compté PAR IP (et non par compte — voir
# check_and_consume_free_quota).
#
# Même style que neon_embeddings.py / redis_client.py : connexion
# psycopg2 paresseuse, jamais d'exception qui remonte à l'appelant côté
# lecture (on renvoie None/False), mais les écritures liées à l'argent
# (Stripe) remontent l'erreur pour ne pas perdre silencieusement un
# paiement — à l'appelant (core/billing.py) de logger/alerter.
#
# Variables d'environnement :
#   NEON_DATABASE_URL / DATABASE_URL — déjà utilisées ailleurs dans le repo

import os
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

MAGIC_LINK_TTL_MINUTES = 15
SESSION_TTL_DAYS = 30
FREE_TRIALS_PER_DAY = 1
LOGIN_CODE_MAX_ATTEMPTS = 5

_conn = None
_schema_ready = False


def _get_conn(retry: bool = True):
    """
    Connexion Neon paresseuse et réutilisée. Neon (serverless) peut se
    mettre en veille après inactivité et prendre plusieurs secondes à se
    réveiller — un premier essai peut donc légitimement échouer sans que
    la base soit réellement en panne. On retente une fois avant d'abandonner,
    pour éviter qu'un utilisateur avec une session parfaitement valide soit
    déconnecté juste parce que Neon se réveillait au mauvais moment.
    """
    global _conn
    try:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(NEON_DATABASE_URL, connect_timeout=10)
            _conn.autocommit = True
    except Exception as e:
        _conn = None
        if retry:
            print(f"⚠️ users_db: connexion Neon KO, nouvel essai ({e})", flush=True)
            time.sleep(1.5)
            return _get_conn(retry=False)
        print(f"⚠️ users_db: connexion Neon KO après nouvel essai ({e})", flush=True)
    return _conn


def _reset_conn():
    """Force une reconnexion à la prochaine requête (connexion probablement morte)."""
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:
        pass
    _conn = None


def ensure_schema():
    """Idempotent, à appeler au démarrage de l'app (lifespan)."""
    global _schema_ready
    if _schema_ready:
        return
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    signup_ip TEXT,
                    stripe_customer_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_magic_links (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES pelify_users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            # Migration douce : ajoute les colonnes du code à 6 chiffres si la
            # table existait déjà avant cette fonctionnalité.
            cur.execute("""
                ALTER TABLE pelify_magic_links
                    ADD COLUMN IF NOT EXISTS code_hash TEXT,
                    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES pelify_users(id) ON DELETE CASCADE,
                    token_hash TEXT UNIQUE NOT NULL,
                    ip TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES pelify_users(id) ON DELETE CASCADE,
                    stripe_subscription_id TEXT UNIQUE,
                    status TEXT NOT NULL DEFAULT 'none',
                    current_period_end TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_usage (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES pelify_users(id) ON DELETE CASCADE,
                    used_on DATE NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(user_id, used_on)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pelify_ip_usage (
                    id SERIAL PRIMARY KEY,
                    ip TEXT NOT NULL,
                    used_on DATE NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(ip, used_on)
                );
            """)
        _schema_ready = True
        print("✅ users_db: schéma prêt", flush=True)
    except Exception as e:
        print(f"⚠️ users_db: ensure_schema KO ({e})", flush=True)


# ────────────────────────────────────────────────────────────────
# Tokens
# ────────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


# ────────────────────────────────────────────────────────────────
# Utilisateurs / magic link
# ────────────────────────────────────────────────────────────────

def get_or_create_user(email: str, signup_ip: str) -> Optional[int]:
    """Retourne l'id utilisateur, en le créant si besoin. None si Neon KO."""
    conn = _get_conn()
    if not conn:
        return None
    email = email.strip().lower()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pelify_users WHERE email = %s;", (email,))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute(
                "INSERT INTO pelify_users (email, signup_ip) VALUES (%s, %s) RETURNING id;",
                (email, signup_ip),
            )
            return cur.fetchone()[0]
    except Exception as e:
        print(f"⚠️ users_db.get_or_create_user KO ({e})", flush=True)
        return None


def _new_login_code() -> str:
    """Code à 6 chiffres, généré avec secrets (pas random) même si l'entropie
    reste faible — le vrai rempart contre le brute-force est le compteur
    LOGIN_CODE_MAX_ATTEMPTS + l'expiration à 15 min, pas la longueur du code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def create_magic_link(user_id: int) -> Optional[tuple]:
    """Crée un lien de connexion ET un code à 6 chiffres pour le même essai
    de connexion (deux façons d'arriver au même résultat — le lien pour le
    confort, le code pour contourner les navigateurs intégrés des apps mail
    qui ne partagent pas leurs cookies avec le vrai navigateur).
    Retourne (token, code) EN CLAIR (jamais stockés tels quels), ou None."""
    conn = _get_conn()
    if not conn:
        return None
    token = _new_token()
    code = _new_login_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_TTL_MINUTES)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pelify_magic_links (user_id, token_hash, code_hash, expires_at) VALUES (%s, %s, %s, %s);",
                (user_id, _hash_token(token), _hash_token(code), expires_at),
            )
        return token, code
    except Exception as e:
        print(f"⚠️ users_db.create_magic_link KO ({e})", flush=True)
        return None


def consume_magic_link(token: str) -> Optional[int]:
    """Valide le token (non expiré, non utilisé), le marque consommé, retourne user_id ou None."""
    conn = _get_conn()
    if not conn:
        return None
    token_hash = _hash_token(token)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id FROM pelify_magic_links
                WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
                ORDER BY id DESC LIMIT 1;
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            link_id, user_id = row
            cur.execute("UPDATE pelify_magic_links SET used_at = now() WHERE id = %s;", (link_id,))
            return user_id
    except Exception as e:
        print(f"⚠️ users_db.consume_magic_link KO ({e})", flush=True)
        return None


def verify_login_code(user_id: int, code: str) -> bool:
    """
    Vérifie le code à 6 chiffres du dernier essai de connexion en cours pour
    ce compte. Incrémente un compteur de tentatives par lien (pas par
    utilisateur/IP) pour limiter le brute-force sans pénaliser tout le
    compte si un autre lien légitime est demandé ensuite.
    """
    conn = _get_conn()
    if not conn:
        return False
    code_hash = _hash_token(code)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code_hash, attempts FROM pelify_magic_links
                WHERE user_id = %s AND used_at IS NULL AND expires_at > now()
                    AND code_hash IS NOT NULL
                ORDER BY id DESC LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return False
            link_id, stored_hash, attempts = row
            if attempts >= LOGIN_CODE_MAX_ATTEMPTS:
                return False
            if stored_hash != code_hash:
                cur.execute("UPDATE pelify_magic_links SET attempts = attempts + 1 WHERE id = %s;", (link_id,))
                return False
            cur.execute("UPDATE pelify_magic_links SET used_at = now() WHERE id = %s;", (link_id,))
            return True
    except Exception as e:
        print(f"⚠️ users_db.verify_login_code KO ({e})", flush=True)
        return False


def get_user(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, email, stripe_customer_id, created_at FROM pelify_users WHERE id = %s;", (user_id,))
            return cur.fetchone()
    except Exception as e:
        print(f"⚠️ users_db.get_user KO ({e})", flush=True)
        return None


def set_stripe_customer_id(user_id: int, customer_id: str) -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE pelify_users SET stripe_customer_id = %s WHERE id = %s;", (customer_id, user_id))
    except Exception as e:
        print(f"⚠️ users_db.set_stripe_customer_id KO ({e})", flush=True)


def get_user_by_stripe_customer(customer_id: str) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, email FROM pelify_users WHERE stripe_customer_id = %s;", (customer_id,))
            return cur.fetchone()
    except Exception as e:
        print(f"⚠️ users_db.get_user_by_stripe_customer KO ({e})", flush=True)
        return None


# ────────────────────────────────────────────────────────────────
# Sessions
# ────────────────────────────────────────────────────────────────

def create_session(user_id: int, ip: str) -> Optional[str]:
    conn = _get_conn()
    if not conn:
        return None
    token = _new_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pelify_sessions (user_id, token_hash, ip, expires_at) VALUES (%s, %s, %s, %s);",
                (user_id, _hash_token(token), ip, expires_at),
            )
        return token
    except Exception as e:
        print(f"⚠️ users_db.create_session KO, nouvel essai ({e})", flush=True)
        _reset_conn()
        conn = _get_conn(retry=False)
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pelify_sessions (user_id, token_hash, ip, expires_at) VALUES (%s, %s, %s, %s);",
                    (user_id, _hash_token(token), ip, expires_at),
                )
            return token
        except Exception as e2:
            print(f"⚠️ users_db.create_session KO après nouvel essai ({e2})", flush=True)
            return None


def get_user_from_session(token: str) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    token_hash = _hash_token(token)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.stripe_customer_id
                FROM pelify_sessions s
                JOIN pelify_users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.expires_at > now();
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE pelify_sessions SET last_seen_at = now() WHERE token_hash = %s;",
                    (token_hash,),
                )
            return row
    except Exception as e:
        # La connexion a pu mourir entre deux requêtes (Neon qui se
        # rendort, coupure réseau...) — on force une reconnexion et on
        # retente UNE fois avant de conclure "session introuvable", pour
        # ne pas déconnecter quelqu'un dont la session est en réalité
        # parfaitement valide.
        print(f"⚠️ users_db.get_user_from_session KO, nouvel essai ({e})", flush=True)
        _reset_conn()
        conn = _get_conn(retry=False)
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT u.id, u.email, u.stripe_customer_id
                    FROM pelify_sessions s
                    JOIN pelify_users u ON u.id = s.user_id
                    WHERE s.token_hash = %s AND s.expires_at > now();
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE pelify_sessions SET last_seen_at = now() WHERE token_hash = %s;",
                        (token_hash,),
                    )
                return row
        except Exception as e2:
            print(f"⚠️ users_db.get_user_from_session KO après nouvel essai ({e2})", flush=True)
            return None


def delete_session(token: str) -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pelify_sessions WHERE token_hash = %s;", (_hash_token(token),))
    except Exception as e:
        print(f"⚠️ users_db.delete_session KO ({e})", flush=True)


# ────────────────────────────────────────────────────────────────
# Abonnements
# ────────────────────────────────────────────────────────────────

def upsert_subscription(user_id: int, stripe_subscription_id: str, status: str,
                         current_period_end: Optional[datetime]) -> None:
    conn = _get_conn()
    if not conn:
        raise RuntimeError("Neon indisponible : impossible d'enregistrer l'abonnement")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pelify_subscriptions (user_id, stripe_subscription_id, status, current_period_end, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (user_id) DO UPDATE SET
                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                status = EXCLUDED.status,
                current_period_end = EXCLUDED.current_period_end,
                updated_at = now();
            """,
            (user_id, stripe_subscription_id, status, current_period_end),
        )


def get_subscription(user_id: int) -> Optional[dict]:
    """
    Retourne l'abonnement complet de l'utilisateur.

    Retourne None si aucun abonnement n'existe ou si Neon
    est momentanément indisponible.
    """
    conn = _get_conn()
    if not conn:
        return None

    try:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT
                    user_id,
                    stripe_subscription_id,
                    status,
                    current_period_end,
                    updated_at
                FROM pelify_subscriptions
                WHERE user_id = %s
                LIMIT 1;
                """,
                (user_id,),
            )

            return cur.fetchone()

    except Exception as e:
        print(
            f"⚠️ users_db.get_subscription KO ({e})",
            flush=True,
        )
        return None


def is_subscription_active(user_id: int) -> bool:
    """
    Vérifie si l'utilisateur possède actuellement un abonnement
    Stripe actif ou en période d'essai.

    Les statuts acceptés sont :
      - active
      - trialing

    current_period_end est également contrôlé lorsqu'il existe.
    """

    subscription = get_subscription(user_id)

    if not subscription:
        return False

    status = subscription.get("status")

    if status not in ("active", "trialing"):
        return False

    current_period_end = subscription.get(
        "current_period_end"
    )

    if current_period_end:
        now = datetime.now(timezone.utc)

        if current_period_end < now:
            return False

    return True


# ────────────────────────────────────────────────────────────────
# Quota gratuit — compté PAR COMPTE (email), pas par IP.
#
# Historique : la V1 comptait par IP, mais plusieurs utilisateurs
# derrière un même WiFi/box (IP partagée, CGNAT) se retrouvaient à
# partager le même quota — un client bloquait l'essai gratuit de
# tous les autres sur le même réseau. Le quota est donc maintenant
# rattaché au compte (user_id / email), pas à l'IP.
# ────────────────────────────────────────────────────────────────

def check_and_consume_user_quota(user_id: int) -> bool:
    """
    Retourne True si l'essai gratuit du jour est consommé avec succès pour
    ce compte, False si le quota du jour est déjà atteint.
    Fail-open si Neon est down (on ne veut pas casser le produit pour
    un abonné potentiel à cause d'une panne DB) — à surveiller si Neon
    est instable, car fail-open ici veut dire "laisser passer".
    """
    conn = _get_conn()
    if not conn:
        return True
    today = datetime.now(timezone.utc).date()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pelify_usage (user_id, used_on, count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, used_on) DO UPDATE SET count = pelify_usage.count + 1
                    WHERE pelify_usage.count < %s
                RETURNING count;
                """,
                (user_id, today, FREE_TRIALS_PER_DAY),
            )
            row = cur.fetchone()
            return row is not None
    except Exception as e:
        print(f"⚠️ users_db.check_and_consume_user_quota KO ({e})", flush=True)
        return True


# ────────────────────────────────────────────────────────────────
# Ancien quota par IP — conservé mais NON utilisé par défaut pour le
# gating (cf. décision produit ci-dessus). Laissé disponible si tu
# veux un jour combiner IP + email (ex: anti-abus multi-comptes),
# mais ce n'est plus ce qui bloque l'essai gratuit aujourd'hui.
# ────────────────────────────────────────────────────────────────

def check_and_consume_free_quota(ip: str) -> bool:
    conn = _get_conn()
    if not conn:
        return True
    today = datetime.now(timezone.utc).date()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pelify_ip_usage (ip, used_on, count)
                VALUES (%s, %s, 1)
                ON CONFLICT (ip, used_on) DO UPDATE SET count = pelify_ip_usage.count + 1
                    WHERE pelify_ip_usage.count < %s
                RETURNING count;
                """,
                (ip, today, FREE_TRIALS_PER_DAY),
            )
            row = cur.fetchone()
            return row is not None
    except Exception as e:
        print(f"⚠️ users_db.check_and_consume_free_quota KO ({e})", flush=True)
        return True