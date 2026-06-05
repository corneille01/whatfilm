#!/usr/bin/env python3
# youtube_worker.py – sous‑processus isolé pour YouTube via Playwright
import json
import sys

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

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Accepter automatiquement les dialogues (cookies, etc.)
            page.on("dialog", lambda dialog: dialog.accept())

            # ── INTERCEPTION RÉSEAU : capturer l'URL de la vidéo ──
            video_urls = []

            def handle_response(response):
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    if 'video' in content_type and ('videoplayback' in response.url or '.mp4' in response.url):
                        video_urls.append(response.url)

            page.on("response", handle_response)
            # ──────────────────────────────────────────────────────

            page.goto(url, wait_until="networkidle", timeout=30000)

            # Essayer de cliquer sur "Accepter tout" si présent
            try:
                accept_button = page.locator('button:has-text("Tout accepter"), button:has-text("Accept all")')
                if accept_button.count() > 0:
                    accept_button.click()
            except:
                pass

            # Attendre un peu que la vidéo commence à charger
            page.wait_for_timeout(6000)

            # Si l'interception réseau a trouvé une URL, on l'utilise
            if video_urls:
                browser.close()
                print(json.dumps({"ok": True, "direct_url": video_urls[0]}, ensure_ascii=False))
                return

            # Sinon, essayer de la récupérer dans le DOM
            video_url = None
            try:
                video_url = page.evaluate("""
                    () => {
                        const video = document.querySelector('video');
                        return video ? video.src || video.currentSrc : '';
                    }
                """)
            except:
                pass

            if not video_url:
                try:
                    meta = page.query_selector('meta[property="og:video"]')
                    if meta:
                        video_url = meta.get_attribute("content")
                except:
                    pass

            if not video_url:
                try:
                    video_el = page.query_selector('video')
                    if video_el:
                        video_url = video_el.get_attribute("src")
                except:
                    pass

            browser.close()

            if video_url:
                print(json.dumps({"ok": True, "direct_url": video_url}, ensure_ascii=False))
            else:
                print(json.dumps({"ok": False, "code": "no_video_found",
                                  "message": "Impossible d'extraire l'URL de la vidéo YouTube"}))
    except Exception as e:
        print(json.dumps({"ok": False, "code": "playwright_error", "message": str(e)}))

if __name__ == "__main__":
    main()