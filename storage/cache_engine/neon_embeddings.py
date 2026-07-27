# storage/cache_engine/neon_embeddings.py
#
# Recherche par similarité sémantique (texte) pour identifier un film déjà
# connu AVANT d'appeler Gemini/Qwen/Groq — même logique que
# core/embeddings_engine.py visait à faire via la base MySQL université,
# mais ici :
#   - le stockage/la recherche vectorielle se fait dans Neon (pgvector),
#     la même base Postgres que storage/cache_engine/redis_client.py ;
#   - les embeddings sont générés via l'API Gemini (gemini-embedding-001),
#     et non via sentence-transformers en local — qui ne tourne pas sur
#     Render Free (512 Mo de RAM, cf. commentaires historiques du repo).
#
# Ce module ne lève jamais d'exception vers l'appelant : toute erreur
# (Neon indisponible, Gemini en panne, texte trop court) donne un retour
# vide/None, pour que le pipeline principal bascule simplement sur les
# LLM comme si ce module n'existait pas.
#
# Variables d'environnement :
#   NEON_DATABASE_URL / DATABASE_URL — déjà utilisées par redis_client.py
#   GEMINI_API_KEY                   — déjà utilisée par core/extraction.py

import os
import time
import asyncio
from typing import Optional, List, Dict, Any

import httpx
import psycopg2

NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768  # output_dimensionality réduit : moins de stockage/CPU, largement suffisant pour ce cas d'usage
EMBEDDING_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"

_conn = None
_schema_ready = False


def _get_conn():
    """Connexion Postgres paresseuse, reconnectée automatiquement si coupée."""
    global _conn
    try:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(NEON_DATABASE_URL, connect_timeout=5)
            _conn.autocommit = True
    except Exception as e:
        print(f"⚠️ neon_embeddings: connexion KO ({e})", flush=True)
        _conn = None
    return _conn


def _ensure_schema() -> bool:
    global _schema_ready
    if _schema_ready:
        return True

    conn = _get_conn()
    if not conn:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS film_text_embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    tmdb_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'movie',
                    lang TEXT NOT NULL DEFAULT 'fr',
                    excerpt TEXT,
                    embedding VECTOR({EMBEDDING_DIM}) NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_film_text_embeddings_tmdb "
                "ON film_text_embeddings (tmdb_id)"
            )
            # ivfflat : index approximatif, se construit même sur une table
            # vide et s'améliore avec le volume de données. À défaut de
            # pgvector (extension non disponible sur ce projet Neon), on
            # continue sans index — la recherche reste correcte, juste
            # moins rapide (scan séquentiel), largement suffisant tant
            # que la table reste de l'ordre de quelques dizaines de
            # milliers de lignes.
            try:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_film_text_embeddings_vec "
                    "ON film_text_embeddings USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            except Exception as e:
                print(f"ℹ️ neon_embeddings: index ivfflat non créé ({str(e)[:120]})", flush=True)

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_match_log (
                    id BIGSERIAL PRIMARY KEY,
                    query_type TEXT NOT NULL,
                    similarity_score DOUBLE PRECISION,
                    threshold_used DOUBLE PRECISION,
                    accepted BOOLEAN,
                    matched_tmdb_id INTEGER,
                    fallback_to_llm BOOLEAN,
                    created_at DOUBLE PRECISION NOT NULL
                )
                """
            )

        _schema_ready = True
        print("✅ Neon Postgres (embeddings pgvector) schéma prêt", flush=True)
        return True

    except Exception as e:
        print(f"⚠️ neon_embeddings: schéma KO ({e})", flush=True)
        return False


def _vector_literal(embedding: List[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


# ═══════════════════════════ GÉNÉRATION (GEMINI) ═══════════════════════════

async def generate_text_embedding(text: str) -> Optional[List[float]]:
    """
    Génère un embedding texte via l'API Gemini. Ne lève jamais
    d'exception : retourne None si la clé API manque, si le texte est
    vide, ou en cas d'erreur réseau/API.
    """
    text = (text or "").strip()
    if not text or not GEMINI_API_KEY:
        return None

    truncated = text[:2000]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{EMBEDDING_URL}?key={GEMINI_API_KEY}",
                json={
                    "content": {"parts": [{"text": truncated}]},
                    "outputDimensionality": EMBEDDING_DIM,
                },
            )
            if resp.status_code != 200:
                print(f"⚠️ Gemini embedding HTTP {resp.status_code}: {resp.text[:150]}", flush=True)
                return None

            data = resp.json()
            values = data.get("embedding", {}).get("values")
            return values if values else None

    except Exception as e:
        print(f"⚠️ Gemini embedding exception: {str(e)[:120]}", flush=True)
        return None


# ═══════════════════════════ STOCKAGE / RECHERCHE (NEON) ═══════════════════════════

def _insert_sync(tmdb_id: int, embedding: List[float], media_type: str, lang: str, excerpt: Optional[str]) -> bool:
    if not _ensure_schema():
        return False

    conn = _get_conn()
    if not conn:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO film_text_embeddings (tmdb_id, media_type, lang, excerpt, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                """,
                (tmdb_id, media_type, lang, (excerpt or "")[:500], _vector_literal(embedding), time.time()),
            )
        return True
    except Exception as e:
        print(f"⚠️ neon_embeddings insert KO: {str(e)[:150]}", flush=True)
        return False


def _search_sync(embedding: List[float], top_k: int, threshold: float) -> List[Dict[str, Any]]:
    if not _ensure_schema():
        return []

    conn = _get_conn()
    if not conn:
        return []

    try:
        vec = _vector_literal(embedding)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT tmdb_id, media_type, lang, 1 - (embedding <=> %s::vector) AS score
                FROM film_text_embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, vec, top_k),
            )
            rows = cur.fetchall()

        return [
            {"tmdb_id": tmdb_id, "media_type": media_type, "lang": lang, "score": float(score)}
            for tmdb_id, media_type, lang, score in rows
            if score >= threshold
        ]
    except Exception as e:
        print(f"⚠️ neon_embeddings search KO: {str(e)[:150]}", flush=True)
        return []


def _log_match_sync(
    query_type: str,
    similarity_score: float,
    threshold_used: float,
    accepted: bool,
    matched_tmdb_id: Optional[int],
    fallback_to_llm: bool,
) -> None:
    if not _ensure_schema():
        return

    conn = _get_conn()
    if not conn:
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO embedding_match_log
                    (query_type, similarity_score, threshold_used, accepted, matched_tmdb_id, fallback_to_llm, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (query_type, similarity_score, threshold_used, accepted, matched_tmdb_id, fallback_to_llm, time.time()),
            )
    except Exception:
        pass  # log non-critique, jamais bloquant


async def neon_insert_text_embedding(
    tmdb_id: int,
    embedding: List[float],
    media_type: str = "movie",
    lang: str = "fr",
    excerpt: Optional[str] = None,
) -> bool:
    return await asyncio.to_thread(_insert_sync, tmdb_id, embedding, media_type, lang, excerpt)


async def neon_search_text_embeddings(
    embedding: List[float],
    top_k: int = 5,
    threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_search_sync, embedding, top_k, threshold)


async def neon_log_match(
    query_type: str,
    similarity_score: float,
    threshold_used: float,
    accepted: bool,
    matched_tmdb_id: Optional[int] = None,
    fallback_to_llm: bool = False,
) -> None:
    await asyncio.to_thread(
        _log_match_sync, query_type, similarity_score, threshold_used, accepted, matched_tmdb_id, fallback_to_llm
    )