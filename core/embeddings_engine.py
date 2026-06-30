"""
core/embeddings_engine.py — Génération d'embeddings et recherche par
similarité, en couche d'identification AVANT les LLM (Gemini/Qwen/Groq).

Objectif : à mesure que Pelify identifie des films avec succès, on
mémorise leur "signature" (embeddings texte du transcript/OCR + embeddings
visuels des frames) dans la base MySQL université. Pour chaque nouvelle
vidéo, on vérifie d'abord si elle ressemble à une signature déjà connue
avant de dépenser du quota Gemini/Qwen/Groq.

Modèles utilisés :
  - Texte   : sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
  - Visuel  : openai/clip-vit-base-patch32 (512 dimensions) — DÉSACTIVÉ
    temporairement pour contrainte mémoire Render Free (512 MB).

Politique de seuils (calibrée au démarrage, à affiner avec
pelify_embedding_match_log au fil du temps) :
  - Visuel : seuil strict (0.92) — deux scènes différentes peuvent se
    ressembler visuellement sans être le même film, donc on préfère
    rater un hit que créer un faux positif.
  - Texte  : seuil modéré (0.88) — un transcript a plus de signal
    discriminant qu'une image isolée (noms propres, dialogues), mais
    reste prudent.

Politique d'enregistrement : seuls les résultats avec confidence >= 70
(score final du rerank) sont mémorisés, pour ne jamais polluer la base
de référence avec un match incertain qui deviendrait un faux ami pour
toutes les recherches futures.

Ce module ne lève jamais d'exception vers l'appelant : toute erreur
(modèle non chargé, université indisponible, frame illisible) résulte en
un retour vide/None, pour que le pipeline principal bascule simplement
sur les LLM comme si ce module n'existait pas.
"""

import os
from functools import lru_cache
from typing import Optional, List, Dict, Any

from storage.university_client import (
    university_search_text_embeddings,
    university_search_visual_embeddings,
    university_insert_text_embedding,
    university_insert_visual_embedding,
    university_log_match,
)

# ═══════════════════════════ CONFIGURATION ═══════════════════════════

EMBEDDINGS_ENABLED = os.environ.get("EMBEDDINGS_ENABLED", "true").lower() == "true"

TEXT_MODEL_NAME  = "sentence-transformers/all-MiniLM-L6-v2"
VISUAL_MODEL_NAME = "openai/clip-vit-base-patch32"

TEXT_SIMILARITY_THRESHOLD   = float(os.environ.get("TEXT_SIMILARITY_THRESHOLD", "0.88"))
VISUAL_SIMILARITY_THRESHOLD = float(os.environ.get("VISUAL_SIMILARITY_THRESHOLD", "0.92"))

# Score de confiance minimal (du rerank final) pour qu'un résultat soit
# mémorisé comme référence future. Volontairement strict : on préfère
# une base de référence petite mais fiable plutôt que large mais bruitée.
MIN_CONFIDENCE_TO_STORE = 70

MIN_TEXT_LENGTH_FOR_EMBEDDING = 30  # caractères ; sous ce seuil, signal trop faible


# ═══════════════════════════ CHARGEMENT LAZY DES MODÈLES ═══════════════════════════
#
# Les modèles sont chargés à la première utilisation seulement (lazy), pas
# au démarrage de l'app — évite d'alourdir le temps de boot de Render pour
# des requêtes qui n'utiliseraient jamais cette fonctionnalité. Mis en
# cache ensuite via lru_cache pour ne charger qu'une seule fois par
# process worker.

@lru_cache(maxsize=1)
def _get_text_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(TEXT_MODEL_NAME)
    except Exception as e:
        print(f"⚠️ Embeddings texte: modèle non chargé ({str(e)[:120]})", flush=True)
        return None


@lru_cache(maxsize=1)
def _get_visual_model():
    """
    Désactivé temporairement : CLIP (~600 MB) dépasse la mémoire
    disponible sur Render Free (512 MB) combiné avec le modèle texte
    (PyTorch + sentence-transformers ~340 MB déjà à eux seuls).
    À réactiver quand le plan Render sera upgradé, ou en migrant CLIP
    vers un service séparé.
    """
    print("ℹ️ Embeddings visuels désactivés (contrainte mémoire Render Free)", flush=True)
    return None, None


# ═══════════════════════════ GÉNÉRATION D'EMBEDDINGS ═══════════════════════════

