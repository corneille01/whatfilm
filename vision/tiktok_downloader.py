# vision/tiktok_downloader.py — PATCH 2026-06
import asyncio
import re
import os
import httpx
from playwright.async_api import async_playwright

TIKTOK_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://www.tiktok.com/",
    "Origin":  "https://www.tiktok.com",
    "Cookie":  "tt_webid_v2=; ttwid=; msToken=",
    "Accept":  "video/webm,video/mp4,video/*;q=0.9,*/*;q=0.8",
    "Range":   "bytes=0-",
}


async def get_tiktok_video_url(video_url: str) -> str | None:
    """
    Extrait l'URL directe de la vidéo TikTok via Playwright.
    Timeout augmenté à 45s (TikTok charge beaucoup de JS).
    """
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
                user_agent=TIKTOK_DOWNLOAD_HEADERS["User-Agent"],
                viewport={"width": 390, "height": 844},
                extra_http_headers={
                    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                },
            )
            page = await context.new_page()

            best_url  = None
            best_size = 0

            async def handle_response(response):
                nonlocal best_url, best_size
                ct  = response.headers.get("content-type", "")
                cl  = int(response.headers.get("content-length", "0") or 0)
                url = response.url
                is_video = (
                    "video" in ct
                    or ".mp4" in url
                    or "mime_type=video" in url
                )
                is_tiktok_cdn = any(d in url for d in [
                    "tiktokcdn", "tiktok.com", "muscdn",
                    "tiktokv.com", "bytecdn", "snssdk",
                ])
                if is_video and is_tiktok_cdn and cl > best_size:
                    best_url  = url
                    best_size = cl
                    print(f"🎬 Vidéo candidate ({cl//1024}KB): {url[:70]}",
                          flush=True)

            page.on("response", handle_response)

            # ── Navigation avec timeout augmenté à 45s ───────────
            try:
                await page.goto(video_url,
                                wait_until="networkidle",
                                timeout=45000)   # 45s au lieu de 30s
            except Exception:
                # networkidle peut timeout mais la vidéo est déjà interceptée
                pass

            await page.evaluate("window.scrollBy(0, 100)")
            await asyncio.sleep(4)
            await browser.close()

            # ── Fallback : parser le HTML ────────────────────────
            if not best_url:
                try:
                    async with async_playwright() as p2:
                        br2 = await p2.chromium.launch(
                            headless=True,
                            args=["--no-sandbox", "--disable-setuid-sandbox",
                                  "--disable-dev-shm-usage", "--disable-gpu"])
                        ctx2 = await br2.new_context(
                            user_agent=TIKTOK_DOWNLOAD_HEADERS["User-Agent"])
                        pg2  = await ctx2.new_page()
                        # Timeout augmenté à 40s pour le fallback HTML
                        await pg2.goto(video_url, timeout=40000)
                        await asyncio.sleep(4)
                        html = await pg2.content()
                        await br2.close()

                        for pattern in [
                            r'"downloadAddr":"(https?://[^"]+)"',
                            r'"playAddr":"(https?://[^"]+)"',
                            r'"url":"(https?://[^"]+\.mp4[^"]*)"',
                        ]:
                            m = re.search(pattern, html)
                            if m:
                                best_url = (m.group(1)
                                            .replace(r"\u002F", "/")
                                            .replace(r"\/", "/"))
                                print(f"🎬 URL parsée HTML: {best_url[:70]}",
                                      flush=True)
                                break
                except Exception as e2:
                    print(f"⚠️ Fallback HTML parse: {e2}", flush=True)

            if best_url:
                print(f"✅ URL TikTok trouvée: {best_url[:80]}...", flush=True)
            else:
                print("❌ Aucune URL vidéo TikTok trouvée", flush=True)

            return best_url

    except Exception as e:
        print(f"❌ Playwright TikTok erreur: {e}", flush=True)
        return None


async def download_tiktok_direct(video_url: str, out_path: str) -> bool:
    url = await get_tiktok_video_url(video_url)
    if not url:
        return False

    try:
        async with httpx.AsyncClient(
            timeout=60,             # 60s au lieu de 45s
            follow_redirects=True,
            headers=TIKTOK_DOWNLOAD_HEADERS,
        ) as client:
            resp = await client.get(url)
            print(f"📥 TikTok DL status={resp.status_code} "
                  f"size={len(resp.content)//1024}KB", flush=True)

            if resp.status_code in (200, 206) and len(resp.content) > 1000:
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                return True

            if resp.status_code == 403:
                headers_no_range = {k: v
                                    for k, v in TIKTOK_DOWNLOAD_HEADERS.items()
                                    if k != "Range"}
                resp2 = await client.get(url, headers=headers_no_range)
                if resp2.status_code == 200 and len(resp2.content) > 1000:
                    with open(out_path, "wb") as f:
                        f.write(resp2.content)
                    return True

    except Exception as e:
        print(f"❌ TikTok download direct: {e}", flush=True)

    return False