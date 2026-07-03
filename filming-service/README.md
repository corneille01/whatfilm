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
- Toutes les tables préfixées `filming_pelify_` (schéma SQL + modèles
  SQLAlchemy) comme demandé pour la base universitaire partagée.
- `.env.example` (aucun secret dedans, `.env` reste ignoré par git).

Pas encore fait :
- **Appliquer réellement `sql/schema.sql` sur la base** et connecter
  `DATABASE_URL` — voir "Connexion DB" ci-dessous, il manque le nom de
  la base et la confirmation du port MySQL.
- Chargeur `scripts/load_wikidata_to_mysql.py` qui lira les fichiers de
  `scripts/output/wikidata_raw/` et peuplera `filming_pelify_movies` /
  `filming_pelify_filming_locations`.
- Frontend Leaflet (panneau latéral + carte, filtres, popups commodités,
  "créer un itinéraire").
- Config Render effective (service à créer, variables d'environnement
  à définir : `DATABASE_URL`, `FILMING_ADMIN_TOKEN`,
  `CORS_ALLOWED_ORIGINS`).
- Tableau de bord ciné-tourisme (§14 du cahier des charges).

## Connexion DB

- Utilisateur : `ehoudb_user`
- Base : `ehou_db`
- Port MySQL : `3306`
- Host : **à confirmer**. `localhost:3306` tel que communiqué n'est
  probablement valable que depuis le serveur lui-même (ex: phpMyAdmin,
  qui tourne sur la même machine que MySQL). Pour que Render (un service
  hébergé ailleurs) puisse s'y connecter, il faut l'IP publique
  `109.238.12.189` **et** que MySQL accepte les connexions distantes
  dessus (pas juste `127.0.0.1`/`localhost` en interne).

Ce sandbox de développement ne peut pas tester la connectivité réseau
vers `109.238.12.189` (port 3306 injoignable, même politique réseau que
pour Wikidata) — à valider en local (un client MySQL sur ton PC pointant
vers l'IP publique) ou depuis Render une fois déployé.

**Appliquer le schéma** — le plus simple et le plus sûr avec ce qu'on a
confirmé marcher (accès phpMyAdmin) :
1. Ouvrir `https://109.238.12.189:8443/phpMyAdmin/`, sélectionner la base `ehou_db`
2. Onglet **Importer** → choisir `filming-service/sql/schema.sql` → Exécuter

Alternative en ligne de commande (si accès SSH/mysql direct au serveur) :
```bash
mysql -h HOST -P 3306 -u ehoudb_user -p ehou_db < sql/schema.sql
```

## Blocage historique (résolu)

Ce repo n'avait au départ **aucun accès MySQL direct** : `storage/university_client.py`
(app principale) ne parle qu'à un proxy HTTP PHP limité à 2 endpoints
(`cache`, `embeddings`) — pas de SQL arbitraire. Des identifiants MySQL
directs ont depuis été fournis (cf. section "Connexion DB" ci-dessus).

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
