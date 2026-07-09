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
# Par défaut on le désactive. Tu peux remettre false en local si besoin.
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
    return bool(path and os.path.exists(path) and os.path.getsize(path) > 1000)


def _too_big(path: str) -> bool:
    try:
        return os.path.getsize(path) > MAX_DOWNLOAD_BYTES
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# YOUTUBE — subprocess worker isolé du process principal
# ══════════════════════════════════════════════════════════════

async def _download_youtube_via_worker(url: str, output_path: str) -> Dict[str, Any]:
    """
    Lance youtube_worker.py en subprocess isolé.

    Le worker tente :
      1. yt-dlp android_vr
      2. Invidious API

    Retourne {"ok": True} si le fichier est téléchargé,
    sinon {"ok": False, "code": "...", "message": "..."}.
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
                f"  [youtube_worker stderr] {stderr.decode(errors='ignore')[:400]}",
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
# yt-dlp générique
# ══════════════════════════════════════════════════════════════

async def _download_with_ytdlp(url: str, output_path: str) -> Dict[str, Any]:
    """
    yt-dlp avec répertoire temporaire unique.

    Important :
    - évite les conflits du type :
      temp/7659805933555469600.mp4.part -> temp/7659805933555469600.mp4
      quand plusieurs requêtes touchent la même vidéo ;
    - garde le fichier final uniquement dans output_path.
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
        ]

        last_error = ""

        for strategy in strategies:
            opts = dict(YTDLP_BASE_OPTIONS)
            opts.update(strategy)

            # Téléchargement isolé dans un dossier unique.
            opts["outtmpl"] = os.path.join(temp_dir, "download.%(ext)s")
            opts["cookiefile"] = cookie_file
            opts["max_filesize"] = MAX_DOWNLOAD_BYTES

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
                        if os.path.isfile(candidate) and not candidate.endswith(".part"):
                            downloaded_file = candidate
                            break

                if downloaded_file and _file_ok(downloaded_file):
                    if _too_big(downloaded_file):
                        return {
                            "ok": False,
                            "code": "file_too_large",
                            "message": f"Vidéo trop volumineuse, limite {MAX_DOWNLOAD_MB} Mo.",
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
# TikTok API publique tikwm
# ══════════════════════════════════════════════════════════════

async def _download_tiktok_api(url: str, output_path: str) -> Dict[str, Any]:
    """
    Résout l'URL MP4 via l'API publique tikwm.com, puis télécharge.
    C'est le chemin prioritaire pour TikTok.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            r = await client.get(
                "https://www.tikwm.com/api/",
                params={"url": url, "hd": 1},
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
        play = data.get("hdplay") or data.get("play") or data.get("wmplay")

        if not play:
            return {
                "ok": False,
                "code": "tikwm_no_url",
                "message": "tikwm: pas d'URL vidéo.",
            }

        if play.startswith("/"):
            play = "https://www.tikwm.com" + play

        print("✅ tikwm → URL MP4 obtenue, téléchargement...", flush=True)

        return await _download_via_direct_url(
            play,
            output_path,
            referer="https://www.tiktok.com/",
        )

    except Exception as e:
        return {
            "ok": False,
            "code": "tikwm_error",
            "message": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════
# TikTok Playwright subprocess
# ══════════════════════════════════════════════════════════════

async def _download_tiktok_playwright_subprocess(
    url: str,
    output_path: str,
) -> Dict[str, Any]:
    """
    Playwright dans un worker séparé.

    Sur Render Free, on évite normalement Playwright via DISABLE_PLAYWRIGHT=true.
    """
    if DISABLE_PLAYWRIGHT:
        print("ℹ️ Playwright désactivé sur Render → yt-dlp", flush=True)
        return {
            "ok": False,
            "code": "playwright_disabled",
            "message": "Playwright désactivé.",
        }

    worker_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "playwright_worker.py",
    )

    if not os.path.exists(worker_path):
        return {
            "ok": False,
            "code": "playwright_worker_missing",
            "message": f"playwright_worker.py introuvable à {worker_path}",
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            url,
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)

        if proc.returncode != 0:
            return {
                "ok": False,
                "code": "playwright_subprocess_error",
                "message": (
                    f"Worker Playwright a échoué "
                    f"(exit {proc.returncode}): "
                    f"{stderr.decode(errors='ignore')[:200]}"
                ),
            }

        if not stdout:
            return {
                "ok": False,
                "code": "playwright_worker_no_output",
                "message": "Worker Playwright n'a produit aucune sortie.",
            }

        return json.loads(stdout.decode(errors="ignore"))

    except asyncio.TimeoutError:
        return {
            "ok": False,
            "code": "playwright_timeout",
            "message": "Timeout Playwright après 45s.",
        }

    except json.JSONDecodeError:
        return {
            "ok": False,
            "code": "playwright_worker_output",
            "message": "Réponse JSON invalide du worker Playwright.",
        }

    except Exception as e:
        return {
            "ok": False,
            "code": "playwright_subprocess_error",
            "message": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════
# TikTok Playwright direct local
# ══════════════════════════════════════════════════════════════

async def _download_tiktok_playwright_direct(url: str) -> Dict[str, Any]:
    """
    Playwright direct, plutôt pour tests locaux.

    Sur Render, préfère DISABLE_PLAYWRIGHT=true pour éviter les OOM.
    """
    if DISABLE_PLAYWRIGHT:
        print("ℹ️ Playwright désactivé → yt-dlp", flush=True)
        return {
            "ok": False,
            "code": "playwright_disabled",
            "message": "Playwright désactivé.",
        }

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "ok": False,
            "code": "playwright_missing",
            "message": "Playwright non installé.",
        }

    browser = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                ],
            )

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 10; Pixel 3) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Mobile Safari/537.36"
                )
            )

            page = await context.new_page()

            await page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in (
                        "image",
                        "font",
                        "stylesheet",
                        "media",
                    )
                    else route.continue_()
                ),
            )

            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2500)

            video_url = await page.evaluate(
                """() => {
                    const grab = (root) => {
                        let found = null;

                        const walk = (o) => {
                            if (found || !o || typeof o !== 'object') return;

                            for (const k in o) {
                                const v = o[k];

                                if (
                                    (k === 'playAddr' || k === 'downloadAddr')
                                    && typeof v === 'string'
                                    && v.startsWith('http')
                                ) {
                                    found = v;
                                    return;
                                }

                                if (v && typeof v === 'object') {
                                    walk(v);
                                }
                            }
                        };

                        walk(root);
                        return found;
                    };

                    const el = document.getElementById(
                        '__UNIVERSAL_DATA_FOR_REHYDRATION__'
                    );

                    if (el) {
                        try {
                            const u = grab(JSON.parse(el.textContent));
                            if (u) return u;
                        } catch(e) {}
                    }

                    const og = document.querySelector('meta[property="og:video"]');
                    if (og && og.content) return og.content;

                    const v = document.querySelector('video');
                    if (v && v.src && v.src.startsWith('http')) return v.src;

                    return null;
                }"""
            )

            await context.close()
            await browser.close()
            browser = None

            if video_url:
                return {
                    "ok": True,
                    "direct_url": video_url,
                }

            return {
                "ok": False,
                "code": "no_video_found",
                "message": "Impossible d'extraire l'URL vidéo avec Playwright.",
            }

    except Exception as e:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        return {
            "ok": False,
            "code": "playwright_error",
            "message": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════
# Téléchargement URL directe
# ══════════════════════════════════════════════════════════════

async def _download_via_direct_url(
    direct_url: str,
    output_path: str,
    referer: str = "https://www.youtube.com/",
) -> Dict[str, Any]:
    """
    Télécharge un fichier depuis une URL directe avec httpx streaming.
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
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════

async def download_video(
    url: str,
    output_path: str,
    platform: str = "unknown",
) -> Dict[str, Any]:
    """
    Télécharge une vidéo depuis plusieurs plateformes.

    Cascade YouTube :
      1. youtube_worker.py
      2. yt-dlp direct

    Cascade TikTok :
      1. tikwm
      2. Playwright seulement si DISABLE_PLAYWRIGHT=false
      3. yt-dlp

    Autres plateformes :
      → yt-dlp directement
    """
    _safe_remove(output_path)

    # ── YouTube ──────────────────────────────────────────────────
    if platform == "youtube" or "youtube.com" in url or "youtu.be" in url:
        print("🎬 Téléchargement YouTube via worker subprocess", flush=True)

        result = await _download_youtube_via_worker(url, output_path)

        if result.get("ok"):
            return result

        print(
            f"⚠️ Worker YouTube KO ({result.get('code')}) "
            f"→ fallback yt-dlp direct",
            flush=True,
        )

        result = await _download_with_ytdlp(url, output_path)

        if result.get("ok") and result.get("direct_url"):
            return await _download_via_direct_url(
                result["direct_url"],
                output_path,
                referer="https://www.youtube.com/",
            )

        return result

    # ── TikTok ───────────────────────────────────────────────────
    if platform == "tiktok":
        # 1) API publique tikwm
        api_result = await _download_tiktok_api(url, output_path)

        if api_result.get("ok"):
            return api_result

        print(
            f"⚠️ tikwm KO ({api_result.get('code')})",
            flush=True,
        )

        # 2) Playwright uniquement si autorisé
        if not DISABLE_PLAYWRIGHT:
            print("🎭 Tentative Playwright TikTok", flush=True)

            if IS_RENDER:
                pw = await _download_tiktok_playwright_subprocess(url, output_path)
            else:
                pw = await _download_tiktok_playwright_direct(url)

            if pw and pw.get("ok"):
                if pw.get("downloaded") and _file_ok(output_path):
                    return {"ok": True}

                if pw.get("direct_url"):
                    dl = await _download_via_direct_url(
                        pw["direct_url"],
                        output_path,
                        referer="https://www.tiktok.com/",
                    )

                    if dl.get("ok"):
                        return dl

            print("⚠️ Playwright KO → yt-dlp", flush=True)

        else:
            print("ℹ️ Playwright désactivé → yt-dlp", flush=True)

        # 3) yt-dlp dernier recours
        result = await _download_with_ytdlp(url, output_path)

        if result.get("ok") and result.get("direct_url"):
            return await _download_via_direct_url(
                result["direct_url"],
                output_path,
                referer="https://www.tiktok.com/",
            )

        return result

    # ── Autres plateformes ───────────────────────────────────────
    result = await _download_with_ytdlp(url, output_path)

    if result.get("ok") and result.get("direct_url"):
        return await _download_via_direct_url(
            result["direct_url"],
            output_path,
        )

    return result