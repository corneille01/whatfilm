"""
vision/whisper_engine.py — Transcription audio avec cascade de services gratuits.

Cascade :
  1. Groq Whisper        → gratuit, 28 800 min/jour (whisper-large-v3-turbo)
  2. Deepgram Nova-2     → gratuit, 45h/mois (DEEPGRAM_API_KEY)
  3. AssemblyAI          → gratuit, 100h/mois (ASSEMBLYAI_API_KEY)
  4. Whisper via OpenAI  → payant mais très fiable (OPENAI_API_KEY)
  5. Gladia              → gratuit, 10h/mois (GLADIA_API_KEY)
  6. Fallback client     → Whisper.js navigateur

Chaque service est tenté dans l'ordre.
Un service sans clé API est ignoré silencieusement.
"""

import os
import asyncio
import httpx

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY",       "")
DEEPGRAM_API_KEY   = os.environ.get("DEEPGRAM_API_KEY",   "")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY",     "")
GLADIA_API_KEY     = os.environ.get("GLADIA_API_KEY",     "")


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Groq Whisper (28 800 min/jour gratuit)
# Console : https://console.groq.com
# Modèle : whisper-large-v3-turbo
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
        err = str(e)[:120]
        # Distinguer erreur auth (clé invalide/expirée) des autres erreurs
        if "401" in err or "invalid" in err.lower() or "unauthorized" in err.lower():
            print(f"⚠️ Groq AUTH KO (clé invalide/expirée): {err}", flush=True)
        else:
            print(f"⚠️ Groq KO: {err}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 2 — Deepgram Nova-2 (45h/mois gratuit)
# Console : https://console.deepgram.com
# Clé : DEEPGRAM_API_KEY
# ════════════════════════════════════════════════════════════════

async def transcribe_deepgram(audio_path: str) -> str:
    if not DEEPGRAM_API_KEY:
        return ""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen"
                "?model=nova-2&language=fr&detect_language=true&smart_format=true",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type":  "audio/mpeg",
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
        print(f"⚠️ Deepgram KO: {str(e)[:120]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 3 — AssemblyAI (100h/mois gratuit)
# Console : https://www.assemblyai.com/dashboard
# Clé : ASSEMBLYAI_API_KEY
# ════════════════════════════════════════════════════════════════

async def transcribe_assemblyai(audio_path: str) -> str:
    if not ASSEMBLYAI_API_KEY:
        return ""
    headers = {
        "authorization":  ASSEMBLYAI_API_KEY,
        "content-type":   "application/json",
    }
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        async with httpx.AsyncClient(timeout=40) as client:
            # Upload
            upload = await client.post(
                "https://api.assemblyai.com/v2/upload",
                headers={"authorization": ASSEMBLYAI_API_KEY},
                content=audio_data,
            )
            upload.raise_for_status()
            upload_url = upload.json()["upload_url"]

            # Soumettre la transcription
            submit = await client.post(
                "https://api.assemblyai.com/v2/transcript",
                headers=headers,
                json={
                    "audio_url":          upload_url,
                    "language_detection": True,
                },
            )
            submit.raise_for_status()
            transcript_id = submit.json()["id"]

            # Polling (max 25 tentatives × 3s = 75s)
            for _ in range(25):
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
                    print(
                        f"⚠️ AssemblyAI error: {poll.json().get('error')}",
                        flush=True
                    )
                    return ""

        return ""
    except Exception as e:
        print(f"⚠️ AssemblyAI KO: {str(e)[:120]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 4 — OpenAI Whisper (payant, ~$0.006/min)
# Console : https://platform.openai.com
# Clé : OPENAI_API_KEY
# Utilisé uniquement en dernier recours si tous les gratuits KO
# ════════════════════════════════════════════════════════════════

async def transcribe_openai(audio_path: str) -> str:
    if not OPENAI_API_KEY:
        return ""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (audio_path, audio_data, "audio/mpeg")},
                data={
                    "model":    "whisper-1",
                    "language": "fr",
                },
            )
            resp.raise_for_status()

        text = (resp.json().get("text") or "").strip()
        if text:
            print(f"✅ OpenAI Whisper OK ({len(text)} chars)", flush=True)
        return text
    except Exception as e:
        print(f"⚠️ OpenAI Whisper KO: {str(e)[:120]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# NIVEAU 5 — Gladia (10h/mois gratuit)
# Console : https://app.gladia.io
# Clé : GLADIA_API_KEY
# ════════════════════════════════════════════════════════════════

async def transcribe_gladia(audio_path: str) -> str:
    if not GLADIA_API_KEY:
        return ""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        async with httpx.AsyncClient(timeout=60) as client:
            # Upload
            upload = await client.post(
                "https://api.gladia.io/v2/upload",
                headers={
                    "x-gladia-key": GLADIA_API_KEY,
                },
                files={"audio": (audio_path, audio_data, "audio/mpeg")},
            )
            upload.raise_for_status()
            audio_url = upload.json().get("audio_url", "")
            if not audio_url:
                print("⚠️ Gladia upload KO: pas d'audio_url", flush=True)
                return ""

            # Soumettre
            submit = await client.post(
                "https://api.gladia.io/v2/pre-recorded",
                headers={
                    "x-gladia-key":  GLADIA_API_KEY,
                    "Content-Type":  "application/json",
                },
                json={
                    "audio_url":          audio_url,
                    "detect_language":    True,
                    "transcription_hint": "film movie series cinema",
                },
            )
            submit.raise_for_status()
            result_url = submit.json().get("result_url", "")
            if not result_url:
                print("⚠️ Gladia submit KO: pas de result_url", flush=True)
                return ""

            # Polling (max 20 tentatives × 4s = 80s)
            for _ in range(20):
                await asyncio.sleep(4)
                poll = await client.get(
                    result_url,
                    headers={"x-gladia-key": GLADIA_API_KEY},
                )
                poll.raise_for_status()
                data   = poll.json()
                status = data.get("status", "")

                if status == "done":
                    utterances = (
                        data.get("result", {})
                        .get("transcription", {})
                        .get("utterances", [])
                    )
                    text = " ".join(
                        u.get("text", "") for u in utterances
                    ).strip()
                    if text:
                        print(f"✅ Gladia OK ({len(text)} chars)", flush=True)
                    return text

                if status == "error":
                    print(
                        f"⚠️ Gladia error: {data.get('error_message', 'unknown')}",
                        flush=True
                    )
                    return ""

        return ""
    except Exception as e:
        print(f"⚠️ Gladia KO: {str(e)[:120]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════

def transcribe(audio_path: str, enabled: bool = True) -> str:
    """
    Cascade de transcription :
      1. Groq Whisper      (28 800 min/jour gratuit)
      2. Deepgram Nova-2   (45h/mois gratuit)
      3. AssemblyAI        (100h/mois gratuit)
      4. Gladia            (10h/mois gratuit)
      5. OpenAI Whisper    (payant, dernier recours)
      6. Fallback client   (Whisper.js navigateur)

    Chaque service sans clé API est ignoré automatiquement.
    """
    if not enabled:
        return ""

    loop = asyncio.get_event_loop()

    # ── 1. Groq Whisper ──────────────────────────────────────────
    print("🎙️ Essai Groq...", flush=True)
    text = transcribe_groq(audio_path)
    if text:
        return text

    # ── 2. Deepgram ──────────────────────────────────────────────
    if DEEPGRAM_API_KEY:
        print("🎙️ Essai Deepgram...", flush=True)
        text = loop.run_until_complete(transcribe_deepgram(audio_path))
        if text:
            return text

    # ── 3. AssemblyAI ────────────────────────────────────────────
    if ASSEMBLYAI_API_KEY:
        print("🎙️ Essai AssemblyAI...", flush=True)
        text = loop.run_until_complete(transcribe_assemblyai(audio_path))
        if text:
            return text

    # ── 4. Gladia ────────────────────────────────────────────────
    if GLADIA_API_KEY:
        print("🎙️ Essai Gladia...", flush=True)
        text = loop.run_until_complete(transcribe_gladia(audio_path))
        if text:
            return text

    # ── 5. OpenAI Whisper (payant, dernier recours) ───────────────
    if OPENAI_API_KEY:
        print("🎙️ Essai OpenAI Whisper (payant)...", flush=True)
        text = loop.run_until_complete(transcribe_openai(audio_path))
        if text:
            return text

    # ── 6. Fallback client ───────────────────────────────────────
    print(
        "⚠️ Tous les services de transcription KO → fallback client",
        flush=True
    )
    return ""