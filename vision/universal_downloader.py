# vision/universal_downloader.py — PATCH 2026-06
# Fix TikTok : yt-dlp seul ne suffit plus → on injecte des headers
# spécifiques et on utilise --extractor-args pour contourner le blocage.
# Headers TikTok plus complets

import os
import re
import asyncio
import subprocess
import tempfile
from typing import Optional

MAX_SECONDS  = 120
MAX_SIZE_MB  = 50
MIN_SIZE_B   = 1000

UA = {
    "mobile":  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
               "AppleWebKit/605.1.15 (KHTML, like Gecko) "
               "Version/17.4.1 Mobile/15E148 Safari/604.1",
    "desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36",
    "android": "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Mobile Safari/537.36",
    # TikTok app UA — contourne certains blocages serveur
    "tiktok_app": "TikTok 35.1.3 rv:351303 (iPhone; iOS 17.4.1; en_US) "
                  "Cronet",
}

def _ok() -> dict:
    return {"ok": True}

def _err(code: str, msg: str) -> dict:
    return {"ok": False, "code": code, "message": msg}

def _parse_ytdlp_error(stderr: str) -> dict:
    e = stderr.lower()
    if "private" in e or "login" in e or "sign in" in e or "authenticate" in e:
        return _err("video_private", "Cette vidéo est privée ou nécessite une connexion.")
    if "geo" in e or "not available in your country" in e or "region" in e:
        return _err("video_geo", "Cette vidéo n'est pas disponible dans votre région.")
    if "removed" in e or "deleted" in e or "no longer available" in e:
        return _err("video_deleted", "Cette vidéo a été supprimée ou n'existe plus.")
    if "expired" in e or "story" in e:
        return _err("video_expired", "Ce contenu a expiré.")
    if "copyright" in e or "blocked" in e or "takedown" in e:
        return _err("video_blocked", "Cette vidéo est bloquée pour droits d'auteur.")
    if "unsupported url" in e or "no video formats" in e or "no suitable" in e:
        return _err("unsupported", "Format ou plateforme non supporté.")
    if "too large" in e or "filesize" in e:
        return _err("file_too_large", "Fichier trop volumineux.")
    if "rate" in e and "limit" in e:
        return _err("rate_limited", "Trop de requêtes. Réessayez dans quelques minutes.")
    return _err("download_failed",
                "Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique.")

def _ytdlp_base(url: str, out: str, ua: str,
                extra_args: Optional[list] = None) -> list:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-check-certificate",
        "--force-ipv4",
        "--extractor-retries", "3",
        "--retries", "3",
        "--socket-timeout", "20",
        "--download-sections", f"*0-{MAX_SECONDS}",
        "--no-warnings",
        "--user-agent", ua,
        "-f", f"best[ext=mp4][filesize<{MAX_SIZE_MB}M]"
              f"/best[filesize<{MAX_SIZE_MB}M]/best",
        "-o", out,
    ]
    if extra_args:
        cmd += extra_args
    cmd.append(url)
    return cmd

def _run(cmd: list, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def _check_file(path: str) -> bool:
    return (os.path.exists(path)
            and os.path.getsize(path) >= MIN_SIZE_B
            and os.path.getsize(path) <= MAX_SIZE_MB * 1024 * 1024)


# ════════════════════════════════════════════════════════════════
# TIKTOK — stratégie 2026 complète
# ════════════════════════════════════════════════════════════════



async def _dl_tiktok(url: str, out: str) -> dict:
    """
    TikTok 2026 — 3 stratégies dans l'ordre :
    1. yt-dlp + webpage_download + headers Referer/Origin
    2. yt-dlp + cookies (si fichier présent)
    3. tiktok_downloader.download_tiktok_direct (Playwright + httpx avec bons headers)
    """

    # ── Stratégie 1 : yt-dlp webpage_download ───────────────────
    try:
        cmd = _ytdlp_base(url, out, UA["mobile"], [
            "--extractor-args", "tiktok:webpage_download=true",
            "--add-header", "Referer:https://www.tiktok.com/",
            "--add-header", "Origin:https://www.tiktok.com",
        ])
        r = _run(cmd, timeout=60)
        if r.returncode == 0 and _check_file(out):
            print("✅ TikTok strat 1 OK", flush=True)
            return _ok()
        err = _parse_ytdlp_error(r.stderr + r.stdout)
        if err["code"] in ("video_private", "video_deleted",
                           "video_expired", "video_geo"):
            return err   # erreur définitive → inutile de réessayer
    except subprocess.TimeoutExpired:
        print("⚠️ TikTok strat 1 timeout", flush=True)

    # ── Stratégie 2 : yt-dlp + cookies ──────────────────────────
    cookies_path = os.environ.get("TIKTOK_COOKIES_PATH", "")
    if not cookies_path:
        cookies_path = "/app/cookies/tiktok_cookies.txt"
    if os.path.exists(cookies_path):
        try:
            cmd = _ytdlp_base(url, out, UA["mobile"], [
                "--cookies", cookies_path,
                "--add-header", "Referer:https://www.tiktok.com/",
            ])
            r = _run(cmd, timeout=60)
            if r.returncode == 0 and _check_file(out):
                print("✅ TikTok strat 2 (cookies) OK", flush=True)
                return _ok()
        except subprocess.TimeoutExpired:
            print("⚠️ TikTok strat 2 timeout", flush=True)

    # ── Stratégie 3 : Playwright + httpx avec bons headers ──────
    # C'est votre tiktok_downloader.py — mais on utilise maintenant
    # download_tiktok_direct() qui injecte les headers corrects.
    try:
        from vision.tiktok_downloader import download_tiktok_direct
        success = await download_tiktok_direct(url, out)
        if success and _check_file(out):
            print("✅ TikTok strat 3 (Playwright+httpx) OK", flush=True)
            return _ok()
    except ImportError:
        print("⚠️ tiktok_downloader non trouvé", flush=True)
    except Exception as e:
        print(f"⚠️ TikTok strat 3: {e}", flush=True)

    return _err("download_failed",
                "Impossible de télécharger cette vidéo TikTok. "
                "Elle est peut-être privée, expirée ou géo-bloquée.")


# ── Toutes les autres plateformes — identiques à votre version ──

async def _dl_instagram(url: str, out: str) -> dict:
    url_reel = re.sub(r"/p/([A-Za-z0-9_-]+)", r"/reel/\1", url)
    for attempt_url in [url_reel, url]:
        try:
            r = _run(_ytdlp_base(attempt_url, out, UA["mobile"]))
            if r.returncode == 0 and _check_file(out):
                return _ok()
            err = _parse_ytdlp_error(r.stderr + r.stdout)
            if err["code"] in ("video_private", "video_expired"):
                return err
        except subprocess.TimeoutExpired:
            continue
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=UA["mobile"])
            page = await ctx.new_page()
            video_url = None
            async def intercept(response):
                nonlocal video_url
                ct = response.headers.get("content-type", "")
                if "video" in ct and not video_url:
                    video_url = response.url
            page.on("response", intercept)
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(4000)
            await browser.close()
            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=30) as c:
                    resp = await c.get(video_url, headers={"User-Agent": UA["mobile"]})
                    with open(out, "wb") as f:
                        f.write(resp.content)
                if _check_file(out):
                    return _ok()
    except Exception as e:
        print(f"⚠️ Instagram Playwright: {e}", flush=True)
    return _err("download_failed",
                "Impossible de télécharger ce contenu Instagram.")


