---
name: competitor-analysis
description: Analyse SEO concurrentielle — identifie qui se positionne sur quels mots-clés, pourquoi ils rankent mieux, et ce qu'ils font différemment (contenu, structure, backlinks, technique). Utiliser quand l'utilisateur demande "analyse la concurrence", "competitor analysis", "pourquoi X est mieux classé que nous", ou veut comparer son site à des concurrents.
---

# Competitor Analysis (SEO)

Objectif : comprendre pourquoi des concurrents surperforment sur certains mots-clés/sujets et en tirer des actions concrètes.

## Étape 1 — Identifier les concurrents

- Concurrents **directs** (même produit/audience) donnés par l'utilisateur ou déduits du domaine (pour whatfilm : sites de cinétourisme, bases de données de lieux de tournage, guides de voyage cinéma).
- Concurrents **SEO** (pas forcément des concurrents produit) : qui apparaît en haut des SERP sur les mots-clés cibles. Utilise WebSearch sur 5-10 requêtes représentatives pour repérer les domaines récurrents.

## Étape 2 — Comparer sur plusieurs axes

Pour chaque concurrent retenu (3-5 max, pour rester actionnable) :

1. **Contenu** : quels types de pages ont-ils que le site analysé n'a pas (guides, listes, pages par ville/film, comparatifs) ? Profondeur et fraîcheur du contenu.
2. **Structure / architecture** : organisation des catégories, maillage interne, présence de pages piliers.
3. **Technique** : vitesse perçue, mobile-friendliness, structured data visible (via WebFetch sur le HTML si besoin — regarder les balises `<script type="application/ld+json">`), title/meta description.
4. **Backlinks** : si aucune donnée d'API n'est disponible, s'appuyer sur des signaux indirects (mentions presse trouvées via WebSearch, partenariats visibles) plutôt que d'inventer des métriques de Domain Rating. Renvoyer vers la skill `backlink-analyzer` pour une analyse dédiée.
5. **Positionnement éditorial** : ton, angle, proposition de valeur.

## Étape 3 — Diagnostiquer les écarts

Pour chaque mot-clé/sujet où un concurrent surperforme, formule une hypothèse causale explicite plutôt qu'une simple observation : "ils rankent mieux sur X parce que [contenu plus complet / plus de backlinks presse / meilleure UX mobile]", pas juste "ils sont mieux classés".

## Étape 4 — Restituer

Tableau de synthèse :

| Concurrent | Points forts | Faiblesses exploitables | Écart principal vs nous |
|---|---|---|---|

Suivi de 3-5 actions priorisées, classées par effort/impact, pas une liste exhaustive.

## Limites à rappeler

- Sans accès à un outil de scraping SERP à grande échelle, l'analyse se base sur un échantillon de requêtes manuel, pas une couverture exhaustive.
- Ne pas prétendre à des métriques précises (Domain Rating, trafic estimé) sans source citée.
