#!/usr/bin/env python3
import json
import logging
import httpx
import asyncio
import time
import sys

# Configuration du log
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
PAGE_SIZE = 500
MAX_PAGES = 10  # Commençons par 10 pages pour tester

# La requête SPARQL est définie en texte brut sans accolades de formatage Python
QUERY_TEMPLATE = """
SELECT DISTINCT ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?countryLabel ?cityLabel ?coord ?year WHERE {
  VALUES ?type { wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }
  ?film wdt:P31 ?type ; wdt:P915 ?loc .
  OPTIONAL { ?loc wdt:P625 ?coord . }
  OPTIONAL { ?loc wdt:P17 ?country . ?country rdfs:label ?countryLabel . FILTER(LANG(?countryLabel) = "fr") }
  OPTIONAL { ?loc wdt:P131 ?city . ?city rdfs:label ?cityLabel . FILTER(LANG(?cityLabel) = "fr") }
  OPTIONAL { ?film wdt:P4947 ?tmdb_id . }
  OPTIONAL { ?film wdt:P8306 ?tmdb_tv_id . }
  OPTIONAL { ?film wdt:P577 ?date . BIND(YEAR(?date) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en" . }
}
ORDER BY ?film
LIMIT %LIMIT%
OFFSET %OFFSET%
"""

def parse_coord(s):
    if not s: return None, None
    try:
        inner = s.replace("Point(", "").replace(")", "").strip()
        parts = inner.split()
        if len(parts) == 2: return float(parts[1]), float(parts[0]) # lat, lng
    except: pass
    return None, None

async def fetch_page(client, offset):
    # On remplace manuellement sans utiliser .format()
    q = QUERY_TEMPLATE.replace("%LIMIT%", str(PAGE_SIZE)).replace("%OFFSET%", str(offset))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/sparql-results+json"
    }
    try:
        r = await client.get(WIKIDATA_SPARQL, params={"query": q, "format": "json"}, headers=headers)
        if r.status_code == 403:
            logger.error("🚫 ACCÈS REFUSÉ (403). Wikidata bloque votre IP.")
            return None
        r.raise_for_status()
        return r.json().get("results", {}).get("bindings", [])
    except Exception as e:
        logger.error(f"Erreur offset {offset}: {e}")
        return []

async def main():
    all_films = {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        for page_num in range(MAX_PAGES):
            offset = page_num * PAGE_SIZE
            logger.info(f"--- Récupération page {page_num + 1} (Offset {offset}) ---")
            
            bindings = await fetch_page(client, offset)
            if bindings is None: break # Erreur fatale
            if not bindings: break # Fin des résultats
            
            for row in bindings:
                fid = row.get("film", {}).get("value", "").split("/")[-1]
                if not fid: continue
                
                if fid not in all_films:
                    tid = row.get("tmdb_id", {}).get("value", "")
                    tv = row.get("tmdb_tv_id", {}).get("value", "")
                    all_films[fid] = {
                        "wikidata_id": fid,
                        "title": row.get("filmLabel", {}).get("value", fid),
                        "tmdb_id": int(tid or tv) if (tid or tv) else None,
                        "media_type": "series" if tv else "movie",
                        "year": int(row.get("year", {}).get("value", 0)) or None,
                        "locations": [],
                    }
                
                lid = row.get("loc", {}).get("value", "").split("/")[-1]
                if lid:
                    lat, lng = parse_coord(row.get("coord", {}).get("value", ""))
                    all_films[fid]["locations"].append({
                        "wikidata_id": lid,
                        "name": row.get("locLabel", {}).get("value", "Inconnu"),
                        "city": row.get("cityLabel", {}).get("value", "Non spécifié"),
                        "country": row.get("countryLabel", {}).get("value", "Inconnu"),
                        "lat": lat,
                        "lng": lng,
                    })
            
            time.sleep(5) # Pause très importante pour ne pas être banni

    # Construction finale
    catalogue = []
    for f in all_films.values():
        locs = f["locations"]
        best = locs[0] if locs else None
        catalogue.append({**f, "location_count": len(locs), "primary_location": best})
    
    with open("catalogue_filming.json", "w", encoding="utf-8") as fh:
        json.dump(catalogue, fh, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ Terminé ! {len(catalogue)} films enregistrés.")

if __name__ == "__main__":
    asyncio.run(main())