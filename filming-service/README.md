# filming-service — plateforme ciné-tourisme (pelify.app)

Service séparé de l'app principale `pelify.app`, destiné à être déployé
indépendamment sur Render. Accessible depuis pelify.app via le bouton
"Lieux de tournage" en page d'accueil, qui **redirige** (nouvel onglet)
vers l'URL de ce service — pas d'appel API cross-origin depuis le
frontend whatfilm, l'UI carte/Leaflet vit entièrement ici (décision
d'architecture : lien simple, pas de proxy serveur).

⚠️ Le bouton pointe vers `FILMING_SERVICE_URL` dans
`frontend/script.js` (whatfilm), actuellement un placeholder
(`https://lieux.pelify.app`). **Ne pas déployer ce changement en
production avant que ce service soit réellement en ligne à cette URL**,
sinon le bouton casse pour les visiteurs actuels.

## État actuel

Fait :
- `sql/schema.sql` — schéma MySQL complet (movies, filming_locations,
  nearby_places, location_nearby_cache, api_jobs, analytics_events),
  avec colonne `geom POINT SRID 4326` prête pour une migration future
  vers PostGIS.
- `scripts/fetch_wikidata.py` — récupération Wikidata (films + séries
  séparés, 1800-2026, découpé en tranches d'années pour éviter les
  timeouts, inclut les images via P18). **Non testé en direct** : le
  sandbox de développement bloque les connexions sortantes vers
  `query.wikidata.org` (403 policy denial côté proxy réseau). À lancer
  en local ou depuis Render avant de faire confiance aux résultats.
- App FastAPI (`app/`) — endpoints `/api/health`, `/api/movies`,
  `/api/movies/{id}/locations`, `/api/locations/{id}/nearby`,
  `/api/admin/preload-nearby` (protégé par `FILMING_ADMIN_TOKEN`).
  Testée avec succès contre une base SQLite locale (démarre aussi sans
  DB configurée, `/api/health` répond, le reste renvoie 503 explicite).
- Cache-first sur les commodités proches (`app/nearby_service.py`) :
  lecture cache → job créé si absent (contrainte UNIQUE = jamais 2 jobs
  actifs pour le même lieu) → réponse `processing` immédiate → le
  vrai travail (appel Overpass/OSM, catégories accommodation/
  restaurant/transport/tourism_office/activity/**safety** [police,
  hôpital, pharmacie]) tourne en tâche de fond FastAPI, avec un
  rate-limiter (20 appels/min par défaut) et une escalade de rayon
  5km → 15km → 30km. **Logique testée avec un cache simulé en local,
  pas d'appel Overpass réel effectué** (même contrainte réseau que
  Wikidata).
- `Dockerfile` prêt pour Render (lit `$PORT` dynamiquement).

Pas encore fait (bloqué sur l'accès DB, cf. ci-dessous) :
- Chargeur `scripts/load_wikidata_to_mysql.py` qui lira les fichiers de
  `scripts/output/wikidata_raw/` et peuplera `movies` /
  `filming_locations`.
- Frontend Leaflet (panneau latéral + carte, filtres, popups commodités,
  "créer un itinéraire").
- Config Render effective (service à créer, variables d'environnement
  à définir : `DATABASE_URL`, `FILMING_ADMIN_TOKEN`,
  `CORS_ALLOWED_ORIGINS`).
- Tableau de bord ciné-tourisme (§14 du cahier des charges).

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
