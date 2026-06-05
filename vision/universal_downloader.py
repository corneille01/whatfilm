# vision/universal_downloader.py
import os
import sys
import asyncio
import json
import tempfile
from typing import Dict, Any

# ══════════════════════════════════════════════════════════════
# DÉTECTION RENDER (ne bloque rien hors Render)
# ══════════════════════════════════════════════════════════════
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
# FONCTIONS INTERNES
# ══════════════════════════════════════════════════════════════

async def _download_with_ytdlp(url: str, output_path: str) -> Dict[str, Any]:
    """Téléchargement universel via yt-dlp, fallback Playwright pour YouTube."""
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
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
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
            except:
                pass

    # ── Fallback Playwright pour YouTube ──
    if "youtube.com" in url or "youtu.be" in url:
        print("🔄 Fallback YouTube Playwright après échec yt-dlp", flush=True)
        pw_result = await _download_youtube_playwright(url)
        if not pw_result.get("ok"):
            print(f"❌ Playwright a échoué : {pw_result.get('message', 'Erreur inconnue')}", flush=True)
        if pw_result.get("ok") and pw_result.get("direct_url"):
            dl_result = await _download_via_direct_url(pw_result["direct_url"], output_path)
            if dl_result["ok"]:
                return dl_result
            else:
                print(f"❌ Téléchargement direct échoué : {dl_result.get('message')}", flush=True)
                return {"ok": False, "code": "youtube_direct_dl_failed",
                        "message": "Playwright a extrait l'URL mais le téléchargement direct a échoué"}
        else:
            return {"ok": False, "code": "youtube_blocked",
                    "message": f"YouTube bloque l'accès (même avec Playwright). Raison : {pw_result.get('message', 'Échec extraction URL')}"}

    return {"ok": False, "code": "ytdlp_error", "message": last_error}


async def _download_youtube_playwright(url: str) -> Dict[str, Any]:
    """Lance youtube_worker.py avec le même interpréteur Python."""
    worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_worker.py")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, worker_path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode().strip()[:300]
            print(f"❌ youtube_worker.py erreur (exit {proc.returncode}): {err_msg}", flush=True)
            return {"ok": False, "code": "playwright_subprocess_error",
                    "message": f"Le worker YouTube a échoué : {err_msg}"}
        result = json.loads(stdout.decode())
        return result
    except FileNotFoundError:
        return {"ok": False, "code": "youtube_worker_missing",
                "message": f"youtube_worker.py introuvable à {worker_path}"}
    except json.JSONDecodeError:
        return {"ok": False, "code": "playwright_worker_output",
                "message": "Réponse JSON invalide du worker YouTube"}
    except Exception as e:
        return {"ok": False, "code": "playwright_subprocess_error", "message": str(e)[:200]}


async def _download_tiktok_playwright_subprocess(url: str) -> Dict[str, Any]:
    """Sur Render, lance playwright_worker.py en sous‑processus isolé."""
    worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_worker.py")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, worker_path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {"ok": False, "code": "playwright_subprocess_error",
                    "message": f"Worker Playwright a échoué (exit {proc.returncode}): {stderr.decode()[:200]}"}
        result = json.loads(stdout.decode())
        return result
    except FileNotFoundError:
        return {"ok": False, "code": "playwright_worker_missing",
                "message": f"playwright_worker.py introuvable à {worker_path}"}
    except json.JSONDecodeError:
        return {"ok": False, "code": "playwright_worker_output",
                "message": "Réponse JSON invalide du worker Playwright"}
    except Exception as e:
        return {"ok": False, "code": "playwright_subprocess_error", "message": str(e)[:200]}


async def _download_tiktok_playwright_direct(url: str) -> Dict[str, Any]:
    """Utilisation directe de Playwright (hors Render). Retourne une URL directe."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "code": "playwright_missing",
                "message": "Playwright non installé"}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
            )
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort()
                             if route.request.resource_type in ("image", "font", "stylesheet")
                             else route.continue_())
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)
            video_url = None
            try:
                el = await page.query_selector("video")
                if el:
                    video_url = await el.get_attribute("src")
            except:
                pass
            if not video_url:
                try:
                    meta = await page.query_selector('meta[property="og:video"]')
                    if meta:
                        video_url = await meta.get_attribute("content")
                except:
                    pass
            if not video_url:
                try:
                    data = await page.evaluate("() => window.__UNIVERSAL_DATA__ || window.__NEXT_DATA__ || window.__DATA__")
                    if isinstance(data, dict):
                        for key, val in data.items():
                            if isinstance(val, str) and val.startswith("http") and ".mp4" in val:
                                video_url = val
                                break
                except:
                    pass
            await browser.close()
            if video_url:
                return {"ok": True, "direct_url": video_url}
            return {"ok": False, "code": "no_video_found",
                    "message": "Impossible d'extraire l'URL vidéo avec Playwright"}
    except Exception as e:
        return {"ok": False, "code": "playwright_error", "message": str(e)[:200]}


async def _download_via_direct_url(direct_url: str, output_path: str) -> Dict[str, Any]:
    """Télécharge la vidéo à partir d'une URL directe (mp4) avec httpx."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("GET", direct_url) as resp:
                if resp.status_code != 200:
                    return {"ok": False, "code": "direct_download_failed",
                            "message": f"Échec du téléchargement direct (HTTP {resp.status_code})"}
                with open(output_path, 'wb') as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        if os.path.getsize(output_path) > 1000:
            return {"ok": True}
        else:
            return {"ok": False, "code": "direct_download_empty", "message": "Fichier téléchargé vide"}
    except Exception as e:
        return {"ok": False, "code": "direct_download_error", "message": str(e)[:200]}


# ══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE (appelée par app.py)
# ══════════════════════════════════════════════════════════════

async def download_video(url: str, output_path: str, platform: str = "unknown") -> Dict[str, Any]:
    """
    Point d'entrée unique pour télécharger une vidéo.
    Stratégies :
      - TikTok : Playwright (direct ou sous‑processus) puis fallback yt‑dlp
      - Autres plateformes : yt‑dlp (avec contournement + fallback Playwright pour YouTube)
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    if platform == "tiktok":
        playwright_result = None
        if IS_RENDER:
            playwright_result = await _download_tiktok_playwright_subprocess(url)
        else:
            playwright_result = await _download_tiktok_playwright_direct(url)

        if playwright_result and playwright_result.get("ok") and playwright_result.get("direct_url"):
            dl_result = await _download_via_direct_url(playwright_result["direct_url"], output_path)
            if dl_result["ok"]:
                return dl_result

        return await _download_with_ytdlp(url, output_path)

    return await _download_with_ytdlp(url, output_path)