"""
app/db.py — Connexion SQLAlchemy vers MySQL.

Tant que DATABASE_URL n'est pas définie (identifiants MySQL manquants),
`engine` est None et get_session() lève une erreur explicite plutôt que de
planter au démarrage — permet à l'app de démarrer (ex: /api/health répond)
même sans base configurée.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600) if DATABASE_URL else None
# expire_on_commit=False : les objets renvoyés par un endpoint restent lisibles
# après la fermeture de la session (FastAPI sérialise la réponse après le `with`,
# donc une fois la session déjà commit/close — sans ça, DetachedInstanceError).
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False) if engine else None


@contextmanager
def get_session() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL non configurée — définis la variable d'environnement "
            "DATABASE_URL (ex: mysql+pymysql://user:pass@host:3306/pelify_filming)."
        )
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
