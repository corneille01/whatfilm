#!/usr/bin/env python3
# youtube_worker.py – Capture l'URL vidéo YouTube via Playwright + fallback Invidious
import json
import sys
import time
import urllib.request
import re

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not url:
        print(json.dumps({"ok": False, "code": "no_url", "message": "Aucune URL fournie"}))
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"ok": False, "code": "playwright_not_installed",
                          "message": "Playwright non installé"}))
        return

    # Extraire l'ID de la vidéo YouTube (pour fallback Invidious)
    video_id = None
    if "youtube.com" in url:
        match = re.search(r'v=([^&]+)', url)
        if match:
            video_id = match.group(1)
    elif "youtu.be" in url:
        video_id = url.split('/')[-1].split('?')[0]

    video_url = None

    # ── 1. Tentative Playwright ──────────────────────────────────
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Accepter les dialogues
            page.on("dialog", lambda dialog: dialog.accept())

            # Intercepter les réponses réseau pour attraper l'URL de la vidéo
            video_urls = []
            def handle_response(response):
                if response.status == 200:
                    ct = response.headers.get('content-type', '')
                    if 'video' in ct and ('videoplayback' in response.url or '.mp4' in response.url):
                        video_urls.append(response.url)
            page.on("response", handle_response)

            page.goto(url, wait_until="networkidle", timeout=30000)

            # Cliquer sur "Accepter tout" (cookies)
            try:
                accept_button = page.locator('button:has-text("Tout accepter"), button:has-text("Accept all")')
                if accept_button.count() > 0:
                    accept_button.click()
                    page.wait_for_timeout(2000)
            except:
                pass

            # Cliquer sur le bouton de lecture s'il existe (pour lancer la vidéo)
            try:
                play_button = page.locator('button.ytp-play-button, button.ytp-large-play-button')
                if play_button.count() > 0:
                    play_button.click()
                    page.wait_for_timeout(5000)  # attendre que la vidéo commence à charger
            except:
                pass

            # Attendre un peu plus pour les réponses réseau
            page.wait_for_timeout(5000)

            if video_urls:
                video_url = video_urls[0]  # Prendre la première URL attrapée
            else:
                # Essayer de récupérer l'URL dans le DOM
                try:
                    video_url = page.evaluate("() => { const v = document.querySelector('video'); return v ? (v.src || v.currentSrc) : ''; }")
                except:
                    pass

                if not video_url:
                    try:
                        meta = page.query_selector('meta[property="og:video"]')
                        if meta:
                            video_url = meta.get_attribute("content")
                    except:
                        pass

            browser.close()
    except Exception as e:
        # Playwright a échoué, on continue vers le fallback Invidious
        pass

    # ── 2. Fallback Invidious (si Playwright n'a rien trouvé) ────
    if not video_url and video_id:
        try:
            api_url = f"https://invidiou.site/api/v1/videos/{video_id}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                # Chercher un format mp4 de qualité acceptable
                for fmt in data.get("formatStreams", []):
                    if fmt.get("container") == "mp4" and fmt.get("url"):
                        video_url = fmt["url"]
                        break
                if not video_url:
                    for fmt in data.get("adaptiveFormats", []):
                        if fmt.get("type", "").startswith("video/mp4") and fmt.get("url"):
                            video_url = fmt["url"]
                            break
        except Exception:
            pass

    # ── Retour ──────────────────────────────────────────────────
    if video_url:
        print(json.dumps({"ok": True, "direct_url": video_url}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "code": "no_video_found",
                          "message": "Impossible d'extraire l'URL de la vidéo YouTube"}))
    return

if __name__ == "__main__":
    main()