async def _dl_facebook(url: str, out: str) -> dict:
    for ua in [UA["desktop"], UA["mobile"]]:
        try:
            r = _run(_ytdlp_base(url, out, ua))
            if r.returncode == 0 and _check_file(out):
                return _ok()
            err = _parse_ytdlp_error(r.stderr + r.stdout)
            if err["code"] in ("video_private", "video_deleted"):
                return err
        except subprocess.TimeoutExpired:
            continue
    return _err("download_failed", "Impossible de télécharger cette vidéo Facebook.")


async def _dl_twitter(url: str, out: str) -> dict:
    url_tw = url.replace("x.com", "twitter.com")
    for u in [url_tw, url]:
        try:
            r = _run(_ytdlp_base(u, out, UA["desktop"]))
            if r.returncode == 0 and _check_file(out):
                return _ok()
        except subprocess.TimeoutExpired:
            continue
    return _err("download_failed", "Impossible de télécharger cette vidéo Twitter/X.")


async def _dl_reddit(url: str, out: str) -> dict:
    url_full = re.sub(r"redd\.it/([a-z0-9]+)", r"reddit.com/\1", url)
    try:
        r = _run(_ytdlp_base(url_full, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
    except subprocess.TimeoutExpired:
        pass
    return _err("download_failed", "Impossible de télécharger cette vidéo Reddit.")


async def _dl_snapchat(url: str, out: str) -> dict:
    try:
        r = _run(_ytdlp_base(url, out, UA["mobile"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
    except subprocess.TimeoutExpired:
        pass
    return _err("download_failed", "Impossible de télécharger ce Snap.")


async def _dl_youtube(url: str, out: str) -> dict:
    url_norm = re.sub(r"youtube\.com/shorts/([^?&]+)",
                      r"youtube.com/watch?v=\1", url)
    try:
        r = _run(_ytdlp_base(url_norm, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement YouTube trop lent.")


async def _dl_dailymotion(url: str, out: str) -> dict:
    url_dm = re.sub(r"dai\.ly/([a-zA-Z0-9]+)",
                    r"dailymotion.com/video/\1", url)
    try:
        r = _run(_ytdlp_base(url_dm, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Dailymotion trop lent.")


async def _dl_vimeo(url: str, out: str) -> dict:
    try:
        r = _run(_ytdlp_base(url, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Vimeo trop lent.")


async def _dl_bilibili(url: str, out: str) -> dict:
    try:
        r = _run(_ytdlp_base(url, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Bilibili trop lent.")


async def _dl_generic(url: str, out: str) -> dict:
    for ua in [UA["desktop"], UA["mobile"]]:
        try:
            r = _run(_ytdlp_base(url, out, ua))
            if r.returncode == 0 and _check_file(out):
                return _ok()
        except subprocess.TimeoutExpired:
            continue
    return _err("unsupported_platform",
                "Cette plateforme n'est pas supportée.")


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE UNIQUE
# ════════════════════════════════════════════════════════════════
async def download_video(url: str, out_path: str, platform: str) -> dict:
    print(f"⬇️  Download [{platform}]: {url[:70]}", flush=True)
    router = {
        "tiktok":      _dl_tiktok,
        "instagram":   _dl_instagram,
        "facebook":    _dl_facebook,
        "twitter":     _dl_twitter,
        "youtube":     _dl_youtube,
        "reddit":      _dl_reddit,
        "snapchat":    _dl_snapchat,
        "dailymotion": _dl_dailymotion,
        "vimeo":       _dl_vimeo,
        "bilibili":    _dl_bilibili,
    }
    fn = router.get(platform, _dl_generic)
    try:
        result = await fn(url, out_path)
        if result["ok"]:
            mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"✅ Download OK ({mb:.1f} MB)", flush=True)
        else:
            print(f"❌ Download KO [{result['code']}]: {result['message']}", flush=True)
        return result
    except Exception as e:
        print(f"❌ Download exception: {e}", flush=True)
        return _err("unexpected", "Erreur inattendue lors du téléchargement.")