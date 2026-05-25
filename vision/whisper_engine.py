import whisper

model = None


def transcribe(audio_path, enabled=True):

    global model

    if not enabled:
        return ""

    try:

        if model is None:
            print("LOADING WHISPER MODEL...")
            model = whisper.load_model("tiny")

        result = model.transcribe(
            audio_path,
            fp16=False
        )

        text = result.get("text", "")

        print("TRANSCRIPT =", text)

        return text.strip()

    except Exception as e:

        print("WHISPER ERROR =", str(e))

        return ""