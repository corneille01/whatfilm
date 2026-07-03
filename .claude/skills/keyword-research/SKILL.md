---
name: keyword-research
description: Recherche de mots-clés SEO avec estimation de volume, difficulté et opportunités. Utiliser quand l'utilisateur demande "quels mots-clés cibler", "recherche de mots-clés", "keyword research", ou veut prioriser des sujets/pages pour le SEO. Sans clé API DataForSEO/Ahrefs/Semrush configurée, s'appuie sur WebSearch et le jugement éditorial plutôt que sur des données de volume exactes.
---

# Keyword Research

Objectif : produire une liste de mots-clés priorisés (volume estimé, difficulté estimée, intention, opportunité) pour orienter du contenu ou des pages produit.

## Étape 0 — Vérifier l'accès aux données

Cherche une clé API dans l'environnement ou la config du projet (`DATAFORSEO_*`, `AHREFS_*`, `SEMRUSH_*` dans `.env`, `config/`, variables d'environnement). Si une clé existe, utilise l'API correspondante pour des chiffres précis (volume de recherche, CPC, difficulté).

S'il n'y a **aucune** clé disponible, dis-le explicitement à l'utilisateur avant de commencer, puis passe en mode estimation manuelle (voir ci-dessous). Ne jamais inventer des chiffres précis (ex. "12 400 recherches/mois") sans source — utilise des fourchettes qualitatives (faible/moyen/élevé) et indique la méthode.

## Étape 1 — Cadrer la recherche

Demande ou déduis du contexte :
- Le domaine/produit concerné (pour whatfilm : lieux de tournage, films, séries, localisation de scènes)
- La langue et le marché cible (France, francophonie, international ?)
- L'objectif (trafic organique, conversion, notoriété)

## Étape 2 — Générer les candidats

1. Mots-clés de tête ("seed keywords") à partir des pages/fonctionnalités existantes du produit.
2. Variations : questions ("où a été tourné...", "quel est le lieu de tournage de..."), longue traîne, synonymes, entités (titres de films, noms de lieux, réalisateurs).
3. Utilise WebSearch pour observer les suggestions "autocomplete-like", les "recherches associées", et les PAA (People Also Ask) visibles dans les résultats.
4. Regarde ce que couvrent 3-5 concurrents directs (cf. skill `competitor-analysis` si une analyse plus poussée est nécessaire).

## Étape 3 — Qualifier chaque mot-clé

Pour chaque mot-clé, estime :
- **Intention** : informationnelle / navigationnelle / transactionnelle
- **Volume estimé** (fourchette qualitative si pas d'API : très faible / faible / moyen / élevé, en te basant sur la spécificité et la popularité du sujet)
- **Difficulté estimée** : regarde qui se positionne déjà (grands médias/plateformes établies = difficile ; blogs de niche/forums = accessible)
- **Pertinence produit** : le mot-clé correspond-il à une page qui existe ou pourrait exister ?

## Étape 4 — Prioriser

Classe les mots-clés par opportunité = pertinence élevée + difficulté gérable + intention alignée avec l'objectif. Présente sous forme de tableau :

| Mot-clé | Intention | Volume estimé | Difficulté estimée | Page cible / à créer | Priorité |
|---|---|---|---|---|---|

## Limites à rappeler à l'utilisateur

- Sans API de données SEO, les volumes/difficultés sont des estimations qualitatives, pas des chiffres mesurés.
- Pour des données fiables (volume réel, CPC, SERP features), recommander de connecter une clé DataForSEO/Ahrefs/Semrush si le besoin devient récurrent.
