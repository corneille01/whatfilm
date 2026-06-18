#!/usr/bin/env python3
# playwright_worker.py – sous-processus isolé (évite que Render détecte les ports UDP)
import json
import sys

EXTRACT_JS = """() => {
    const grab = (root) => {
        let found = null;
        const walk = (o) => {
            if (found || !o || typeof o !== 'object') return;
            for (const k in o) {
                const v = o[k];
                if ((k === 'playAddr' || k === 'downloadAddr')
                    && typeof v === 'string' && v.startsWith('http')) { found = v; return; }
                if (v && typeof v === 'object') walk(v);
            }
        };
        walk(root);
        return found;
    };
    const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
    if (el) { try { const u = grab(JSON.parse(el.textContent)); if (u) return u; } catch(e){} }
    const og = document.querySelector('meta[property="og:video"]');
    if (og && og.content) return og.content;
    const v = document.querySelector('video');
    if (v && v.src && v.src.startsWith('http')) return v.src;
    return null;
}"""

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    output_path = sys.argv[2] if len(sys.argv) > 2 else ""
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
                user_agent="Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            )
            page = context.new_page()
            page.route("**/*", lambda route: route.abort()
                       if route.request.resource_type in ("image", "font", "stylesheet")
                       else route.continue_())
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500)

            try:
                video_url = page.evaluate(EXTRACT_JS)
            except Exception:
                video_url = None

            if not video_url:
                browser.close()
                print(json.dumps({"ok": False, "code": "no_video_found",
                                  "message": "Impossible d'extraire l'URL de la vidéo"}))
                return

            # Téléchargement DANS le contexte Playwright (cookies + referer) → évite les 404 playAddr
            if output_path:
                try:
                    resp = context.request.get(video_url, headers={"referer": url})
                    if resp.ok:
                        body = resp.body()
                        if body and len(body) > 1000:
                            with open(output_path, "wb") as f:
                                f.write(body)
                            browser.close()
                            print(json.dumps({"ok": True, "downloaded": True}))
                            return
                except Exception:
                    pass

            browser.close()
            # Fallback : renvoyer l'URL au parent
            print(json.dumps({"ok": True, "direct_url": video_url}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "code": "playwright_error", "message": str(e)}))

if __name__ == "__main__":
    main()