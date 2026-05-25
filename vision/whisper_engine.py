# vision/whisper_engine.py

import whisper


model = whisper.load_model("tiny")


def transcribe(audio_path, enabled=True):

    if not enabled:
        return ""

    try:

        print("WHISPER AUDIO =", audio_path)

        result = model.transcribe(audio_path)

        text = result.get("text", "")

        print("WHISPER RESULT =", text)

        return text

    except Exception as e:

        print("WHISPER ERROR =", str(e))

        return ""