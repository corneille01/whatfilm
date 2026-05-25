import whisper

model = whisper.load_model("tiny")  # coût ↓↓↓


def transcribe(audio_path, enabled=True):

    if not enabled:
        return ""

    result = model.transcribe(audio_path)

    # truncate audio noise
    return result["text"][:2000]