# storage/cache_engine/hash_utils.py

import hashlib
import re
from pathlib import Path
from typing import Optional


def sha256_text(value: str, length: Optional[int] = None) -> str:
    """
    Crée un hash SHA256 à partir d'un texte.
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()

    if length is not None:
        return digest[:length]

    return digest


def md5_text(value: str) -> str:
    """
    Ancien hash utilisé par ton ancien storage/cache.py.
    On le garde pour lire les anciens caches.
    """
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def key_url(url: str) -> str:
    """
    Nouvelle clé URL en SHA256.
    """
    return "url:" + sha256_text(url)


def legacy_key_url(url: str) -> str:
    """
    Ancienne clé URL en MD5.
    Utile pendant la migration.
    """
    return "url:" + md5_text(url)


def key_film(tmdb_id, lang: str) -> str:
    """
    Clé pour un film identifié par TMDB.
    """
    return f"film:{tmdb_id}:{lang}"


def key_title(title: str) -> Optional[str]:
    """
    Clé basée sur le titre du film.
    """
    normalized = re.sub(
        r"[^a-z0-9]",
        "",
        title.lower().strip()
    )

    if len(normalized) < 3:
        return None

    return "title:" + normalized


def key_content(transcript: str, ocr_text: str) -> Optional[str]:
    """
    Clé basée sur le contenu textuel :
    transcript + OCR.
    """
    combined = (transcript or "") + " " + (ocr_text or "")

    normalized = re.sub(
        r"[^a-z0-9àâäéèêëïîôùûüç]",
        " ",
        combined.lower()
    )

    words = sorted(set(normalized.split()))
    meaningful_words = [word for word in words if len(word) >= 4]

    if len(meaningful_words) < 5:
        return None

    text_to_hash = " ".join(meaningful_words)

    return "content:" + sha256_text(text_to_hash, length=32)


def video_sha256(path: str | Path) -> str:
    """
    Calcule le SHA256 réel d'un fichier vidéo.
    Permet de reconnaître deux vidéos identiques même si l'URL change.
    """
    path = Path(path)
    h = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def key_video(path: str | Path) -> str:
    """
    Clé Redis pour une vidéo.
    """
    return "video:" + video_sha256(path)


def key_gemini(video_hash: str) -> str:
    """
    Clé Redis pour un résultat Gemini basé sur le hash vidéo.
    """
    return "gemini:" + video_hash


def key_ocr(video_hash: str) -> str:
    """
    Clé Redis pour OCR.
    """
    return "ocr:" + video_hash


def key_subtitle(video_hash: str) -> str:
    """
    Clé Redis pour sous-titres.
    """
    return "subtitle:" + video_hash


def key_tmdb(tmdb_id, lang: str = "fr") -> str:
    """
    Clé Redis pour TMDB.
    """
    return f"tmdb:{tmdb_id}:{lang}"