# vision/universal_downloader.py
# Downloader universel — stratégies adaptées par plateforme
#
# Ordre de tentative par plateforme :
#   1. yt-dlp avec cookies/user-agent adaptés
#   2. Playwright (navigateur headless) pour les sites anti-bot
#   3. API officielle si disponible (Reddit, Twitter)
#
# Toutes les plateformes téléchargent MAX 60s de vidéo.

import os
import re
import asyncio
import subprocess
import tempfile
from typing import Optional

MAX_SECONDS  = 60
MAX_SIZE_MB  = 50
MIN_SIZE_B   = 1000

# ── User-agents par plateforme ────────────────────────────────────
UA = {
    "mobile":  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
               "AppleWebKit/605.1.15 (KHTML, like Gecko) "
               "Version/17.0 Mobile/15E148 Safari/604.1",
    "desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/120.0.0.0 Safari/537.36",
    "android": "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/120.0.0.0 Mobile Safari/537.36",
}

# ── Résultat standard ─────────────────────────────────────────────
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
        return _err("video_expired", "Ce contenu a expiré (story ou lien temporaire).")
    if "copyright" in e or "blocked" in e or "takedown" in e:
        return _err("video_blocked", "Cette vidéo est bloquée pour droits d'auteur.")
    if "unsupported url" in e or "no video formats" in e or "no suitable" in e:
        return _err("unsupported", "Format ou plateforme non supporté.")
    if "too large" in e or "filesize" in e:
        return _err("file_too_large", "Fichier trop volumineux. Essayez une vidéo plus courte.")
    if "rate" in e and "limit" in e:
        return _err("rate_limited", "Trop de requêtes. Réessayez dans quelques minutes.")
    return _err("download_failed",
                "Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique.")

def _ytdlp_base(url: str, out: str, ua: str,
                extra_args: Optional[list] = None) -> list:
    """Construit la commande yt-dlp de base."""
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
# STRATÉGIES PAR PLATEFORME
# ════════════════════════════════════════════════════════════════

