# ════════════════════════════════════════════════════════════════
# SEO/GEO — métadonnées par page pour le rendu SSR de templates/index.html
#
# La SPA servait auparavant le même frontend/index.html statique (même
# <title>/<meta description>/JSON-LD) pour toutes les routes dynamiques
# (/film/{id}, /genre/{name}, /plateforme/{key}, /lieux-de-tournage...).
# Ce module construit les métadonnées propres à chaque page, injectées
# dans le template Jinja2 par render_index().
# ════════════════════════════════════════════════════════════════
import json

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

_BASE_URL = "https://pelify.app"

_DEFAULT_META = {
    "html_lang": "fr",
    "title": "Trouver un film à partir d’un TikTok, Reel ou Short — Pelify",
    "meta_description": (
        "Trouve instantanément un film, une série ou un anime à partir d’un TikTok, "
        "Reel ou YouTube Short. Identify movies from video links in seconds. "
        "找电影 / 视频找电影 / 电影识别工具 — gratuit."
    ),
    "meta_keywords": (
        "trouver film tiktok, identifier film vidéo, quel film est cette scène, "
        "movie finder, shazam film, find movie from video, film identifier, "
        "anime finder, série identifier, tiktok film, 电影识别, 找电影, 视频找电影, "
        "影视识别, 取景地, film location finder"
    ),
    "canonical": f"{_BASE_URL}/",
    "og_type": "website",
    "og_title": "🎬 Trouver un film depuis TikTok & Reels — Pelify",
    "og_description": (
        "Colle un lien TikTok ou Reel — trouve instantanément le film, la série "
        "ou l’anime + où le regarder en streaming et visiter les lieux de tournage."
    ),
    "og_url": f"{_BASE_URL}/",
    "og_image": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1200&auto=format",
    "twitter_title": "🎬 Find movies from TikTok & Reels — Pelify",
    "twitter_description": (
        "Paste a TikTok or Reel link — find any movie in seconds and visit the "
        "filming locations. Free worldwide."
    ),
    "twitter_image": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1200&auto=format",
    "extra_jsonld": "",
}


def render_index(request: Request, **overrides) -> HTMLResponse:
    ctx = {**_DEFAULT_META, **overrides}
    return templates.TemplateResponse(request, "index.html", ctx)


def _truncate(text: str, length: int = 160) -> str:
    text = (text or "").strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rsplit(" ", 1)[0] + "…"


