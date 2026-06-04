"""
vision/universal_downloader.py — Téléchargement multi-plateforme robuste.

Cascade TikTok :
  0. Playwright — télécharge DEPUIS le navigateur (pas httpx externe)
  1. yt-dlp cookies navigateur
  2. yt-dlp headers TikTok
  3. yt-dlp API mobile Android
  4. yt-dlp --force-generic-extractor
  5. yt-dlp --get-url + httpx streaming
"""

import os
import re
import asyncio
import subprocess
import httpx

MAX_VIDEO_SECONDS = 120
MAX_FILE_SIZE_MB  = 50

# ════════════════════════════════════════════════════════════════
# USER AGENTS
# ════════════════════════════════════════════════════════════════
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4.1 Mobile/15E148 Safari/604.1"
)
UA_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.6422.165 Mobile Safari/537.36"
)

# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _file_ok(path: str, min_kb: int = 50) -> bool:
    return os.path.exists(path) and os.path.getsize(path) >= min_kb * 1024

def _check_size(path: str) -> dict:
    if not os.path.exists(path):
        return {"ok": False, "code": "download_empty", "message": "Fichier vide ou absent."}
    size_mb = os.path.getsize(path) / 1024 / 1024
    if size_mb > MAX_FILE_SIZE_MB:
        os.remove(path)
        return {"ok": False, "code": "file_too_large",
                "message": f"Fichier trop volumineux ({size_mb:.0f} MB)."}
    if os.path.getsize(path) < 10 * 1024:
        os.remove(path)
        return {"ok": False, "code": "download_empty",
                "message": "Fichier téléchargé trop petit ou corrompu."}
    return {"ok": True}

def _parse_ytdlp_error(stderr: str, stdout: str) -> dict:
    err = (stderr + stdout).lower()
    if "private" in err or "login" in err or "sign in" in err or "age" in err:
        return {"ok": False, "code": "video_private",
                "message": "Cette vidéo est privée ou nécessite une connexion."}
    if "not available" in err or "geo" in err or "country" in err or "region" in err:
        return {"ok": False, "code": "video_geo",
                "message": "Cette vidéo n'est pas disponible dans votre région."}
    if "removed" in err or "deleted" in err or "no longer" in err:
        return {"ok": False, "code": "video_deleted",
                "message": "Cette vidéo a été supprimée ou n'existe plus."}
    if "expired" in err or "story" in err:
        return {"ok": False, "code": "video_expired",
                "message": "Ce contenu a expiré (story ou lien temporaire)."}
    if "copyright" in err or "blocked" in err:
        return {"ok": False, "code": "video_blocked",
                "message": "Cette vidéo est bloquée pour droits d'auteur."}
    if "unsupported url" in err or "no video formats" in err:
        return {"ok": False, "code": "unsupported",
                "message": "Format ou plateforme non supporté."}
    if "too large" in err or "filesize" in err:
        return {"ok": False, "code": "file_too_large",
                "message": "Fichier trop volumineux."}
    if "403" in err or "forbidden" in err:
        return {"ok": False, "code": "forbidden_403",
                "message": "Accès refusé (403). Protection anti-bot active."}
    return {"ok": False, "code": "download_failed",
            "message": "Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique."}

def _base_ytdlp_args(video_path: str, ua: str, timeout_s: int = MAX_VIDEO_SECONDS) -> list:
    return [
        "yt-dlp",
        "--no-playlist",
        "--no-check-certificate",
        "--force-ipv4",
        "--extractor-retries", "2",
        "--retries", "2",
        "--socket-timeout", "15",
        "--download-sections", f"*0-{timeout_s}",
        "--no-warnings",
        "--user-agent", ua,
        "-o", video_path,
    ]

