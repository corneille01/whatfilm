#!/usr/bin/env python3
# playwright_worker.py – sous‑processus isolé pour éviter que Render détecte les ports UDP
import json
import sys
import os

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not url:
        print(json.dumps({"ok": False, "code": "no_url", "message": "Aucune URL fournie"}))
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"ok": False, "code": "playwright_not_installed",
                          "message": "Playwright n'est pas installé dans ce worker"}))
        return

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
            )
            page = context.new_page()

            # Bloquer les ressources inutiles pour accélérer
            page.route("**/*", lambda route: route.abort()
                       if route.request.resource_type in ("image", "font", "stylesheet")
                       else route.continue_())

            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)  # laisser la page charger les scripts

            # Essayer de récupérer l'URL de la vidéo via l'API tiktok ou un sélecteur
            video_url = None
            # Chercher une balise <video> avec src
            try:
                video_element = page.query_selector("video")
                if video_element:
                    video_url = video_element.get_attribute("src")
            except:
                pass

            # Si pas trouvé, tenter via la balise meta
            if not video_url:
                try:
                    meta = page.query_selector('meta[property="og:video"]')
                    if meta:
                        video_url = meta.get_attribute("content")
                except:
                    pass

            # Si toujours pas, essayer via l'objet global __UNIVERSAL_DATA__
            if not video_url:
                try:
                    data = page.evaluate("() => window.__UNIVERSAL_DATA__ || window.__NEXT_DATA__ || window.__DATA__")
                    # Parcours heuristique pour trouver une URL vidéo
                    if isinstance(data, dict):
                        for key, val in data.items():
                            if isinstance(val, str) and val.startswith("http") and ".mp4" in val:
                                video_url = val
                                break
                except:
                    pass

            browser.close()

            if video_url:
                print(json.dumps({"ok": True, "direct_url": video_url}, ensure_ascii=False))
            else:
                print(json.dumps({"ok": False, "code": "no_video_found",
                                  "message": "Impossible d'extraire l'URL de la vidéo"}))
    except Exception as e:
        print(json.dumps({"ok": False, "code": "playwright_error", "message": str(e)}))

if __name__ == "__main__":
    main()