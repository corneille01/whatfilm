---
name: seo-geo
description: SEO et GEO (Generative Engine Optimization) combinés — mots-clés, schema markup, et optimisation pour les moteurs de réponse IA (ChatGPT, Perplexity, Gemini, AI Overviews) en plus des moteurs traditionnels. Utiliser quand l'utilisateur demande d'optimiser une page pour le SEO, pour être cité par une IA, ou parle de "GEO", "AI Overviews", "être cité par ChatGPT/Perplexity".
---

# SEO + GEO (Generative Engine Optimization)

Objectif : rendre une page à la fois bien classée sur les moteurs traditionnels et facilement extractible/citable par les moteurs de réponse IA.

## Principe

Le SEO classique et le GEO partagent une base commune (contenu clair, structure sémantique, autorité) mais divergent sur certains points : les moteurs IA privilégient les réponses extractibles, factuelles, bien structurées, et citent plus volontiers des sources qui répondent directement à une question avec des faits vérifiables et une attribution claire.

## Étape 1 — Diagnostic de la page/du sujet

- Vérifier le title, meta description, et la présence d'un H1 clair alignés sur l'intention de recherche.
- Vérifier la structure des headings (H2/H3 qui correspondent à des sous-questions naturelles).
- Regarder si la page répond à une question précise dans les 1-2 premières phrases suivant chaque heading (les moteurs IA extraient souvent ce premier passage).

## Étape 2 — SEO traditionnel

- Utiliser `keyword-research` en amont si les mots-clés cibles ne sont pas déjà définis.
- Vérifier le maillage interne (liens vers/depuis des pages thématiquement liées).
- Vérifier les Core Web Vitals si pertinent (renvoyer vers la skill `benchmark` pour une mesure de performance).

## Étape 3 — Schema markup (données structurées)

Recommander/générer le JSON-LD adapté au type de contenu :
- `Article` / `BlogPosting` pour du contenu éditorial
- `FAQPage` pour des sections questions/réponses
- `Movie` ou `CreativeWork` pour des pages de films (pertinent pour whatfilm)
- `Place` / `LocalBusiness` ou `Place` pour des pages de lieux de tournage géolocalisés
- `BreadcrumbList` pour la navigation

Toujours valider mentalement le schema contre le contenu réel de la page — un schema qui ne correspond pas au contenu visible est une pratique trompeuse à éviter (risque de pénalité et de mauvaise citation par les IA).

## Étape 4 — Optimisation GEO spécifique

- **Réponses autonomes** : chaque section doit pouvoir être comprise hors contexte (un moteur IA peut extraire un seul paragraphe).
- **Faits vérifiables et datés** : citer des sources, des dates, des chiffres précis plutôt que des formulations vagues — les moteurs IA favorisent le contenu qu'ils peuvent attribuer avec confiance.
- **Attribution claire** : nom d'auteur/éditeur, date de publication/mise à jour visible.
- **Éviter le contenu purement promotionnel** sans substance factuelle — les moteurs IA le déprioritisent pour les réponses factuelles.

## Étape 5 — Restituer

Fournir une liste concrète de modifications (pas juste des principes généraux) : titres à reformuler, sections à ajouter, schema JSON-LD à insérer (code prêt à intégrer), maillage interne à créer.

## Limites à rappeler

- Il n'existe pas d'outil de mesure fiable de "visibilité dans les réponses IA" équivalent au tracking de position SEO classique — les recommandations GEO reposent sur les meilleures pratiques connues, pas sur une métrique mesurée en temps réel.
- Ne pas ajouter de schema markup qui ne reflète pas fidèlement le contenu de la page.
