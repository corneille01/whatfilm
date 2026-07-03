"""
fetch_wikidata.py — Récupère films et séries avec lieux de tournage depuis Wikidata (1800-2026).

Découpe la requête en petites tranches d'années (par type film/série séparément)
pour éviter les timeouts du endpoint SPARQL public de Wikidata. Chaque tranche est
écrite dans un fichier JSON séparé sous output/, pour pouvoir reprendre en cas
d'échec sans tout relancer, et pour inspecter les données avant de les charger en base.

Usage:
    python fetch_wikidata.py                # tout (1800-2026, films + séries)
    python fetch_wikidata.py --from 2000 --to 2010 --type film

Un script séparé (load_wikidata_to_mysql.py, à écrire une fois les credentials
MySQL connus) lira les fichiers de output/ pour peupler les tables movies /
filming_locations.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "PelifyFilmingBot/1.0 (https://pelify.app; contact@pelify.app)"

OUTPUT_DIR = Path(__file__).parent / "output" / "wikidata_raw"

TYPE_QIDS = {
    "film": "wd:Q11424",
    "series": "wd:Q5398426",
}

# Tranches d'années : plus larges pour les périodes peu documentées, plus fines
# pour les périodes récentes où la densité de données Wikidata est élevée.
# Une requête SPARQL avec trop d'années d'un coup timeout sur le endpoint public.
def build_year_buckets() -> list[tuple[int, int]]:
    buckets = []
    # 1800-1949 : par décennie (peu de films avec lieu de tournage renseigné)
    for start in range(1800, 1950, 10):
        buckets.append((start, min(start + 10, 1950)))
    # 1950-1999 : par tranche de 5 ans
    for start in range(1950, 2000, 5):
        buckets.append((start, start + 5))
    # 2000-2026 : année par année (forte densité de données)
    for year in range(2000, 2027):
        buckets.append((year, year + 1))
    return buckets


SPARQL_TEMPLATE = """
SELECT
  (STRAFTER(STR(?work), "/entity/") AS ?wikidata_id)
  ?workLabel
  ?release_date
  ?year
  (STRAFTER(STR(?location), "/entity/") AS ?location_id)
  ?locationLabel
  ?cityLabel
  ?filming_countryLabel
  (geof:latitude(?coord) AS ?lat)
  (geof:longitude(?coord) AS ?lng)
  ?image
WHERE {{
  ?work wdt:P31/wdt:P279* {type_qid} ;
        wdt:P915 ?location ;
        wdt:P577 ?release_date .

  BIND(YEAR(?release_date) AS ?year)
  FILTER(?year >= {year_from} && ?year < {year_to})

  ?location wdt:P625 ?coord .
  OPTIONAL {{ ?location wdt:P131 ?city . }}
  OPTIONAL {{ ?location wdt:P17 ?filming_country . }}
  OPTIONAL {{ ?work wdt:P18 ?image . }}

  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "fr,en,[AUTO_LANGUAGE]".
  }}
}}
LIMIT 2000
"""


def fetch_bucket(client: httpx.Client, media_type: str, year_from: int, year_to: int) -> list[dict]:
    query = SPARQL_TEMPLATE.format(
        type_qid=TYPE_QIDS[media_type],
        year_from=year_from,
        year_to=year_to,
    )
    resp = client.get(
        WIKIDATA_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=60.0,
    )
    resp.raise_for_status()
    bindings = resp.json()["results"]["bindings"]

    rows = []
    for b in bindings:
        rows.append({
            "wikidata_id": b.get("wikidata_id", {}).get("value"),
            "title": b.get("workLabel", {}).get("value"),
            "type": media_type,
            "release_date": b.get("release_date", {}).get("value"),
            "year": int(b["year"]["value"]) if "year" in b else None,
            "location_wikidata_id": b.get("location_id", {}).get("value"),
            "location_name": b.get("locationLabel", {}).get("value"),
            "city": b.get("cityLabel", {}).get("value"),
            "country": b.get("filming_countryLabel", {}).get("value"),
            "lat": float(b["lat"]["value"]) if "lat" in b else None,
            "lng": float(b["lng"]["value"]) if "lng" in b else None,
            "image_url": b.get("image", {}).get("value"),
        })
    return rows


def fetch_all(media_types: list[str], year_from: int, year_to: int, delay: float = 1.5) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    buckets = [b for b in build_year_buckets() if b[0] >= year_from and b[1] <= year_to + 1]

    total_rows = 0
    with httpx.Client() as client:
        for media_type in media_types:
            for (start, end) in buckets:
                out_file = OUTPUT_DIR / f"{media_type}_{start}_{end}.json"
                if out_file.exists():
                    print(f"⏭️  {out_file.name} déjà présent, on saute (supprime-le pour re-fetch)")
                    continue

                attempt = 0
                while True:
                    attempt += 1
                    try:
                        rows = fetch_bucket(client, media_type, start, end)
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt <= 5:
                            wait = 5 * attempt
                            print(f"⚠️  429 rate-limited sur {media_type} {start}-{end}, retry dans {wait}s")
                            time.sleep(wait)
                            continue
                        print(f"❌ échec {media_type} {start}-{end}: {e}")
                        rows = []
                        break
                    except Exception as e:
                        print(f"❌ échec {media_type} {start}-{end}: {e}")
                        rows = []
                        break

                out_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                total_rows += len(rows)
                print(f"✅ {media_type} {start}-{end}: {len(rows)} lignes → {out_file.name}")
                time.sleep(delay)  # politesse envers le endpoint public Wikidata

    print(f"\nTerminé. {total_rows} lignes récupérées au total dans {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="year_from", type=int, default=1800)
    parser.add_argument("--to", dest="year_to", type=int, default=2026)
    parser.add_argument("--type", dest="media_type", choices=["film", "series", "both"], default="both")
    parser.add_argument("--delay", type=float, default=1.5, help="secondes entre chaque requête")
    args = parser.parse_args()

    types = ["film", "series"] if args.media_type == "both" else [args.media_type]
    fetch_all(types, args.year_from, args.year_to, args.delay)
