# vision/universal_downloader.py
import os
import sys
import asyncio
import json
import tempfile
import shutil
import uuid
from typing import Dict, Any


IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))

# Sur Render 512 MB, Playwright est trop lourd.
# Ici on ne l'utilise plus dans la cascade principale.
DISABLE_PLAYWRIGHT = os.environ.get("DISABLE_PLAYWRIGHT", "true").lower() == "true"

# Limite de sécurité pour éviter de télécharger des vidéos énormes.
MAX_DOWNLOAD_MB = int(os.environ.get("MAX_DOWNLOAD_MB", "80"))
MAX_DOWNLOAD_BYTES = MAX_DOWNLOAD_MB * 1024 * 1024


YTDLP_BASE_OPTIONS = {
    "format": "mp4/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "socket_timeout": 30,
    "retries": 2,
    "noplaylist": True,
    "continuedl": False,
    "overwrites": True,
    "restrictfilenames": True,
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.6367.82 Mobile Safari/537.36"
        )
    },
}


# ══════════════════════════════════════════════════════════════
# Helpers fichiers
# ══════════════════════════════════════════════════════════════

def _safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _safe_rmtree(path: str) -> None:
    try:
        if path and os.path.exists(path):
            shutil.rmtree(path)
    except Exception:
        pass


def _file_ok(path: str) -> bool:
    return bool(
        path
        and os.path.exists(path)
        and os.path.getsize(path) > 1000
    )


def _too_big(path: str) -> bool:
    try:
        return os.path.getsize(path) > MAX_DOWNLOAD_BYTES
    except Exception:
        return False


def _referer_for_platform(platform: str, url: str) -> str:
    platform = (platform or "").lower()

    if platform == "tiktok" or "tiktok.com" in url:
        return "https://www.tiktok.com/"

    if platform == "facebook" or "facebook.com" in url or "fb.watch" in url:
        return "https://www.facebook.com/"

    if platform == "instagram" or "instagram.com" in url:
        return "https://www.instagram.com/"

    if platform == "twitter" or "x.com" in url or "twitter.com" in url:
        return "https://x.com/"

    if platform == "youtube" or "youtube.com" in url or "youtu.be" in url:
        return "https://www.youtube.com/"

    return "https://www.google.com/"


# ══════════════════════════════════════════════════════════════
# Téléchargement URL directe
# ══════════════════════════════════════════════════════════════

async def _download_via_direct_url(
    direct_url: str,
    output_path: str,
    referer: str = "https://www.google.com/",
) -> Dict[str, Any]:
    """
    Télécharge un fichier depuis une URL directe avec httpx streaming.
    Utilise un fichier .part unique pour éviter les conflits concurrents.
    """
    try:
        import httpx

        total = 0
        tmp_path = f"{output_path}.part-{uuid.uuid4().hex[:8]}"

        _safe_remove(output_path)

        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10; K) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.6367.82 Mobile Safari/537.36"
                ),
                "Referer": referer,
            },
        ) as client:
            async with client.stream("GET", direct_url) as resp:
                if resp.status_code != 200:
                    return {
                        "ok": False,
                        "code": "direct_download_failed",
                        "message": (
                            "Échec du téléchargement direct "
                            f"(HTTP {resp.status_code})."
                        ),
                    }

                with open(tmp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        if not chunk:
                            continue

                        total += len(chunk)

                        if total > MAX_DOWNLOAD_BYTES:
                            _safe_remove(tmp_path)
                            return {
                                "ok": False,
                                "code": "file_too_large",
                                "message": (
                                    f"Vidéo trop volumineuse, "
                                    f"limite {MAX_DOWNLOAD_MB} Mo."
                                ),
                            }

                        f.write(chunk)

        if _file_ok(tmp_path):
            shutil.move(tmp_path, output_path)
            return {"ok": True}

        size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
        _safe_remove(tmp_path)

        return {
            "ok": False,
            "code": "direct_download_empty",
            "message": f"Fichier téléchargé trop petit ({size} octets).",
        }

    except Exception as e:
        try:
            if "tmp_path" in locals():
                _safe_remove(tmp_path)
        except Exception:
            pass

        return {
            "ok": False,
            "code": "direct_download_error",
            "message": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════
# YouTube worker
# ══════════════════════════════════════════════════════════════

async def _download_youtube_via_worker(
    url: str,
    output_path: str,
) -> Dict[str, Any]:
    """
    Lance youtube_worker.py en subprocess isolé.

    YouTube reste séparé parce que Gemini peut parfois analyser directement
    les liens YouTube, et ton worker YouTube a une logique dédiée.
    """
    worker_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "youtube_worker.py",
    )

    if not os.path.exists(worker_path):
        return {
            "ok": False,
            "code": "worker_missing",
            "message": f"youtube_worker.py introuvable à {worker_path}",
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)

        if stderr:
            print(
                f"  [youtube_worker stderr] "
                f"{stderr.decode(errors='ignore')[:400]}",
                flush=True,
            )

        if not stdout:
            return {
                "ok": False,
                "code": "worker_no_output",
                "message": "Worker YouTube n'a produit aucune sortie.",
            }

        worker_result = json.loads(stdout.decode(errors="ignore"))

    except asyncio.TimeoutError:
        return {
            "ok": False,
            "code": "worker_timeout",
            "message": "Timeout worker YouTube après 45s.",
        }

    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "code": "worker_json_error",
            "message": f"JSON invalide du worker YouTube: {e}",
        }

    except Exception as e:
        return {
            "ok": False,
            "code": "worker_exception",
            "message": str(e)[:200],
        }

    if not worker_result.get("ok"):
        print(
            f"⚠️ Worker YouTube KO: {worker_result.get('message', '')}",
            flush=True,
        )
        return worker_result

    direct_url = worker_result.get("direct_url", "")

    if not direct_url:
        return {
            "ok": False,
            "code": "worker_no_url",
            "message": "Worker YouTube n'a pas retourné d'URL directe.",
        }

    print("✅ Worker YouTube → URL directe obtenue, téléchargement...", flush=True)

    return await _download_via_direct_url(
        direct_url,
        output_path,
        referer="https://www.youtube.com/",
    )