def _jsonld(data: dict) -> str:
    """Sérialise en JSON sûr pour un <script type="application/ld+json"> (échappe </script>)."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


GENRE_LABELS = {
    "horror": "Horreur", "horreur": "Horreur", "action": "Action",
    "comedy": "Comédie", "comédie": "Comédie",
    "science-fiction": "Science-fiction", "scifi": "Science-fiction",
    "romance": "Romance", "animation": "Animation", "thriller": "Thriller",
    "drama": "Drame", "drame": "Drame", "documentary": "Documentaire",
    "documentaire": "Documentaire", "fantasy": "Fantastique",
    "fantastique": "Fantastique", "crime": "Crime",
    "family": "Famille", "famille": "Famille",
}

PROVIDER_LABELS = {
    "amazon": "Amazon Prime Video", "netflix": "Netflix", "disney": "Disney+",
    "apple": "Apple TV+", "paramount": "Paramount+", "hulu": "Hulu",
}


def genre_meta(genre_name: str) -> dict:
    label = GENRE_LABELS.get(genre_name.lower(), genre_name.capitalize())
    title = f"Films & séries {label} identifiés depuis TikTok — Pelify"
    desc = (
        f"Découvre les meilleurs films et séries du genre {label} identifiés "
        f"depuis TikTok, Reels et YouTube Shorts, avec streaming et lieux de tournage."
    )
    url = f"{_BASE_URL}/genre/{genre_name}"
    return {
        "title": title, "meta_description": desc,
        "canonical": url, "og_title": title, "og_description": desc, "og_url": url,
        "twitter_title": title, "twitter_description": desc,
    }


def provider_meta(provider_key: str) -> dict:
    label = PROVIDER_LABELS.get(provider_key.lower(), provider_key.capitalize())
    title = f"Films & séries disponibles sur {label} — Pelify"
    desc = (
        f"Découvre les films et séries disponibles en streaming sur {label}, "
        f"identifiés depuis TikTok et Reels par Pelify."
    )
    url = f"{_BASE_URL}/plateforme/{provider_key}"
    return {
        "title": title, "meta_description": desc,
        "canonical": url, "og_title": title, "og_description": desc, "og_url": url,
        "twitter_title": title, "twitter_description": desc,
    }


def series_meta() -> dict:
    title = "Séries identifiées depuis TikTok, Reels & Shorts — Pelify"
    desc = (
        "Retrouve toutes les séries identifiées par Pelify depuis des extraits "
        "viraux TikTok, Instagram Reels et YouTube Shorts."
    )
    url = f"{_BASE_URL}/series"
    return {
        "title": title, "meta_description": desc,
        "canonical": url, "og_title": title, "og_description": desc, "og_url": url,
        "twitter_title": title, "twitter_description": desc,
    }


def lieux_meta(stats: dict | None = None) -> dict:
    stats = stats or {}
    total_films = stats.get("total_films")
    total_locations = stats.get("total_locations")
    if total_films and total_locations:
        desc = (
            f"Explore {total_locations} lieux de tournage réels de {total_films} films "
            f"et séries identifiés par Pelify. Carte, adresses et infos pratiques pour "
            f"visiter les décors de tes films préférés."
        )
    else:
        desc = (
            "Explore les lieux de tournage réels des films et séries identifiés par "
            "Pelify. Carte, adresses et infos pratiques pour visiter les décors."
        )
    title = "Lieux de tournage de films & séries — Pelify"
    url = f"{_BASE_URL}/lieux-de-tournage"
    extra_jsonld = ""
    if total_films and total_locations:
        extra_jsonld = _jsonld({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "Lieux de tournage de films et séries",
            "description": desc,
            "numberOfItems": total_locations,
        })
    return {
        "title": title, "meta_description": desc,
        "canonical": url, "og_title": title, "og_description": desc, "og_url": url,
        "twitter_title": title, "twitter_description": desc,
        "extra_jsonld": extra_jsonld,
    }


def film_meta(details: dict, media_type: str, film_id: int) -> dict:
    title_raw = details.get("title") or details.get("name") or "Film"
    year = (details.get("release_date") or details.get("first_air_date") or "")[:4]
    overview = _truncate(details.get("overview") or "", 160)
    poster = details.get("poster_path")
    image = f"https://image.tmdb.org/t/p/w500{poster}" if poster else _DEFAULT_META["og_image"]
    title = f"{title_raw}{f' ({year})' if year else ''} — Streaming, casting & lieux de tournage | Pelify"
    desc = overview or (
        f"Découvre où regarder {title_raw} en streaming, son casting complet "
        f"et ses lieux de tournage réels sur Pelify."
    )
    url = f"{_BASE_URL}/film/{film_id}"

    schema_type = "TVSeries" if media_type == "tv" else "Movie"
    ld: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": title_raw,
        "description": desc,
    }
    if image:
        ld["image"] = image
    date_val = details.get("release_date") or details.get("first_air_date")
    if date_val:
        ld["datePublished"] = date_val
    genres = [g.get("name") for g in details.get("genres", []) if g.get("name")]
    if genres:
        ld["genre"] = genres
    cast = [
        c.get("name") for c in details.get("credits", {}).get("cast", [])[:8]
        if c.get("name")
    ]
    if cast:
        ld["actor"] = [{"@type": "Person", "name": n} for n in cast]
    vote_avg = details.get("vote_average")
    vote_count = details.get("vote_count")
    if vote_avg and vote_count:
        ld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(vote_avg, 1),
            "ratingCount": vote_count,
            "bestRating": 10,
            "worstRating": 0,
        }

    return {
        "title": title, "meta_description": desc,
        "canonical": url,
        "og_type": "video.movie" if media_type == "movie" else "video.tv_show",
        "og_title": title, "og_description": desc, "og_url": url, "og_image": image,
        "twitter_title": title, "twitter_description": desc, "twitter_image": image,
        "extra_jsonld": _jsonld(ld),
    }


LANG_META = {
    "en": {
        "html_lang": "en",
        "title": "Find a movie from a TikTok, Reel or Short — Pelify",
        "meta_description": (
            "Instantly find a movie, series or anime from a TikTok, Reel or "
            "YouTube Short link. Free movie identification tool."
        ),
        "og_title": "🎬 Find movies from TikTok & Reels — Pelify",
        "og_description": (
            "Paste a TikTok or Reel link — find any movie in seconds and visit "
            "the filming locations. Free worldwide."
        ),
    },
    "es": {
        "html_lang": "es",
        "title": "Encuentra una película desde un TikTok, Reel o Short — Pelify",
        "meta_description": (
            "Encuentra al instante una película, serie o anime a partir de un "
            "enlace de TikTok, Reel o YouTube Short. Herramienta gratuita."
        ),
        "og_title": "🎬 Encuentra películas desde TikTok y Reels — Pelify",
        "og_description": (
            "Pega un enlace de TikTok o Reel — encuentra cualquier película en "
            "segundos y visita las localizaciones de rodaje."
        ),
    },
    "de": {
        "html_lang": "de",
        "title": "Finde einen Film aus einem TikTok, Reel oder Short — Pelify",
        "meta_description": (
            "Finde sofort einen Film, eine Serie oder einen Anime aus einem "
            "TikTok-, Reel- oder YouTube-Short-Link. Kostenloses Tool."
        ),
        "og_title": "🎬 Filme aus TikTok & Reels finden — Pelify",
        "og_description": (
            "Füge einen TikTok- oder Reel-Link ein — finde jeden Film in "
            "Sekunden und besuche die Drehorte."
        ),
    },
    "zh": {
        "html_lang": "zh",
        "title": "从 TikTok、Reel 或 Short 中找电影 — Pelify",
        "meta_description": (
            "通过 TikTok、Reel 或 YouTube Short 链接即时找到电影、剧集或动漫。"
            "免费电影识别工具。"
        ),
        "og_title": "🎬 从 TikTok 和 Reels 找电影 — Pelify",
        "og_description": "粘贴 TikTok 或 Reel 链接——几秒钟内找到任何电影并查看取景地。",
    },
}


def lang_meta(lang: str) -> dict:
    overrides = LANG_META.get(lang)
    if not overrides:
        return {"html_lang": lang}
    url = f"{_BASE_URL}/{lang}"
    return {
        **overrides,
        "canonical": url,
        "og_url": url,
        "twitter_title": overrides.get("og_title", _DEFAULT_META["twitter_title"]),
        "twitter_description": overrides.get("og_description", _DEFAULT_META["twitter_description"]),
    }
