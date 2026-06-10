# vision/universal_downloader.py
import os
import sys
import asyncio
import json
import tempfile
from typing import Dict, Any

IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))

YTDLP_BASE_OPTIONS = {
    "format": "mp4/best",
    "outtmpl": "%(id)s.%(ext)s",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "socket_timeout": 30,
    "retries": 2,
    "headers": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36"
    },
}

# ══════════════════════════════════════════════════════════════
# YOUTUBE — subprocess worker (isolé du process principal)
# ══════════════════════════════════════════════════════════════

async def _download_youtube_via_worker(url: str, output_path: str) -> Dict[str, Any]:
    """
    Lance youtube_worker.py en subprocess isolé.
    Le worker tente : yt-dlp android_vr → Invidious API.
    Retourne {"ok": True} si le fichier est téléchargé, sinon {"ok": False, ...}.
    """
    worker_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "youtube_worker.py"
    )
    if not os.path.exists(worker_path):
        return {"ok": False, "code": "worker_missing",
                "message": f"youtube_worker.py introuvable à {worker_path}"}

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, worker_path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)

        if stderr:
            print(f"  [youtube_worker stderr] {stderr.decode()[:400]}", flush=True)

        if not stdout:
            return {"ok": False, "code": "worker_no_output",
                    "message": "Worker YouTube n'a produit aucune sortie"}

        worker_result = json.loads(stdout.decode())

    except asyncio.TimeoutError:
        return {"ok": False, "code": "worker_timeout",
                "message": "Timeout worker YouTube (45s)"}
    except json.JSONDecodeError as e:
        return {"ok": False, "code": "worker_json_error",
                "message": f"JSON invalide du worker: {e}"}
    except Exception as e:
        return {"ok": False, "code": "worker_exception",
                "message": str(e)[:200]}

    if not worker_result.get("ok"):
        print(f"⚠️ Worker YouTube KO: {worker_result.get('message', '')}", flush=True)
        return worker_result

    direct_url = worker_result.get("direct_url", "")
    if not direct_url:
        return {"ok": False, "code": "worker_no_url",
                "message": "Worker YouTube n'a pas retourné d'URL directe"}

    print(f"✅ Worker YouTube → URL directe obtenue, téléchargement...", flush=True)
    return await _download_via_direct_url(direct_url, output_path)


# ══════════════════════════════════════════════════════════════
# yt-dlp générique (plateformes non-YouTube)
# ══════════════════════════════════════════════════════════════

async def _download_with_ytdlp(url: str, output_path: str) -> Dict[str, Any]:
    """yt-dlp avec stratégies multiples (utilisé pour non-YouTube ou fallback final)."""
    try:
        import yt_dlp
    except ImportError:
        return {"ok": False, "code": "yt_dlp_missing", "message": "yt-dlp non installé"}

    cookie_file = os.path.join(tempfile.gettempdir(), "yt_consent_cookies.txt")
    with open(cookie_file, "w") as f:
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
    ]

    last_error = ""

    for strategy in strategies:
        opts = YTDLP_BASE_OPTIONS.copy()
        opts["outtmpl"] = os.path.join(os.path.dirname(output_path), "%(id)s.%(ext)s")
        opts["cookiefile"] = cookie_file
        opts.update(strategy)

        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = await loop.run_in_executor(
                    None, lambda: ydl.extract_info(url, download=True)
                )
                if info and "requested_downloads" in info:
                    downloaded_file = info["requested_downloads"][0]["filepath"]
                    if downloaded_file != output_path:
                        os.rename(downloaded_file, output_path)
                    return {"ok": True}
                elif info and info.get("url"):
                    return {"ok": True, "direct_url": info["url"]}
                else:
                    last_error = "Aucun flux trouvé"
        except Exception as e:
            last_error = str(e)[:200]
            continue
        finally:
            try:
                if os.path.exists(cookie_file):
                    os.remove(cookie_file)
            except Exception:
                pass

    return {"ok": False, "code": "ytdlp_error", "message": last_error}


# ══════════════════════════════════════════════════════════════
# TikTok
# ══════════════════════════════════════════════════════════════

async def _download_tiktok_playwright_subprocess(url: str) -> Dict[str, Any]:
    worker_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "playwright_worker.py"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, worker_path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {
                "ok": False, "code": "playwright_subprocess_error",
                "message": f"Worker Playwright a échoué (exit {proc.returncode}): "
                           f"{stderr.decode()[:200]}",
            }
        return json.loads(stdout.decode())
    except FileNotFoundError:
        return {"ok": False, "code": "playwright_worker_missing",
                "message": f"playwright_worker.py introuvable à {worker_path}"}
    except json.JSONDecodeError:
        return {"ok": False, "code": "playwright_worker_output",
                "message": "Réponse JSON invalide du worker Playwright"}
    except Exception as e:
        return {"ok": False, "code": "playwright_subprocess_error",
                "message": str(e)[:200]}


