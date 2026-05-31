# vision/whisper_engine.py
# Cascade de transcription : Groq → AssemblyAI → Deepgram → "" (fallback navigateur)
#
# Priorité :
#   1. Groq        (whisper-large-v3, ultra-rapide, 5000 req/jour gratuit)
#   2. AssemblyAI  (100h/mois gratuit, très précis)
#   3. Deepgram    (200$ crédit gratuit, Nova-2)
#   4. ""          → app.py déclenche fallback Tesseract.js + Whisper.js navigateur

import os
import httpx
import asyncio

# ── GROQ ──────────────────────────────────────────────────────────
def _transcribe_groq(audio_path: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY manquante")
    from groq import Groq
    client = Groq(api_key=api_key)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(audio_path, f.read()),
            model="whisper-large-v3",
            response_format="text"
        )
    if not result or not str(result).strip():
        raise ValueError("Groq réponse vide")
    return str(result).strip()


# ── ASSEMBLYAI ────────────────────────────────────────────────────
def _transcribe_assemblyai(audio_path: str) -> str:
    api_key = os.environ.get("ASSEMBLYAI_API_KEY", "")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY manquante")

    headers = {"authorization": api_key}
    base_url = "https://api.assemblyai.com/v2"

    # 1. Upload du fichier audio
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    with httpx.Client(timeout=30) as client:
        up = client.post(f"{base_url}/upload", headers=headers, content=audio_data)
        up.raise_for_status()
        upload_url = up.json()["upload_url"]

        # 2. Lancer la transcription
        resp = client.post(f"{base_url}/transcript",
                           headers=headers,
                           json={"audio_url": upload_url, "language_detection": True})
        resp.raise_for_status()
        transcript_id = resp.json()["id"]

        # 3. Polling jusqu'à complétion (max 60s)
        for _ in range(30):
            poll = client.get(f"{base_url}/transcript/{transcript_id}", headers=headers)
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status")
            if status == "completed":
                text = data.get("text", "").strip()
                if not text:
                    raise ValueError("AssemblyAI réponse vide")
                return text
            if status == "error":
                raise ValueError(f"AssemblyAI error: {data.get('error')}")
            import time; time.sleep(2)

    raise ValueError("AssemblyAI timeout (60s)")


# ── DEEPGRAM ──────────────────────────────────────────────────────
def _transcribe_deepgram(audio_path: str) -> str:
    api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY manquante")

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://api.deepgram.com/v1/listen?model=nova-2&detect_language=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/mpeg",
            },
            content=audio_data,
        )
        resp.raise_for_status()
        data = resp.json()
        text = (data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                    .strip())
        if not text:
            raise ValueError("Deepgram réponse vide")
        return text


# ── CASCADE PRINCIPALE ────────────────────────────────────────────
def transcribe(audio_path: str, enabled: bool = True) -> str:
    """
    Essaie les services de transcription dans l'ordre :
    Groq → AssemblyAI → Deepgram → "" (fallback navigateur)
    Retourne "" si tous échouent → app.py envoie les données au navigateur.
    """
    if not enabled:
        return ""

    if not os.path.exists(audio_path):
        print("⚠️ Transcription : fichier audio introuvable", flush=True)
        return ""

    providers = [
        ("Groq",        _transcribe_groq),
        ("AssemblyAI",  _transcribe_assemblyai),
        ("Deepgram",    _transcribe_deepgram),
    ]

    for name, fn in providers:
        try:
            print(f"🎙️ Essai {name}...", flush=True)
            result = fn(audio_path)
            print(f"✅ {name} OK ({len(result)} chars)", flush=True)
            return result
        except Exception as e:
            print(f"⚠️ {name} KO: {str(e)[:120]}", flush=True)
            continue

    print("⚠️ Tous les services de transcription ont échoué → fallback navigateur", flush=True)
    return ""