def generate_text_embedding(text: str) -> Optional[List[float]]:
    """
    Génère un embedding 384-dim pour un texte (transcript + OCR combinés).
    Retourne None si le texte est trop court ou si le modèle est
    indisponible — jamais d'exception.
    """
    text = (text or "").strip()
    if len(text) < MIN_TEXT_LENGTH_FOR_EMBEDDING:
        return None

    model = _get_text_model()
    if model is None:
        return None

    try:
        # Tronque à une longueur raisonnable : un transcript très long
        # n'apporte pas de signal supplémentaire utile au-delà d'un
        # certain point, et ralentit l'encodage pour rien.
        truncated = text[:2000]
        vector = model.encode(truncated, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        print(f"⚠️ Embedding texte KO: {str(e)[:120]}", flush=True)
        return None


def generate_visual_embeddings(frame_paths: List[str]) -> List[Optional[List[float]]]:
    """
    Génère un embedding 512-dim (CLIP) pour chaque frame fournie.
    Retourne une liste de même longueur que frame_paths ; chaque élément
    est soit un vecteur, soit None si cette frame précise a échoué
    (fichier illisible, etc.) — permet à l'appelant de savoir quelle
    frame a échoué sans perdre les autres.

    Note : retourne actuellement [None] * len(frame_paths) puisque
    _get_visual_model() est désactivé (cf. commentaire ci-dessus).
    """
    if not frame_paths:
        return []

    model, processor = _get_visual_model()
    if model is None or processor is None:
        return [None] * len(frame_paths)

    results: List[Optional[List[float]]] = []

    try:
        from PIL import Image
        import torch

        for fp in frame_paths:
            try:
                if not os.path.exists(fp) or os.path.getsize(fp) == 0:
                    results.append(None)
                    continue

                image = Image.open(fp).convert("RGB")
                inputs = processor(images=image, return_tensors="pt")

                with torch.no_grad():
                    features = model.get_image_features(**inputs)
                    # Normalisation L2 pour que la similarité cosine soit
                    # directement comparable au seuil configuré.
                    features = features / features.norm(p=2, dim=-1, keepdim=True)

                results.append(features[0].tolist())
            except Exception as e:
                print(f"⚠️ Embedding visuel KO pour {fp}: {str(e)[:100]}", flush=True)
                results.append(None)

    except ImportError as e:
        print(f"⚠️ Embeddings visuels: dépendance manquante ({str(e)[:80]})", flush=True)
        return [None] * len(frame_paths)

    return results


# ═══════════════════════════ RECHERCHE AVANT LES LLM ═══════════════════════════

async def check_known_film_by_text(transcript: str, ocr_text: str) -> Optional[Dict[str, Any]]:
    """
    Vérifie si le texte (transcript + OCR) ressemble à un texte déjà
    identifié avec succès auparavant. Retourne le meilleur match
    {tmdb_id, media_type, lang, score} si trouvé au-dessus du seuil,
    None sinon (y compris si les embeddings sont désactivés ou en panne).

    Point d'entrée prévu pour être appelé EN TOUT PREMIER dans le
    pipeline, avant tout appel Gemini/Qwen/Groq, pour économiser le
    quota LLM quand un match fiable existe déjà.
    """
    if not EMBEDDINGS_ENABLED:
        return None

    combined = f"{transcript or ''} {ocr_text or ''}".strip()
    embedding = generate_text_embedding(combined)
    if embedding is None:
        return None

    matches = await university_search_text_embeddings(
        embedding, top_k=1, threshold=TEXT_SIMILARITY_THRESHOLD
    )

    if not matches:
        await university_log_match(
            query_type="text",
            similarity_score=0.0,
            threshold_used=TEXT_SIMILARITY_THRESHOLD,
            accepted=False,
            fallback_to_llm=True,
        )
        return None

    best = matches[0]
    await university_log_match(
        query_type="text",
        similarity_score=best["score"],
        threshold_used=TEXT_SIMILARITY_THRESHOLD,
        accepted=True,
        matched_tmdb_id=best["tmdb_id"],
        fallback_to_llm=False,
    )

    print(
        f"🎯 Match texte trouvé (embeddings) — tmdb_id={best['tmdb_id']} "
        f"score={best['score']:.3f} (seuil={TEXT_SIMILARITY_THRESHOLD})",
        flush=True,
    )
    return best


async def check_known_film_by_frames(frame_paths: List[str]) -> Optional[Dict[str, Any]]:
    """
    Vérifie si une ou plusieurs frames ressemblent visuellement à des
    frames déjà identifiées avec succès auparavant. Compare chaque frame
    individuellement et retourne le meilleur match trouvé tous frames
    confondus, si au-dessus du seuil strict.

    Comme pour check_known_film_by_text, prévu pour être appelé en tout
    premier dans le pipeline, avant les LLM.

    Note : retourne toujours None tant que _get_visual_model() est
    désactivé — c'est attendu, pas un bug.
    """
    if not EMBEDDINGS_ENABLED or not frame_paths:
        return None

    embeddings = generate_visual_embeddings(frame_paths)
    valid_embeddings = [e for e in embeddings if e is not None]
    if not valid_embeddings:
        return None

    best_overall: Optional[Dict[str, Any]] = None

    for embedding in valid_embeddings:
        matches = await university_search_visual_embeddings(
            embedding, top_k=1, threshold=VISUAL_SIMILARITY_THRESHOLD
        )
        if matches and (best_overall is None or matches[0]["score"] > best_overall["score"]):
            best_overall = matches[0]

    if best_overall is None:
        await university_log_match(
            query_type="visual",
            similarity_score=0.0,
            threshold_used=VISUAL_SIMILARITY_THRESHOLD,
            accepted=False,
            fallback_to_llm=True,
        )
        return None

    await university_log_match(
        query_type="visual",
        similarity_score=best_overall["score"],
        threshold_used=VISUAL_SIMILARITY_THRESHOLD,
        accepted=True,
        matched_tmdb_id=best_overall["tmdb_id"],
        fallback_to_llm=False,
    )

    print(
        f"🎯 Match visuel trouvé (embeddings) — tmdb_id={best_overall['tmdb_id']} "
        f"score={best_overall['score']:.3f} (seuil={VISUAL_SIMILARITY_THRESHOLD})",
        flush=True,
    )
    return best_overall


async def check_known_film(
    transcript: str = "",
    ocr_text: str = "",
    frame_paths: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Point d'entrée unique recommandé : tente d'abord le texte (moins coûteux
    en calcul, signal souvent plus discriminant si transcript exploitable),
    puis le visuel si le texte n'a rien donné. Retourne le premier match
    trouvé au-dessus du seuil, ou None si rien ne matche (= il faut passer
    aux LLM normalement).
    """
    if not EMBEDDINGS_ENABLED:
        return None

    text_match = await check_known_film_by_text(transcript, ocr_text)
    if text_match:
        return text_match

    if frame_paths:
        visual_match = await check_known_film_by_frames(frame_paths)
        if visual_match:
            return visual_match

    return None


# ═══════════════════════════ ENREGISTREMENT APRÈS IDENTIFICATION RÉUSSIE ═══════════════════════════

async def store_film_signature(
    tmdb_id: int,
    confidence: int,
    media_type: str = "movie",
    lang: str = "fr",
    transcript: str = "",
    ocr_text: str = "",
    frame_paths: Optional[List[str]] = None,
) -> None:
    """
    Enregistre la signature (embeddings texte + visuel) d'un film identifié
    avec succès, pour alimenter la base de référence future. N'enregistre
    rien si confidence < MIN_CONFIDENCE_TO_STORE (70 par défaut), pour ne
    jamais polluer la base avec un match incertain.

    À appeler depuis process_analysis() juste après qu'un résultat final
    soit obtenu avec succès (peu importe la source : LLM normal, ou même
    un match embeddings antérieur — réenregistrer renforce la confiance
    statistique de cette signature au fil du temps).
    """
    if not EMBEDDINGS_ENABLED:
        return

    if confidence < MIN_CONFIDENCE_TO_STORE:
        return

    if not in_valid_media_type(media_type):
        media_type = "movie"

    combined = f"{transcript or ''} {ocr_text or ''}".strip()
    text_embedding = generate_text_embedding(combined)
    if text_embedding is not None:
        await university_insert_text_embedding(
            tmdb_id=tmdb_id,
            embedding=text_embedding,
            media_type=media_type,
            lang=lang,
            excerpt=combined[:500],
        )

    if frame_paths:
        from storage.cache_engine.hash_utils import sha256_text

        visual_embeddings = generate_visual_embeddings(frame_paths)
        for idx, (fp, embedding) in enumerate(zip(frame_paths, visual_embeddings)):
            if embedding is None:
                continue
            try:
                with open(fp, "rb") as f:
                    frame_hash = sha256_text(f.read().hex(), length=64)
            except Exception:
                frame_hash = None

            await university_insert_visual_embedding(
                tmdb_id=tmdb_id,
                embedding=embedding,
                media_type=media_type,
                frame_index=idx,
                frame_hash=frame_hash,
            )

    print(f"💾 Signature embeddings enregistrée — tmdb_id={tmdb_id} (confidence={confidence})", flush=True)


def in_valid_media_type(media_type: str) -> bool:
    return media_type in ("movie", "tv")