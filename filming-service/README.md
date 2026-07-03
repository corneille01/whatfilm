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

Identifiants reçus : utilisateur `ehoudb_user`, accès via phpMyAdmin sur
`https://109.238.12.189:8443/phpMyAdmin/`. Toujours manquant pour
construire `DATABASE_URL` :
- le **nom de la base** (visible dans phpMyAdmin, colonne de gauche)
- confirmation du **port MySQL réel** (souvent 3306 — le 8443 vu dans
  l'URL est celui de l'interface web phpMyAdmin, pas forcément celui du
  serveur MySQL lui-même)
- confirmation que le serveur accepte les connexions **distantes**
  (beaucoup d'hébergeurs mutualisés/universitaires limitent MySQL à
  `localhost`, auquel cas Render ne pourra jamais s'y connecter
  directement sans un tunnel ou un accès étendu par l'administrateur)

Ce sandbox de développement ne peut pas tester la connectivité réseau
vers `109.238.12.189` (ports 3306 et 8443 injoignables, même politique
réseau que pour Wikidata) — à valider en local ou depuis Render une fois
ces informations connues.

Une fois `DATABASE_URL` connue (localement dans `.env`, jamais commitée),
appliquer le schéma :
```bash
mysql -h HOST -P PORT -u ehoudb_user -p NOM_DE_LA_BASE < sql/schema.sql
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
