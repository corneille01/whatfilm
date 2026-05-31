# vision/ocr_engine.py
import easyocr
import time
import threading
import sys
import os

_reader = None
_loading_thread = None
_loading_started = False
_loading_done = False
_loading_error = None

# Langues compatibles dans un seul Reader (Latin + Cyrillic + Arabe)
# ch_sim / ja / ko retiré — incompatible avec les langues latines en combinaison
SUPPORTED_LANGUAGES = [
    'en', 'fr', 'es', 'de', 'it', 'pt',
    'nl', 'pl', 'sv', 'da', 'cs', 'hu', 'ro', 'tr',
    'ru', 'bg', 'uk', 'vi', 'id', 'ar',
]

def _load_model():
    global _reader, _loading_done, _loading_error
    try:
        print("🔄 Chargement EasyOCR...")
        sys.stdout.flush()
        start = time.time()

        _reader = easyocr.Reader(
            SUPPORTED_LANGUAGES,
            gpu=False,
            verbose=False,
            download_enabled=True,
        )

        elapsed = time.time() - start
        print(f"✅ EasyOCR chargé en {elapsed:.1f}s")
        sys.stdout.flush()

    except Exception as e:
        print(f"❌ EasyOCR échec: {e}")
        sys.stdout.flush()
        _loading_error = str(e)
        # Ne pas faire raise — le thread se termine proprement
        # get_reader() retournera None → fallback client-side

    finally:
        _loading_done = True  # toujours atteint, même en cas d'erreur

def start_loading():
    global _loading_started, _loading_thread
    if not _loading_started:
        _loading_started = True
        _loading_thread = threading.Thread(target=_load_model, daemon=True)
        _loading_thread.start()

def get_reader():
    if not _loading_started:
        start_loading()
    if _reader is not None:
        return _reader
    # Pas de blocage : si pas prêt ou en erreur, on retourne None
    return None

def extract_text_from_images(frames, max_images=8):
    if not frames:
        return ""

    reader = get_reader()
    if reader is None:
        print("⚠️ EasyOCR pas prêt → OCR côté client")
        return ""

    texts = []
    for frame_path in frames[:max_images]:
        try:
            if not os.path.exists(frame_path):
                continue
            results = reader.readtext(frame_path, detail=0)
            text = " ".join(results)
            if text.strip():
                texts.append(text.strip())
        except Exception as e:
            print(f"OCR frame error: {str(e)[:80]}")

    return " ".join(texts)