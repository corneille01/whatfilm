# vision/whisper_engine.py

import whisper


# Chargement du modèle Whisper
# tiny = plus rapide pour Render free
model = whisper.load_model("tiny")


def transcribe(audio_path, enabled=True):

    if not enabled:
        return ""

    try:

        print("WHISPER START")

        result = model.transcribe(audio_path)

        text = result.get("text", "").strip()

        print("WHISPER TEXT =", text[:500])

        return text

    except Exception as e:

        print("WHISPER ERROR =", str(e))

        return ""