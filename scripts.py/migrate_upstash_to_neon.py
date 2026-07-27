#!/usr/bin/env python3
"""
scripts/migrate_upstash_to_neon.py
Recopie toutes les clés existantes d'Upstash (url:*, film:*, title:*,
content:*, ...) vers la nouvelle table kv_store dans Neon.

Prérequis (variables d'environnement) :
  UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN  — source
  NEON_DATABASE_URL (ou DATABASE_URL)                — destination

⚠️ Ton quota Upstash REST est actuellement épuisé (500000/500000 vu
dans les logs). Ce script consomme 2 commandes Upstash par clé (GET +
TTL) plus quelques SCAN — attends que le quota se réinitialise (mensuel,
voir le dashboard Upstash pour la date exacte) avant de le lancer, sinon
il échouera aux mêmes erreurs "max requests limit exceeded".

Reprise : le script saute les clés déjà présentes dans Neon, donc il est
sûr de le relancer plusieurs fois (ex: si le quota Upstash s'épuise en
cours de route un jour donné, on relance le lendemain).

Usage :
    python scripts/migrate_upstash_to_neon.py            # migration réelle
    python scripts/migrate_upstash_to_neon.py --dry-run   # simulation, aucune écriture
    python scripts/migrate_upstash_to_neon.py --limit 500 # s'arrête après 500 clés (test)
"""

import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upstash_redis import Redis as UpstashRedis
from storage.cache_engine.redis_client import NeonKV, NEON_DATABASE_URL

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# Pause entre chaque clé pour ne pas marteler l'API REST Upstash (déjà
# fragile sur le quota gratuit) ni Neon.
SLEEP_BETWEEN_KEYS = 0.05


def already_in_neon(neon: NeonKV, key: str) -> bool:
    try:
        return neon.get(key) is not None
    except Exception:
        return False


def migrate(dry_run: bool, limit: int | None):
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        print("❌ UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN manquants.")
        sys.exit(1)

    if not NEON_DATABASE_URL:
        print("❌ NEON_DATABASE_URL (ou DATABASE_URL) manquant.")
        sys.exit(1)

    upstash = UpstashRedis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
    neon = NeonKV(NEON_DATABASE_URL)

    print("🔎 Scan des clés Upstash...")

    cursor = 0
    total_seen = 0
    total_migrated = 0
    total_skipped = 0
    total_errors = 0

    while True:
        try:
            cursor, batch = upstash.scan(cursor, match="*", count=200)
        except Exception as e:
            print(f"❌ Erreur SCAN Upstash : {e}")
            print("   → quota probablement toujours épuisé, relance ce script plus tard.")
            break

        for key in batch:
            total_seen += 1

            if limit and total_migrated >= limit:
                print(f"⏹️  Limite de {limit} clés migrées atteinte, arrêt.")
                _print_summary(total_seen, total_migrated, total_skipped, total_errors)
                return

            if already_in_neon(neon, key):
                total_skipped += 1
                continue

            try:
                value = upstash.get(key)
                if value is None:
                    total_skipped += 1
                    continue

                ttl = upstash.ttl(key)  # -1 = jamais expire, -2 = clé absente
                ex = ttl if ttl and ttl > 0 else None

                if dry_run:
                    print(f"[dry-run] {key} (ttl={ttl})")
                else:
                    neon.set(key, value, ex=ex)

                total_migrated += 1

                if total_migrated % 50 == 0:
                    print(f"  ... {total_migrated} clés migrées (sur {total_seen} vues)")

            except Exception as e:
                total_errors += 1
                print(f"⚠️ Erreur sur la clé {key} : {e}")

            time.sleep(SLEEP_BETWEEN_KEYS)

        if cursor == 0:
            break

    _print_summary(total_seen, total_migrated, total_skipped, total_errors)


def _print_summary(seen, migrated, skipped, errors):
    print("\n Migration terminée.")
    print(f"   Clés vues      : {seen}")
    print(f"   Migrées        : {migrated}")
    print(f"   Ignorées (déjà présentes / vides) : {skipped}")
    print(f"   Erreurs        : {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Simule sans écrire dans Neon")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de clés à migrer")
    args = parser.parse_args()

    migrate(dry_run=args.dry_run, limit=args.limit)