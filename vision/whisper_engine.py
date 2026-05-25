import os
from groq import Groq

def transcribe(audio_path: str, enabled: bool = True) -> str:
    if not enabled:
        return ""
    
    # Récupération de la clé API depuis les variables d'environnement
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Erreur : GROQ_API_KEY non trouvée dans les variables d'environnement.")
        return ""

    client = Groq(api_key=api_key)
    
    try:
        with open(audio_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
              file=(audio_path, file.read()),
              model="whisper-large-v3", # Modèle Whisper hébergé par Groq
              response_format="text"
            )
        return transcription
    except Exception as e:
        print(f"Erreur lors de la transcription API : {e}")
        return ""