# ══════════════════════════════════════════════════════════════
# API tikwm — tentative générique
# ══════════════════════════════════════════════════════════════

async def _download_via_tikwm_api(
    url: str,
    output_path: str,
    platform: str = "unknown",
) -> Dict[str, Any]:
    """
    Tente de résoudre une vidéo via l'API tikwm.

    Dans ta logique Pelify :
      - toutes les plateformes sauf YouTube passent d'abord ici ;
      - si tikwm échoue, fallback yt-dlp.

    Attention :
      tikwm est surtout fiable pour TikTok.
      Pour Facebook/Instagram/autres, on tente quand même, puis yt-dlp prend le relais.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10; K) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.6367.82 Mobile Safari/537.36"
                )
            },
        ) as client:
            r = await client.get(
                "https://www.tikwm.com/api/",
                params={
                    "url": url,
                    "hd": 1,
                },
            )
            r.raise_for_status()
            j = r.json()

        if j.get("code") != 0:
            return {
                "ok": False,
                "code": "tikwm_failed",
                "message": f"tikwm: {j.get('msg', 'erreur')}",
            }

        data = j.get("data") or {}

        # Champs possibles selon les réponses tikwm.
        play = (
            data.get("hdplay")
            or data.get("play")
            or data.get("wmplay")
            or data.get("download")
            or data.get("url")
        )

        if not play:
            return {
                "ok": False,
                "code": "tikwm_no_url",
                "message": "tikwm: pas d'URL vidéo exploitable.",
            }

        if isinstance(play, list):
            play = play[0] if play else ""

        if not isinstance(play, str) or not play.strip():
            return {
                "ok": False,
                "code": "tikwm_bad_url",
                "message": "tikwm: URL vidéo invalide.",
            }

        play = play.strip()

        if play.startswith("/"):
            play = "https://www.tikwm.com" + play

        print(
            f"✅ tikwm → URL MP4 obtenue pour [{platform}], téléchargement...",
            flush=True,
        )

        return await _download_via_direct_url(
            play,
            output_path,
            referer=_referer_for_platform(platform, url),
        )

    except Exception as e:
        return {
            "ok": False,
            "code": "tikwm_error",
            "message": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════
# yt-dlp générique
# ══════════════════════════════════════════════════════════════

async def _download_with_ytdlp(
    url: str,
    output_path: str,
    platform: str = "unknown",
) -> Dict[str, Any]:
    """
    yt-dlp avec répertoire temporaire unique.

    Important :
    - évite les conflits .part ;
    - chaque téléchargement se fait dans son dossier isolé ;
    - le fichier final est déplacé vers output_path.
    """
    try:
        import yt_dlp
    except ImportError:
        return {
            "ok": False,
            "code": "yt_dlp_missing",
            "message": "yt-dlp non installé.",
        }

    base_dir = os.path.dirname(output_path) or "."
    os.makedirs(base_dir, exist_ok=True)

    temp_dir = tempfile.mkdtemp(
        prefix=f"ytdlp_{uuid.uuid4().hex[:8]}_",
        dir=base_dir,
    )

    cookie_file = os.path.join(temp_dir, "yt_consent_cookies.txt")

    try:
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(".youtube.com\tTRUE\t/\tFALSE\t0\tCONSENT\tYES+\n")
            f.write(".google.com\tTRUE\t/\tFALSE\t0\tCONSENT\tYES+\n")

        strategies = [
            {
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "ios"],
                        "skip": ["hls", "dash"],
                    }
                }
            },
            {
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web", "android"],
                        "skip": ["hls"],
                    }
                }
            },
            {
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web"],
                    }
                }
            },
            {},
        ]

        last_error = ""

        for strategy in strategies:
            opts = dict(YTDLP_BASE_OPTIONS)
            opts.update(strategy)

            opts["outtmpl"] = os.path.join(temp_dir, "download.%(ext)s")
            opts["cookiefile"] = cookie_file
            opts["max_filesize"] = MAX_DOWNLOAD_BYTES

            # Referer utile pour certaines plateformes.
            opts["headers"] = dict(opts.get("headers") or {})
            opts["headers"]["Referer"] = _referer_for_platform(platform, url)

            try:
                loop = asyncio.get_event_loop()

                def _run_ytdlp():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=True)

                info = await loop.run_in_executor(None, _run_ytdlp)

                downloaded_file = None

                if info and info.get("requested_downloads"):
                    downloaded_file = info["requested_downloads"][0].get("filepath")

                if not downloaded_file and info and info.get("_filename"):
                    downloaded_file = info.get("_filename")

                if not downloaded_file:
                    for name in os.listdir(temp_dir):
                        candidate = os.path.join(temp_dir, name)

                        if (
                            os.path.isfile(candidate)
                            and not candidate.endswith(".part")
                            and not candidate.endswith(".ytdl")
                        ):
                            downloaded_file = candidate
                            break

                if downloaded_file and _file_ok(downloaded_file):
                    if _too_big(downloaded_file):
                        return {
                            "ok": False,
                            "code": "file_too_large",
                            "message": (
                                f"Vidéo trop volumineuse, "
                                f"limite {MAX_DOWNLOAD_MB} Mo."
                            ),
                        }

                    _safe_remove(output_path)
                    shutil.move(downloaded_file, output_path)

                    if _file_ok(output_path):
                        return {"ok": True}

                if info and info.get("url"):
                    return {
                        "ok": True,
                        "direct_url": info["url"],
                    }

                last_error = "Aucun flux vidéo exploitable trouvé."

            except Exception as e:
                last_error = str(e)[:200]
                continue

        return {
            "ok": False,
            "code": "ytdlp_error",
            "message": last_error or "yt-dlp a échoué.",
        }

    finally:
        _safe_rmtree(temp_dir)


# ══════════════════════════════════════════════════════════════
# Fonction principale
# ══════════════════════════════════════════════════════════════

async def download_video(
    url: str,
    output_path: str,
    platform: str = "unknown",
) -> Dict[str, Any]:
    """
    Télécharge une vidéo.

    Nouvelle cascade Pelify :

    YouTube :
      1. worker YouTube
      2. yt-dlp fallback

    Toutes les autres plateformes :
      1. tikwm
      2. yt-dlp fallback

    Donc :
      TikTok      → tikwm → yt-dlp
      Facebook    → tikwm → yt-dlp
      Instagram   → tikwm → yt-dlp
      Twitter/X   → tikwm → yt-dlp
      Dailymotion → tikwm → yt-dlp
      Vimeo       → tikwm → yt-dlp
      Reddit      → tikwm → yt-dlp
    """
    _safe_remove(output_path)

    platform = (platform or "unknown").lower()

    # ── YouTube reste séparé ────────────────────────────────────
    if platform == "youtube" or "youtube.com" in url or "youtu.be" in url:
        print("🎬 YouTube → worker subprocess", flush=True)

        result = await _download_youtube_via_worker(url, output_path)

        if result.get("ok"):
            return result

        print(
            f"⚠️ Worker YouTube KO ({result.get('code')}) "
            f"→ fallback yt-dlp",
            flush=True,
        )

        result = await _download_with_ytdlp(
            url,
            output_path,
            platform="youtube",
        )

        if result.get("ok") and result.get("direct_url"):
            return await _download_via_direct_url(
                result["direct_url"],
                output_path,
                referer="https://www.youtube.com/",
            )

        return result

    # ── Toutes les autres plateformes : tikwm d'abord ────────────
    print(f"🌐 [{platform}] → tentative tikwm", flush=True)

    tikwm_result = await _download_via_tikwm_api(
        url,
        output_path,
        platform=platform,
    )

    if tikwm_result.get("ok"):
        return tikwm_result

    print(
        f"⚠️ tikwm KO [{platform}] "
        f"({tikwm_result.get('code')}) → fallback yt-dlp",
        flush=True,
    )

    # ── Fallback yt-dlp ─────────────────────────────────────────
    ytdlp_result = await _download_with_ytdlp(
        url,
        output_path,
        platform=platform,
    )

    if ytdlp_result.get("ok") and ytdlp_result.get("direct_url"):
        return await _download_via_direct_url(
            ytdlp_result["direct_url"],
            output_path,
            referer=_referer_for_platform(platform, url),
        )

    if ytdlp_result.get("ok"):
        return ytdlp_result

    return {
        "ok": False,
        "code": f"{platform}_download_failed",
        "message": (
            f"Impossible de télécharger cette vidéo depuis {platform}. "
            "Le lien est peut-être privé, protégé, expiré, ou non compatible."
        ),
        "details": {
            "tikwm": tikwm_result.get("code"),
            "ytdlp": ytdlp_result.get("code"),
        },
    }