# ════════════════════════════════════════════════════════════════
# STRATÉGIE 0 — Playwright : télécharge DANS le navigateur
# ════════════════════════════════════════════════════════════════
async def _tiktok_strategy_0_playwright(url: str, video_path: str) -> dict:
    """
    Ouvre TikTok dans Chromium headless, intercepte la requête vidéo CDN,
    puis la rejoue VIA fetch() dans le contexte du navigateur (même session,
    mêmes cookies, même token signé) et écrit les bytes dans video_path.

    C'est la seule méthode qui contourne la signature CDN liée à la session.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("⚠️ Playwright non installé — stratégie 0 ignorée", flush=True)
        return {"ok": False, "code": "playwright_missing", "message": "Playwright non disponible."}

    best_url  = None
    best_size = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=UA_MOBILE,
                viewport={"width": 390, "height": 844},
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            )
            page = await context.new_page()

            # ── Interception réseau pour trouver l'URL CDN ───────
            def _handle_response(response):
                nonlocal best_url, best_size
                ct  = response.headers.get("content-type", "")
                cl  = int(response.headers.get("content-length", "0") or 0)
                ru  = response.url
                is_video = "video" in ct or ".mp4" in ru or "mime_type=video" in ru
                is_cdn   = any(d in ru for d in [
                    "tiktokcdn", "tiktok.com", "muscdn",
                    "tiktokv.com", "bytecdn", "snssdk",
                ])
                if is_video and is_cdn and cl > best_size:
                    best_url  = ru
                    best_size = cl
                    print(f"🎬 Vidéo candidate ({cl // 1024}KB): {ru[:70]}", flush=True)

            page.on("response", _handle_response)

            try:
                await page.goto(url, wait_until="networkidle", timeout=45_000)
            except Exception:
                pass  # networkidle peut timeout, la vidéo est souvent déjà interceptée

            await page.evaluate("window.scrollBy(0, 100)")
            await asyncio.sleep(3)

            # ── Fallback : parser le HTML si pas d'interception ──
            if not best_url:
                html = await page.content()
                for pattern in [
                    r'"downloadAddr":"(https?://[^"]+)"',
                    r'"playAddr":"(https?://[^"]+)"',
                    r'"url":"(https?://[^"]+\.mp4[^"]*)"',
                ]:
                    m = re.search(pattern, html)
                    if m:
                        best_url = (
                            m.group(1)
                            .replace(r"\u002F", "/")
                            .replace(r"\/", "/")
                        )
                        print(f"🎬 URL HTML parsée: {best_url[:70]}", flush=True)
                        break

            if not best_url:
                await browser.close()
                return {"ok": False, "code": "playwright_no_url",
                        "message": "Playwright : aucune URL vidéo trouvée."}

            print(f"✅ Playwright URL trouvée, DL dans le navigateur...", flush=True)

            # ── Téléchargement DEPUIS le navigateur (même session) ──
            # On utilise fetch() JS dans la page pour télécharger avec les
            # cookies/tokens de session déjà présents — impossible à faire
            # depuis httpx externe car l'URL est signée pour cette session.
            js_result = await page.evaluate("""
                async (videoUrl) => {
                    try {
                        const resp = await fetch(videoUrl, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'video/webm,video/mp4,video/*;q=0.9,*/*;q=0.8',
                                'Range': 'bytes=0-'
                            }
                        });
                        if (!resp.ok) {
                            return { error: `HTTP ${resp.status}`, bytes: null };
                        }
                        const buffer = await resp.arrayBuffer();
                        // Convertir en tableau d'entiers pour passage JS→Python
                        const uint8 = new Uint8Array(buffer);
                        // Encoder en base64 par blocs pour éviter stack overflow
                        let binary = '';
                        const chunkSize = 8192;
                        for (let i = 0; i < uint8.length; i += chunkSize) {
                            const chunk = uint8.subarray(i, i + chunkSize);
                            binary += String.fromCharCode.apply(null, chunk);
                        }
                        return { error: null, b64: btoa(binary), size: uint8.length };
                    } catch (e) {
                        return { error: e.toString(), bytes: null };
                    }
                }
            """, best_url)

            await browser.close()

            if not js_result or js_result.get("error"):
                err_msg = js_result.get("error", "inconnu") if js_result else "résultat null"
                print(f"⚠️ fetch() JS échoué: {err_msg}", flush=True)
                return {"ok": False, "code": "playwright_fetch_failed",
                        "message": f"fetch() navigateur échoué: {err_msg[:80]}"}

            b64_data = js_result.get("b64", "")
            size_bytes = js_result.get("size", 0)

            if not b64_data or size_bytes < 10_000:
                return {"ok": False, "code": "download_empty",
                        "message": f"Données vidéo trop petites ({size_bytes} bytes)."}

            import base64
            video_bytes = base64.b64decode(b64_data)
            with open(video_path, "wb") as f:
                f.write(video_bytes)

            print(f"📥 Playwright DL OK ({size_bytes // 1024} KB)", flush=True)
            return _check_size(video_path)

    except Exception as e:
        print(f"❌ Playwright erreur: {e}", flush=True)
        return {"ok": False, "code": "playwright_error", "message": str(e)[:120]}


# ════════════════════════════════════════════════════════════════
# STRATÉGIES 1-5 — yt-dlp / httpx
# ════════════════════════════════════════════════════════════════
async def _tiktok_strategy_1_cookies(url: str, video_path: str) -> dict:
    for browser in ("chrome", "firefox", "edge", "chromium", "safari"):
        try:
            cmd = _base_ytdlp_args(video_path, UA_DESKTOP) + [
                "--cookies-from-browser", browser,
                "-f", "best[ext=mp4][filesize<50M]/best[filesize<50M]/best", url,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if r.returncode == 0 and _file_ok(video_path):
                print(f"✅ TikTok cookies {browser} OK", flush=True)
                return {"ok": True}
            if "no such" in r.stderr.lower() or "unable to load" in r.stderr.lower():
                continue
        except (subprocess.TimeoutExpired, Exception):
            pass
    return {"ok": False, "code": "no_browser_cookies",
            "message": "Aucun cookie navigateur disponible."}

async def _tiktok_strategy_2_headers(url: str, video_path: str) -> dict:
    cmd = _base_ytdlp_args(video_path, UA_MOBILE) + [
        "--add-header", "Referer:https://www.tiktok.com/",
        "--add-header", "Origin:https://www.tiktok.com",
        "--add-header", "Sec-Fetch-Site:same-site",
        "--add-header", "Sec-Fetch-Mode:cors",
        "--add-header", "Sec-Fetch-Dest:video",
        "--add-header", "Accept:video/webm,video/ogg,video/*;q=0.9,*/*;q=0.8",
        "--add-header", "Accept-Language:fr-FR,fr;q=0.9,en;q=0.8",
        "-f", "best[ext=mp4][filesize<50M]/best[filesize<50M]/best", url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if r.returncode == 0 and _file_ok(video_path):
            print("✅ TikTok headers OK", flush=True)
            return {"ok": True}
        return _parse_ytdlp_error(r.stderr, r.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "download_timeout", "message": "Timeout."}

async def _tiktok_strategy_3_mobile(url: str, video_path: str) -> dict:
    cmd = _base_ytdlp_args(video_path, UA_ANDROID) + [
        "--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com",
        "--add-header", "Referer:https://www.tiktok.com/",
        "-f", "best[ext=mp4][filesize<50M]/best[filesize<50M]/best", url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if r.returncode == 0 and _file_ok(video_path):
            print("✅ TikTok mobile API OK", flush=True)
            return {"ok": True}
        return _parse_ytdlp_error(r.stderr, r.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "download_timeout", "message": "Timeout."}

async def _tiktok_strategy_4_generic(url: str, video_path: str) -> dict:
    resolved_url = url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10,
                                     headers={"User-Agent": UA_MOBILE}) as client:
            resp = await client.head(url)
            resolved_url = str(resp.url)
            print(f"🔗 TikTok résolu: {resolved_url[:80]}", flush=True)
    except Exception:
        pass

    cmd = _base_ytdlp_args(video_path, UA_DESKTOP) + [
        "--force-generic-extractor", "-f", "best", resolved_url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if r.returncode == 0 and _file_ok(video_path):
            print("✅ TikTok generic extractor OK", flush=True)
            return {"ok": True}
        return _parse_ytdlp_error(r.stderr, r.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "download_timeout", "message": "Timeout."}

async def _tiktok_strategy_5_httpx(url: str, video_path: str) -> dict:
    cmd_geturl = [
        "yt-dlp", "--no-playlist", "--no-check-certificate",
        "--get-url", "--user-agent", UA_MOBILE,
        "--add-header", "Referer:https://www.tiktok.com/",
        "-f", "best[ext=mp4]/best", url,
    ]
    direct_url = None
    try:
        r = subprocess.run(cmd_geturl, capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            direct_url = r.stdout.strip().split("\n")[0]
            print(f"🔗 URL directe: {direct_url[:80]}", flush=True)
    except Exception as e:
        print(f"⚠️ get-url KO: {e}", flush=True)

    if not direct_url:
        return {"ok": False, "code": "no_direct_url",
                "message": "Impossible d'obtenir l'URL directe."}

    headers = {
        "User-Agent":      UA_MOBILE,
        "Referer":         "https://www.tiktok.com/",
        "Origin":          "https://www.tiktok.com",
        "Accept":          "video/webm,video/mp4,video/*;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest":  "video",
        "Sec-Fetch-Mode":  "no-cors",
        "Sec-Fetch-Site":  "cross-site",
        "Range":           "bytes=0-",
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10, read=60, write=10, pool=5),
            headers=headers,
        ) as client:
            async with client.stream("GET", direct_url) as resp:
                if resp.status_code not in (200, 206):
                    return {"ok": False, "code": "forbidden_403",
                            "message": f"CDN refusé ({resp.status_code})."}
                written = 0
                with open(video_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65_536):
                        f.write(chunk)
                        written += len(chunk)
                        if written > MAX_FILE_SIZE_MB * 1024 * 1024:
                            break
        if _file_ok(video_path):
            print(f"✅ TikTok httpx direct OK ({written // 1024} KB)", flush=True)
            return {"ok": True}
        return {"ok": False, "code": "download_empty", "message": "Fichier DL vide."}
    except httpx.TimeoutException:
        return {"ok": False, "code": "download_timeout", "message": "Timeout httpx."}
    except Exception as e:
        return {"ok": False, "code": "download_failed", "message": f"Erreur: {str(e)[:80]}"}


# ════════════════════════════════════════════════════════════════
# ORCHESTRATEUR TIKTOK
# ════════════════════════════════════════════════════════════════
_FATAL_CODES = frozenset({
    "video_private", "video_deleted", "video_geo",
    "video_expired", "video_blocked", "unsupported",
})

async def _download_tiktok(url: str, video_path: str) -> dict:
    strategies = [
        ("Playwright fetch()",  _tiktok_strategy_0_playwright),
        ("yt-dlp cookies",      _tiktok_strategy_1_cookies),
        ("yt-dlp headers",      _tiktok_strategy_2_headers),
        ("yt-dlp API mobile",   _tiktok_strategy_3_mobile),
        ("yt-dlp generic",      _tiktok_strategy_4_generic),
        ("httpx direct CDN",    _tiktok_strategy_5_httpx),
    ]

    last_error = None
    for name, strategy in strategies:
        if os.path.exists(video_path):
            os.remove(video_path)

        print(f"⏳ TikTok [{name}]...", flush=True)
        try:
            result = await strategy(url, video_path)
        except Exception as e:
            print(f"⚠️ [{name}] exception: {e}", flush=True)
            result = {"ok": False, "code": "unexpected", "message": str(e)}

        if result.get("ok"):
            check = _check_size(video_path)
            if check["ok"]:
                print(f"✅ TikTok OK via [{name}]", flush=True)
                return {"ok": True}
            last_error = check
            continue

        if result.get("code") in _FATAL_CODES:
            return result  # inutile d'essayer d'autres stratégies

        last_error = result
        print(f"⚠️ [{name}] KO ({result.get('code')}): "
              f"{result.get('message', '')[:60]}", flush=True)

    return last_error or {
        "ok": False, "code": "download_failed",
        "message": (
            "Impossible de télécharger cette vidéo TikTok après 6 tentatives. "
            "Elle est peut-être privée, expirée ou géo-bloquée."
        ),
    }


# ════════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT GÉNÉRIQUE (non-TikTok)
# ════════════════════════════════════════════════════════════════
async def _download_generic(url: str, video_path: str, platform: str) -> dict:
    ua_map = {
        "instagram": UA_MOBILE,
        "youtube":   UA_DESKTOP,
        "twitter":   UA_DESKTOP,
        "facebook":  UA_DESKTOP,
        "vimeo":     UA_DESKTOP,
        "reddit":    UA_DESKTOP,
    }
    ua = ua_map.get(platform, UA_DESKTOP)

    extra = []
    if platform == "instagram":
        extra = ["--add-header", "Referer:https://www.instagram.com/",
                 "--add-header", "Origin:https://www.instagram.com"]
    elif platform == "twitter":
        extra = ["--add-header", "Referer:https://twitter.com/"]

    cmd = _base_ytdlp_args(video_path, ua) + extra + [
        "-f", "best[ext=mp4][filesize<50M]/best[filesize<50M]/best", url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and _file_ok(video_path):
            return _check_size(video_path)

        error = _parse_ytdlp_error(r.stderr, r.stdout)

        # Fallback cookies Instagram
        if platform == "instagram" and error.get("code") in ("download_failed", "forbidden_403"):
            print("⏳ Instagram fallback cookies...", flush=True)
            for browser in ("chrome", "firefox"):
                cmd2 = _base_ytdlp_args(video_path, ua) + [
                    "--cookies-from-browser", browser,
                    "-f", "best[ext=mp4][filesize<50M]/best[filesize<50M]/best", url,
                ]
                try:
                    r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=45)
                    if r2.returncode == 0 and _file_ok(video_path):
                        print(f"✅ Instagram cookies {browser} OK", flush=True)
                        return _check_size(video_path)
                except Exception:
                    pass

        return error

    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "download_timeout",
                "message": "Téléchargement trop lent. Réessayez dans quelques instants."}
    except Exception as e:
        return {"ok": False, "code": "unexpected", "message": str(e)[:100]}


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ════════════════════════════════════════════════════════════════
async def download_video(url: str, video_path: str, platform: str) -> dict:
    """
    Télécharge une vidéo depuis n'importe quelle plateforme supportée.
    Returns: {"ok": True} ou {"ok": False, "code": str, "message": str}
    """
    os.makedirs(
        os.path.dirname(video_path) if os.path.dirname(video_path) else ".",
        exist_ok=True,
    )
    print(f"⬇️ Download [{platform}]: {url[:80]}", flush=True)

    if platform == "tiktok":
        return await _download_tiktok(url, video_path)
    return await _download_generic(url, video_path, platform)