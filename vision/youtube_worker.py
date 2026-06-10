#!/usr/bin/env python3
# vision/youtube_worker.py
# Extraction URL directe YouTube via cascade : yt-dlp (android client) → Invidious
import json
import sys
import re
import urllib.request
import urllib.parse

INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.privacydev.net",
    "https://yt.cdaut.de",
]

def extract_video_id(url: str) -> str | None:
    patterns = [
        r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def try_invidious(video_id: str) -> dict:
    for base in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{base}/api/v1/videos/{video_id}?fields=formatStreams,adaptiveFormats"
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())

            # Préférer formatStreams (audio+vidéo muxés, mp4)
            for fmt in data.get("formatStreams", []):
                if fmt.get("container") == "mp4" and fmt.get("url"):
                    print(f"✅ Invidious OK ({base})", file=sys.stderr)
                    return {"ok": True, "direct_url": fmt["url"]}

            # Fallback adaptiveFormats vidéo
            for fmt in data.get("adaptiveFormats", []):
                t = fmt.get("type", "")
                if "video/mp4" in t and fmt.get("url"):
                    return {"ok": True, "direct_url": fmt["url"]}

        except Exception as e:
            print(f"⚠️ Invidious {base} KO: {e}", file=sys.stderr)
            continue

    return {"ok": False, "code": "invidious_all_failed",
            "message": "Toutes les instances Invidious ont échoué"}


def try_ytdlp(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError:
        return {"ok": False, "code": "yt_dlp_missing", "message": "yt-dlp non installé"}

    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "socket_timeout": 15,
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr", "android", "ios"],
                "skip": ["hls", "dash"],
            }
        },
        "headers": {
            "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"
        },
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("url"):
                return {"ok": True, "direct_url": info["url"]}
            # Chercher dans formats
            for fmt in (info.get("formats") or []):
                if fmt.get("url") and fmt.get("ext") == "mp4":
                    return {"ok": True, "direct_url": fmt["url"]}
    except Exception as e:
        msg = str(e)[:200]
        print(f"⚠️ yt-dlp KO: {msg}", file=sys.stderr)
        if "bot" in msg.lower() or "sign in" in msg.lower():
            return {"ok": False, "code": "bot_detected", "message": msg}

    return {"ok": False, "code": "ytdlp_failed", "message": "yt-dlp n'a pas trouvé d'URL"}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not url:
        print(json.dumps({"ok": False, "code": "no_url", "message": "Aucune URL fournie"}))
        return

    video_id = extract_video_id(url)
    print(f"🎬 YouTube worker: id={video_id}", file=sys.stderr)

    # 1. yt-dlp (android_vr client, pas de cookies nécessaires)
    result = try_ytdlp(url)
    if result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
        return

    # 2. Invidious (API publique, toujours dispo)
    if video_id:
        result = try_invidious(video_id)
        if result["ok"]:
            print(json.dumps(result, ensure_ascii=False))
            return

    print(json.dumps({
        "ok": False,
        "code": "all_strategies_failed",
        "message": "Impossible d'extraire l'URL YouTube (bot détecté, pas de cookies)"
    }))


if __name__ == "__main__":
    main()