"""
vision/whisper_engine.py — Transcription audio avec cascade de services gratuits.

Cascade :
  1. Groq Whisper      → gratuit, 28 800 min/jour
  2. Deepgram          → gratuit, 45h/mois (DEEPGRAM_API_KEY)
  3. AssemblyAI        → gratuit, 100h/mois (ASSEMBLYAI_API_KEY)
  4. None              → fallback client (Whisper.js navigateur)
"""

import os
import httpx
import asyncio

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
DEEPGRAM_API_KEY  = os.environ.get("DEEPGRAM_API_KEY", "")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Groq Whisper (28 800 min/jour gratuit)
# ════════════════════════════════════════════════════════════════
def transcribe_groq(audio_path: str) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(audio_path, f.read()),
                model="whisper-large-v3-turbo",
                response_format="text",
                language=None,  # auto-detect
            )
        text = result.strip() if isinstance(result, str) else (result.text or "").strip()
        if text:
            print(f"✅ Groq OK ({len(text)} chars)", flush=True)
        return text
    except Exception as e:
        print(f"⚠️ Groq KO: {str(e)[:100]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 2 — Deepgram (45h/mois gratuit)
# ════════════════════════════════════════════════════════════════
async def transcribe_deepgram(audio_path: str) -> str:
    if not DEEPGRAM_API_KEY:
        return ""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&language=fr&detect_language=true",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/mpeg",
                },
                content=audio_data,
            )
            resp.raise_for_status()
        text = (
            resp.json()
            .get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
            .strip()
        )
        if text:
            print(f"✅ Deepgram OK ({len(text)} chars)", flush=True)
        return text
    except Exception as e:
        print(f"⚠️ Deepgram KO: {str(e)[:100]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 3 — AssemblyAI (100h/mois gratuit)
# ════════════════════════════════════════════════════════════════
async def transcribe_assemblyai(audio_path: str) -> str:
    if not ASSEMBLYAI_API_KEY:
        return ""
    headers = {
        "authorization": ASSEMBLYAI_API_KEY,
        "content-type": "application/json",
    }
    try:
        # Upload
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        async with httpx.AsyncClient(timeout=30) as client:
            upload = await client.post(
                "https://api.assemblyai.com/v2/upload",
                headers={"authorization": ASSEMBLYAI_API_KEY},
                content=audio_data,
            )
            upload.raise_for_status()
            upload_url = upload.json()["upload_url"]

            # Submit
            submit = await client.post(
                "https://api.assemblyai.com/v2/transcript",
                headers=headers,
                json={"audio_url": upload_url, "language_detection": True},
            )
            submit.raise_for_status()
            transcript_id = submit.json()["id"]

            # Poll
            for _ in range(20):
                await asyncio.sleep(3)
                poll = await client.get(
                    f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                    headers=headers,
                )
                poll.raise_for_status()
                status = poll.json().get("status")
                if status == "completed":
                    text = (poll.json().get("text") or "").strip()
                    if text:
                        print(f"✅ AssemblyAI OK ({len(text)} chars)", flush=True)
                    return text
                if status == "error":
                    print(f"⚠️ AssemblyAI error: {poll.json().get('error')}", flush=True)
                    return ""
        return ""
    except Exception as e:
        print(f"⚠️ AssemblyAI KO: {str(e)[:100]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
def transcribe(audio_path: str, enabled: bool = True) -> str:
    if not enabled:
        return ""

    # ── 1. Groq Whisper ──────────────────────────────────────────
    # Décommenter pour activer :
    print("🎙️ Essai Groq...", flush=True)
    text = transcribe_groq(audio_path)
    if text:
        return text

    # ── 2. Deepgram ──────────────────────────────────────────────
    # Décommenter pour activer :
    if DEEPGRAM_API_KEY:
        print("🎙️ Essai Deepgram...", flush=True)
        import asyncio
        text = asyncio.get_event_loop().run_until_complete(
            transcribe_deepgram(audio_path)
        )
        if text:
            return text

    # ── 3. AssemblyAI ────────────────────────────────────────────
    # Décommenter pour activer :
    if ASSEMBLYAI_API_KEY:
        print("🎙️ Essai AssemblyAI...", flush=True)
        import asyncio
        text = asyncio.get_event_loop().run_until_complete(
            transcribe_assemblyai(audio_path)
        )
        if text:
            return text

    # ── 4. Fallback client (Whisper.js navigateur) ───────────────
    print("⚠️ Tous les services de transcription KO → fallback client", flush=True)
    return ""