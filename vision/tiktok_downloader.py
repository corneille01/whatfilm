# vision/tiktok_downloader.py

from playwright.async_api import async_playwright

async def get_tiktok_video_url(page_url: str) -> str:
    """
    Ouvre la page TikTok avec un vrai navigateur, attend que la vidéo se charge,
    et retourne l'URL directe de la vidéo (mp4).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
            viewport={"width": 390, "height": 844},
        )
        page = await context.new_page()
        await page.goto(page_url, wait_until="networkidle")
        # Attendre la balise <video>
        video = await page.wait_for_selector("video", timeout=15000)
        video_url = await video.get_attribute("src")
        if not video_url:
            source = await page.query_selector("video source")
            if source:
                video_url = await source.get_attribute("src")
        await browser.close()
        return video_url