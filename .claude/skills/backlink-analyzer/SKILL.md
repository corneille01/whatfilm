---
name: backlink-analyzer
description: Analyse du profil de liens entrants (backlinks) — repère les liens toxiques, les opportunités de link building, et compare le profil à des concurrents. Utiliser quand l'utilisateur demande "analyse mes backlinks", "backlink analysis", "d'où viennent nos liens", ou "opportunités de netlinking". Nécessite un export de données (Ahrefs/Semrush/Moz/Search Console) car aucun outil de backlink n'est connecté par défaut.
---

# Backlink Analyzer

Objectif : évaluer la qualité et les opportunités d'un profil de backlinks. Cette skill ne peut pas crawler le web à la recherche de liens entrants — elle dépend de données fournies par l'utilisateur ou d'outils déjà connectés.

## Étape 0 — Vérifier la source de données

Un profil de backlinks fiable ne peut pas être reconstitué par simple recherche web. Avant de commencer, demande à l'utilisateur :
- Un export CSV/Excel depuis Ahrefs, Semrush, Moz, ou Google Search Console (rapport "Liens"), OU
- Une clé API pour un de ces outils si elle est configurée dans le projet.

Si rien n'est disponible, dis-le clairement et propose une alternative : Google Search Console est gratuit et suffisant pour un premier état des lieux — expliquer comment exporter le rapport de liens (Search Console → Liens → Exporter).

Ne jamais improviser une liste de "backlinks probables" par déduction sans données — c'est le genre d'analyse qui doit rester factuelle.

## Étape 1 — Nettoyer et charger les données

Une fois le fichier fourni (chemin donné par l'utilisateur), le charger et normaliser les colonnes clés : domaine source, URL source, URL cible, texte d'ancre, type de lien (dofollow/nofollow), date de première détection.

## Étape 2 — Segmenter

1. **Par qualité du domaine source** : domaines reconnus/pertinents vs domaines suspects (spam, PBN, contenu automatisé, domaines sans rapport thématique).
2. **Par ancre** : sur-optimisation d'ancres exact-match (signal de manipulation), diversité des ancres.
3. **Par cible** : quelles pages du site concentrent les liens, quelles pages importantes n'en ont aucun.

## Étape 3 — Repérer les liens toxiques

Signaux à considérer (jamais un seul isolé) : domaine sans rapport thématique + ancre sur-optimisée + faible autorité + pic de liens groupé dans le temps. Lister les domaines suspects avec la raison précise, pas juste "semble toxique".

## Étape 4 — Identifier les opportunités

- Concurrents à comparer si des données concurrentes sont aussi fournies (liens qu'ils ont et que nous n'avons pas, sur des domaines thématiquement pertinents).
- Pages avec fort potentiel éditorial mais aucun lien entrant.

## Étape 5 — Restituer

- Résumé quantitatif : nombre de domaines référents, ratio dofollow/nofollow, top 10 domaines par autorité.
- Liste des liens toxiques avec justification, et recommandation (désaveu via Search Console si vraiment nécessaire — action à ne recommander qu'en dernier recours, car un désaveu mal fait peut nuire).
- 3-5 opportunités de netlinking concrètes et actionnables.

## Limites à rappeler

- L'analyse est aussi bonne que les données fournies ; sans export, elle ne peut pas avoir lieu.
- Le désaveu de liens est une action risquée et rarement nécessaire pour Google — ne pas le recommander par défaut.
