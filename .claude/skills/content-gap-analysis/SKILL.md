---
name: content-gap-analysis
description: Identifie les sujets/mots-clés que les concurrents couvrent et pas nous, pour trouver les trous dans la stratégie de contenu. Utiliser quand l'utilisateur demande "content gap analysis", "quels sujets on rate", "trous dans notre contenu", ou veut planifier un calendrier éditorial basé sur ce que fait la concurrence.
---

# Content Gap Analysis

Objectif : produire une liste priorisée de sujets/pages manquants par rapport à la concurrence, avec justification et suggestion de format.

Cette skill s'appuie sur `competitor-analysis` et `keyword-research` — les utiliser en amont si une analyse plus large est nécessaire ; ici on se concentre sur le croisement "ce qu'ils ont / ce qu'on a".

## Étape 1 — Cartographier le contenu existant

Liste (ou demande à l'utilisateur de fournir) l'inventaire des pages/contenus du site : catégories, pages piliers, articles de blog. Pour whatfilm, ça inclut typiquement les pages par film, par lieu, par région, les guides thématiques.

## Étape 2 — Cartographier le contenu des concurrents

Pour 3-5 concurrents pertinents, explorer leur structure (via WebFetch/WebSearch) et lister leurs grandes catégories de contenu : quels types de pages ont-ils, quels sujets reviennent souvent, quels formats (listes, guides, comparatifs, contenu généré par les utilisateurs).

## Étape 3 — Croiser

Construis un tableau sujet × présence :

| Sujet / type de page | Nous | Concurrent A | Concurrent B | Concurrent C |
|---|---|---|---|---|

Repère les lignes où les concurrents sont présents et pas nous — ce sont les "gaps".

## Étape 4 — Qualifier chaque gap

Pour chaque trou identifié, évalue :
- **Pertinence** pour l'audience et le produit (un gap n'est pas automatiquement une opportunité — vérifier l'alignement avec la mission du site).
- **Effort estimé** pour produire le contenu (donnée existante en base vs recherche éditoriale à faire).
- **Signal de demande** : le sujet apparaît-il dans des recherches WebSearch, des questions récurrentes, des forums ?

## Étape 5 — Prioriser et restituer

Classe les gaps par impact/effort. Sortie attendue :

| Sujet manquant | Pourquoi ça compte | Effort | Format suggéré | Priorité |
|---|---|---|---|---|

Limiter la liste finale à des recommandations actionnables (5-15 sujets), pas un inventaire exhaustif de tout ce que fait chaque concurrent.

## Limites à rappeler

- L'exploration de la concurrence se fait par recherche web manuelle, pas par crawl exhaustif — l'échantillon peut manquer des pages profondes.
- Un gap de contenu n'est une priorité que s'il est aligné avec le positionnement du produit, pas seulement parce qu'un concurrent l'a.
