import os
from groq import Groq

def transcribe(audio_path: str, enabled: bool = True) -> str:
    """
    Transcrit un fichier audio en texte en utilisant l'API ultra-rapide de Groq.
    Détecte automatiquement la langue parlée.
    """
    if not enabled:
        return ""

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("❌ ERREUR : La variable d'environnement GROQ_API_KEY est introuvable.")
        return ""

    try:
        client = Groq(api_key=api_key)

        with open(audio_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_path, file.read()),
                model="whisper-large-v3", 
                response_format="text"
                # Le paramètre 'language' a été retiré : 
                # Whisper va maintenant détecter la langue automatiquement !
            )
        
        return transcription

    except Exception as e:
        print(f"❌ ERREUR API GROQ (Transcription) : {str(e)}")
        return ""