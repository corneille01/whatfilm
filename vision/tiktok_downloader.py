# vision/tiktok_downloader.py
import asyncio
from playwright.async_api import async_playwright
import re

async def get_tiktok_video_url(video_url: str) -> str:
    """
    Utilise Playwright pour extraire l'URL directe de la vidéo TikTok
    """
    try:
        async with async_playwright() as p:
            # Lancer le navigateur
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844}
            )
            
            page = await context.new_page()
            
            # Variable pour stocker l'URL de la vidéo
            video_url_found = None
            
            # Intercepter les requêtes pour trouver la vidéo
            async def handle_response(response):
                nonlocal video_url_found
                if not video_url_found:
                    content_type = response.headers.get('content-type', '')
                    if 'video' in content_type or '.mp4' in response.url:
                        if response.status == 200:
                            # Vérifier que c'est bien une vidéo TikTok
                            if any(domain in response.url for domain in ['tiktokcdn', 'tiktok.com', 'muscdn']):
                                video_url_found = response.url
            
            page.on("response", handle_response)
            
            # Aller sur la page TikTok
            await page.goto(video_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)  # Attendre que la vidéo commence à charger
            
            # Si on n'a pas trouvé l'URL via l'interception, chercher dans le HTML
            if not video_url_found:
                page_content = await page.content()
                
                # Patterns pour trouver l'URL de la vidéo
                patterns = [
                    r'"downloadAddr":"([^"]+)"',
                    r'"playAddr":"([^"]+)"',
                    r'video/mp4[^"]+"url":"([^"]+)"',
                    r'"video":.*?"url":"([^"]+)"',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, page_content)
                    if matches:
                        video_url_found = matches[0].replace('\\u002F', '/')
                        break
            
            await browser.close()
            
            if video_url_found:
                print(f"URL vidéo trouvée: {video_url_found[:100]}...")
                return video_url_found
            else:
                print("Aucune URL vidéo trouvée")
                return None
                
    except Exception as e:
        print(f"Erreur Playwright: {e}")
        return None