# filming-service — plateforme ciné-tourisme (pelify.app)

Service séparé de l'app principale `pelify.app`, destiné à être déployé
indépendamment sur Render. Accessible depuis pelify.app via le bouton
"Lieux de tournage" (route `/lieux-de-tournage`), qui appelle l'API de ce
service en cross-origin.

## État actuel

Fait :
- `sql/schema.sql` — schéma MySQL complet (movies, filming_locations,
  nearby_places, location_nearby_cache, api_jobs, analytics_events),
  avec colonne `geom POINT SRID 4326` prête pour une migration future
  vers PostGIS.
- `scripts/fetch_wikidata.py` — récupération Wikidata (films + séries
  séparés, 1800-2026, découpé en tranches d'années pour éviter les
  timeouts, inclut les images via P18). **Non testé en direct dans cette
  session** : le sandbox bloque les connexions sortantes vers
  `query.wikidata.org` (403 policy denial côté proxy). À lancer en local
  ou depuis Render avant de faire confiance aux résultats.

Pas encore fait (bloqué sur une décision d'accès DB, cf. ci-dessous) :
- App FastAPI (`app/`) avec les endpoints `/api/movies`,
  `/api/movies/{id}/locations`, `/api/locations/{id}/nearby`,
  `/api/admin/preload-nearby`, `/api/health`.
- Système de cache-first + file de jobs (table `api_jobs`) pour les
  commodités proches (hébergement, restaurant, transport, office de
  tourisme, activité, + sécurité : police/hôpital).
- Chargeur `scripts/load_wikidata_to_mysql.py` qui lira les fichiers de
  `scripts/output/wikidata_raw/` et peuplera `movies` /
  `filming_locations`.
- Frontend Leaflet (panneau latéral + carte, filtres, popups commodités).
- Dockerfile + config Render pour ce service.

## Blocage à lever avant de continuer

Ce repo n'a **aucun accès MySQL direct** : `storage/university_client.py`
(app principale) ne parle qu'à un proxy HTTP PHP limité à 2 endpoints
(`cache`, `embeddings`) — pas de SQL arbitraire, donc impossible d'y
créer les 6 nouvelles tables telles quelles.

Pour brancher la vraie persistance, il faut soit :
1. des identifiants MySQL directs (host/port/user/password/nom de base)
   pour la base universitaire, soit
2. de nouveaux endpoints côté PHP (hors de ce repo) exposant les
   opérations nécessaires (insert/query sur les 6 tables).

Sans ça, `sql/schema.sql` reste un schéma prêt à appliquer mais aucune
connexion n'est configurée.

## Lancer le fetch Wikidata (à faire hors de ce sandbox)

```bash
cd filming-service/scripts
pip install -r ../requirements.txt
python fetch_wikidata.py --from 1800 --to 2026   # tout, films + séries
python fetch_wikidata.py --from 2020 --to 2021 --type film  # test rapide
```

Chaque tranche d'années est écrite dans
`scripts/output/wikidata_raw/{type}_{annee_debut}_{annee_fin}.json`,
pour pouvoir reprendre sans tout relancer en cas d'échec réseau.