async def _download_tiktok_playwright_direct(url: str) -> Dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "code": "playwright_missing",
                "message": "Playwright non installé"}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 10; Pixel 3) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/90.0.4430.91 Mobile Safari/537.36"
                )
            )
            page = await context.new_page()
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "font", "stylesheet")
                else route.continue_(),
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)

            video_url = None
            try:
                el = await page.query_selector("video")
                if el:
                    video_url = await el.get_attribute("src")
            except Exception:
                pass

            if not video_url:
                try:
                    meta = await page.query_selector('meta[property="og:video"]')
                    if meta:
                        video_url = await meta.get_attribute("content")
                except Exception:
                    pass

            if not video_url:
                try:
                    data = await page.evaluate(
                        "() => window.__UNIVERSAL_DATA__ "
                        "|| window.__NEXT_DATA__ || window.__DATA__"
                    )
                    if isinstance(data, dict):
                        for val in data.values():
                            if isinstance(val, str) and val.startswith("http") \
                                    and ".mp4" in val:
                                video_url = val
                                break
                except Exception:
                    pass

            await browser.close()

            if video_url:
                return {"ok": True, "direct_url": video_url}
            return {"ok": False, "code": "no_video_found",
                    "message": "Impossible d'extraire l'URL vidéo avec Playwright"}
    except Exception as e:
        return {"ok": False, "code": "playwright_error", "message": str(e)[:200]}


# ══════════════════════════════════════════════════════════════
# Téléchargement URL directe
# ══════════════════════════════════════════════════════════════

async def _download_via_direct_url(direct_url: str, output_path: str) -> Dict[str, Any]:
    """Télécharge un fichier depuis une URL directe (httpx streaming)."""
    try:
        import httpx
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10; K) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.6367.82 Mobile Safari/537.36"
                ),
                "Referer": "https://www.youtube.com/",
            },
        ) as client:
            async with client.stream("GET", direct_url) as resp:
                if resp.status_code != 200:
                    return {
                        "ok": False, "code": "direct_download_failed",
                        "message": f"Échec du téléchargement direct (HTTP {resp.status_code})",
                    }
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

        size = os.path.getsize(output_path)
        if size > 1000:
            return {"ok": True}
        return {"ok": False, "code": "direct_download_empty",
                "message": f"Fichier téléchargé trop petit ({size} octets)"}
    except Exception as e:
        return {"ok": False, "code": "direct_download_error", "message": str(e)[:200]}


# ══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════

async def download_video(url: str, output_path: str, platform: str = "unknown") -> Dict[str, Any]:
    """
    Télécharge une vidéo depuis n'importe quelle plateforme.

    Cascade YouTube :
      1. youtube_worker.py (subprocess isolé)
         → yt-dlp android_vr (sans cookies)
         → Invidious API (4 instances)
      2. yt-dlp direct en fallback ultime

    Cascade TikTok :
      1. playwright_worker.py (subprocess isolé sur Render)
         ou Playwright direct (local)
      2. yt-dlp

    Autres plateformes :
      → yt-dlp directement
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    # ── YouTube ──────────────────────────────────────────────────
    if platform == "youtube" or "youtube.com" in url or "youtu.be" in url:
        print("🎬 Téléchargement YouTube via worker subprocess", flush=True)

        result = await _download_youtube_via_worker(url, output_path)
        if result["ok"]:
            return result

        # Fallback ultime : yt-dlp direct (fonctionne parfois hors Render)
        print(
            f"⚠️ Worker YouTube KO ({result.get('code')}) "
            f"→ fallback yt-dlp direct",
            flush=True,
        )
        return await _download_with_ytdlp(url, output_path)

    # ── TikTok ───────────────────────────────────────────────────
    if platform == "tiktok":
        playwright_result = None
        if IS_RENDER:
            playwright_result = await _download_tiktok_playwright_subprocess(url)
        else:
            playwright_result = await _download_tiktok_playwright_direct(url)

        if playwright_result and playwright_result.get("ok") \
                and playwright_result.get("direct_url"):
            dl_result = await _download_via_direct_url(
                playwright_result["direct_url"], output_path
            )
            if dl_result["ok"]:
                return dl_result

        return await _download_with_ytdlp(url, output_path)

    # ── Autres plateformes ───────────────────────────────────────
    return await _download_with_ytdlp(url, output_path)