#!/usr/bin/env python3
"""
build_catalogue_local.py — À lancer EN LOCAL (pas sur Render)

Lance depuis ton PC :  python3 build_catalogue_local.py
Produit :             catalogue_filming.json

Ensuite tu commites ce fichier dans ton repo et filming_catalogue.py
le charge depuis le disque au lieu de requêter Wikidata.
"""

import asyncio
import json
import time
import logging
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
PAGE_SIZE = 500
DELAY = 3.0
TIMEOUT = 60
MAX_PAGES = 30

QUERY = """
SELECT DISTINCT
  ?film ?filmLabel
  ?tmdb_id ?tmdb_tv_id
  ?loc ?locLabel
  ?countryLabel
  ?coord
  ?year
WHERE {{
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}
  OPTIONAL {{ ?film wdt:P4947 ?tmdb_id . }}
  OPTIONAL {{ ?film wdt:P8306 ?tmdb_tv_id . }}
  OPTIONAL {{
    ?film wdt:P577 ?date .
    BIND(YEAR(?date) AS ?year)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
}}
ORDER BY DESC(?year) ?film
LIMIT {limit}
OFFSET {offset}
"""

def parse_coord(s):
    if not s: return None, None
    try:
        inner = s.replace("Point(", "").replace(")", "").strip()
        parts = inner.split()
        if len(parts) == 2:
            lng, lat = float(parts[0]), float(parts[1])
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    except: pass
    return None, None

def wd_id(uri):
    return uri.split("/")[-1] if uri else ""

async def fetch_page(client, offset, retries=3):
    query = QUERY.format(limit=PAGE_SIZE, offset=offset)
    for attempt in range(retries):
        try:
            r = await client.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={
                    "Accept": "application/sparql-results+json",
                    "User-Agent": "ShadowFrame/4.0 (https://quelfilm.app) build-local",
                },
            )
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                logger.warning(f"429 — attente {wait}s")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            bindings = r.json().get("results", {}).get("bindings", [])
            logger.info(f"  offset={offset} → {len(bindings)} lignes")
            return bindings
        except httpx.TimeoutException:
            logger.warning(f"  timeout offset={offset} tentative {attempt+1}")
            await asyncio.sleep(15 * (attempt + 1))
        except Exception as e:
            logger.warning(f"  erreur offset={offset}: {e}")
            await asyncio.sleep(10 * (attempt + 1))
    return []

async def main():
    all_films = {}
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for page_num in range(MAX_PAGES):
            offset = page_num * PAGE_SIZE
            logger.info(f"Page {page_num+1} (offset={offset})...")
            bindings = await fetch_page(client, offset)
            
            if not bindings:
                logger.info("Page vide — fin.")
                break
            
            for row in bindings:
                fid = wd_id(row.get("film", {}).get("value", ""))
                if not fid: continue
                
                label   = row.get("filmLabel",  {}).get("value", "")
                tid_raw = row.get("tmdb_id",    {}).get("value", "")
                tv_raw  = row.get("tmdb_tv_id", {}).get("value", "")
                yr_raw  = row.get("year",       {}).get("value", "")
                
                tmdb_id = int(tid_raw) if tid_raw and tid_raw.isdigit() else None
                mtype = "movie"
                if tv_raw and tv_raw.isdigit():
                    tmdb_id = int(tv_raw)
                    mtype = "tv"
                
                if fid not in all_films:
                    all_films[fid] = {
                        "wikidata_id": fid,
                        "title": label or fid,
                        "tmdb_id": tmdb_id,
                        "media_type": mtype,
                        "year": int(yr_raw) if yr_raw and yr_raw.isdigit() else None,
                        "locations": [],
                    }
                
                lid   = wd_id(row.get("loc", {}).get("value", ""))
                lname = row.get("locLabel", {}).get("value", lid)
                cname = row.get("countryLabel", {}).get("value", "")
                coord = row.get("coord", {}).get("value", "")
                lat, lng = parse_coord(coord)
                
                existing = {l["wikidata_id"] for l in all_films[fid]["locations"]}
                if lid and lid not in existing:
                    all_films[fid]["locations"].append({
                        "wikidata_id": lid,
                        "name": lname,
                        "country": cname,
                        "lat": lat,
                        "lng": lng,
                    })
            
            logger.info(f"  Total films: {len(all_films)}")
            
            if len(bindings) < PAGE_SIZE:
                logger.info("Dernière page atteinte.")
                break
            
            await asyncio.sleep(DELAY)
    
    # Construire le catalogue final
    catalogue = []
    for f in all_films.values():
        locs = f["locations"]
        gps = [l for l in locs if l.get("lat") is not None]
        best = gps[0] if gps else (locs[0] if locs else None)
        countries = sorted({l["country"] for l in locs if l.get("country")})
        
        catalogue.append({
            "wikidata_id": f["wikidata_id"],
            "title": f["title"],
            "tmdb_id": f["tmdb_id"],
            "media_type": f["media_type"],
            "year": f["year"],
            "poster_path": None,
            "vote_average": None,
            "vote_count": None,
            "location_count": len(locs),
            "countries": countries,
            "_title_lower": f["title"].lower(),
            "_countries_lower": [c.lower() for c in countries],
            "primary_location": {
                "name": best["name"],
                "lat": best["lat"],
                "lng": best["lng"],
                "country": best["country"],
                "wikidata_id": best["wikidata_id"],
            } if best else None,
            "locations": locs,
        })
    
    output = "catalogue_filming.json"
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(catalogue, fh, ensure_ascii=False, indent=2)
    
    logger.info(f"\n✅ TERMINÉ — {len(catalogue)} films → {output}")
    logger.info(f"Taille fichier : {len(json.dumps(catalogue)) / 1024 / 1024:.1f} MB")

asyncio.run(main())