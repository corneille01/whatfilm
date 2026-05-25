from google import genai

from config.config import GEMINI_API_KEY


client = genai.Client(api_key=GEMINI_API_KEY)


def multimodal_extract(frames, ocr_text, transcript):

    combined = f"""
    OCR:
    {ocr_text}

    TRANSCRIPT:
    {transcript}
    """

    try:

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"""
            Analyse ce contenu vidéo :

            {combined}

            Résume précisément le contenu.
            """
        )

        return {
            "summary": response.text
        }

    except Exception as e:

        return {
            "summary": combined[:1000],
            "error": str(e)
        }