async def _dl_tiktok(url: str, out: str) -> dict:
    """
    TikTok : yt-dlp mobile UA → Playwright fallback.
    TikTok bloque agressivement les bots → on simule un iPhone.
    """
    # Tentative 1 : yt-dlp avec UA mobile
    try:
        r = _run(_ytdlp_base(url, out, UA["mobile"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
    except subprocess.TimeoutExpired:
        pass

    # Tentative 2 : yt-dlp avec cookies navigateur (si dispo)
    try:
        r = _run(_ytdlp_base(url, out, UA["mobile"],
                             ["--cookies-from-browser", "chrome"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
    except Exception:
        pass

    # Tentative 3 : Playwright (navigateur headless complet)
    try:
        from vision.tiktok_downloader import get_tiktok_video_url
        import httpx
        video_url = await get_tiktok_video_url(url)
        async with httpx.AsyncClient(timeout=30,
                                     headers={"User-Agent": UA["mobile"]}) as c:
            resp = await c.get(video_url)
            with open(out, "wb") as f:
                f.write(resp.content)
        if _check_file(out):
            return _ok()
    except Exception as e:
        print(f"⚠️ TikTok Playwright: {e}", flush=True)

    return _err("download_failed",
                "Impossible de télécharger cette vidéo TikTok. "
                "Elle est peut-être privée ou géo-bloquée.")


async def _dl_instagram(url: str, out: str) -> dict:
    """
    Instagram : Reels, Posts, Stories.
    Nécessite souvent des cookies → on essaie sans d'abord.
    """
    # Réécrire /p/ en /reel/ si nécessaire (même contenu, meilleur support)
    url_reel = re.sub(r"/p/([A-Za-z0-9_-]+)", r"/reel/\1", url)

    for attempt_url in [url_reel, url]:
        try:
            r = _run(_ytdlp_base(attempt_url, out, UA["mobile"]))
            if r.returncode == 0 and _check_file(out):
                return _ok()
            err = _parse_ytdlp_error(r.stderr + r.stdout)
            # Si privé ou login → inutile de réessayer
            if err["code"] in ("video_private", "video_expired"):
                return err
        except subprocess.TimeoutExpired:
            continue

    # Fallback Playwright
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
                    resp = await c.get(video_url,
                                      headers={"User-Agent": UA["mobile"]})
                    with open(out, "wb") as f:
                        f.write(resp.content)
                if _check_file(out):
                    return _ok()
    except Exception as e:
        print(f"⚠️ Instagram Playwright: {e}", flush=True)

    return _err("download_failed",
                "Impossible de télécharger ce contenu Instagram. "
                "Les Reels privés ou les Stories expirées ne sont pas accessibles.")


async def _dl_facebook(url: str, out: str) -> dict:
    """
    Facebook : Videos, Reels, Watch.
    fb.watch → résoudre d'abord en URL complète.
    """
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

    # Playwright fallback
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=UA["desktop"])
            page = await ctx.new_page()

            video_url = None
            async def intercept(response):
                nonlocal video_url
                ct = response.headers.get("content-type", "")
                if "video" in ct and "mp4" in response.url and not video_url:
                    video_url = response.url

            page.on("response", intercept)
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(5000)
            await browser.close()

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=30) as c:
                    resp = await c.get(video_url)
                    with open(out, "wb") as f:
                        f.write(resp.content)
                if _check_file(out):
                    return _ok()
    except Exception as e:
        print(f"⚠️ Facebook Playwright: {e}", flush=True)

    return _err("download_failed",
                "Impossible de télécharger cette vidéo Facebook. "
                "Les vidéos privées ou de groupes fermés ne sont pas accessibles.")


async def _dl_twitter(url: str, out: str) -> dict:
    """
    Twitter/X : Videos dans les tweets.
    yt-dlp fonctionne bien avec le bon UA.
    """
    # Normaliser x.com → twitter.com (meilleur support yt-dlp)
    url_tw = url.replace("x.com", "twitter.com")

    try:
        r = _run(_ytdlp_base(url_tw, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        err = _parse_ytdlp_error(r.stderr + r.stdout)
        if err["code"] != "download_failed":
            return err
    except subprocess.TimeoutExpired:
        pass

    # Fallback avec URL originale x.com
    if url != url_tw:
        try:
            r = _run(_ytdlp_base(url, out, UA["desktop"]))
            if r.returncode == 0 and _check_file(out):
                return _ok()
        except subprocess.TimeoutExpired:
            pass

    return _err("download_failed",
                "Impossible de télécharger cette vidéo Twitter/X. "
                "Les tweets privés ou supprimés ne sont pas accessibles.")


async def _dl_reddit(url: str, out: str) -> dict:
    """
    Reddit : Videos Reddit (v.redd.it) et Gfycat/Imgur embarqués.
    v.redd.it a l'audio séparé — yt-dlp le gère automatiquement.
    """
    # Normaliser redd.it → reddit.com
    url_full = re.sub(r"redd\.it/([a-z0-9]+)", r"reddit.com/\1", url)

    try:
        r = _run(_ytdlp_base(url_full, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        err = _parse_ytdlp_error(r.stderr + r.stdout)
        if err["code"] != "download_failed":
            return err
    except subprocess.TimeoutExpired:
        pass

    return _err("download_failed",
                "Impossible de télécharger cette vidéo Reddit. "
                "Les posts supprimés ou de subreddits privés ne sont pas accessibles.")


async def _dl_snapchat(url: str, out: str) -> dict:
    """
    Snapchat Spotlight : contenu public uniquement.
    yt-dlp supporte certains Spotlights publics.
    """
    try:
        r = _run(_ytdlp_base(url, out, UA["mobile"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
    except subprocess.TimeoutExpired:
        pass

    # Playwright : intercepter le flux vidéo
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
            await page.wait_for_timeout(5000)
            await browser.close()

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=30) as c:
                    resp = await c.get(video_url,
                                      headers={"User-Agent": UA["mobile"]})
                    with open(out, "wb") as f:
                        f.write(resp.content)
                if _check_file(out):
                    return _ok()
    except Exception as e:
        print(f"⚠️ Snapchat Playwright: {e}", flush=True)

    return _err("download_failed",
                "Impossible de télécharger ce Snap. "
                "Seuls les Spotlights publics sont accessibles.")


async def _dl_youtube(url: str, out: str) -> dict:
    """
    YouTube : Videos, Shorts, Clips.
    yt-dlp très fiable — on limite à 60s via --download-sections.
    """
    # Normaliser les Shorts en URL standard (même traitement)
    url_norm = re.sub(r"youtube\.com/shorts/([^?&]+)", r"youtube.com/watch?v=\1", url)

    try:
        r = _run(_ytdlp_base(url_norm, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout",
                    "Téléchargement YouTube trop lent. Réessayez dans quelques instants.")


async def _dl_dailymotion(url: str, out: str) -> dict:
    """Dailymotion : yt-dlp fonctionne bien."""
    # Normaliser dai.ly
    url_dm = re.sub(r"dai\.ly/([a-zA-Z0-9]+)", r"dailymotion.com/video/\1", url)
    try:
        r = _run(_ytdlp_base(url_dm, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Dailymotion trop lent.")


async def _dl_vimeo(url: str, out: str) -> dict:
    """Vimeo : yt-dlp fonctionne bien. Vidéos privées avec mot de passe = KO."""
    try:
        r = _run(_ytdlp_base(url, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Vimeo trop lent.")


async def _dl_bilibili(url: str, out: str) -> dict:
    """Bilibili : yt-dlp fonctionne pour les vidéos publiques."""
    try:
        r = _run(_ytdlp_base(url, out, UA["desktop"]))
        if r.returncode == 0 and _check_file(out):
            return _ok()
        return _parse_ytdlp_error(r.stderr + r.stdout)
    except subprocess.TimeoutExpired:
        return _err("download_timeout", "Téléchargement Bilibili trop lent.")


async def _dl_generic(url: str, out: str) -> dict:
    """
    Fallback générique pour toute URL non reconnue.
    yt-dlp supporte ~1000 sites — on tente quand même.
    """
    for ua in [UA["desktop"], UA["mobile"]]:
        try:
            r = _run(_ytdlp_base(url, out, ua))
            if r.returncode == 0 and _check_file(out):
                return _ok()
        except subprocess.TimeoutExpired:
            continue

    return _err("unsupported_platform",
                "Cette plateforme n'est pas supportée. "
                "Essayez TikTok, Instagram, YouTube, Twitter/X, Facebook, "
                "Dailymotion, Vimeo, Reddit ou Snapchat.")

# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE UNIQUE
# ════════════════════════════════════════════════════════════════
async def download_video(url: str, out_path: str, platform: str) -> dict:
    """
    Télécharge une vidéo depuis n'importe quelle plateforme.
    Utilise la stratégie optimale selon la plateforme détectée.
    Retourne {"ok": True} ou {"ok": False, "code": ..., "message": ...}
    """
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