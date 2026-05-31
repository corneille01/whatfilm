# vision/ocr_engine.py
import easyocr
import time
import threading
import sys
import os
import signal
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

_reader = None
_loading_started = False
_loading_done = False
_loading_error = None

# ⚠️ 'ar' EST INCOMPATIBLE avec les langues latines dans le même Reader EasyOCR
# Il faut un Reader séparé pour l'arabe — on le retire du groupe principal
SUPPORTED_LANGUAGES = [
    'en', 'fr', 'es', 'de', 'it', 'pt',
    'nl', 'pl', 'sv', 'da', 'cs', 'hu', 'ro', 'tr',
    'ru', 'bg', 'uk', 'vi', 'id',
]

_ocr_executor = ThreadPoolExecutor(max_workers=1)

def _load_model():
    global _reader, _loading_done, _loading_error
    try:
        print("🔄 Chargement EasyOCR...", flush=True)
        start = time.time()
        _reader = easyocr.Reader(
            SUPPORTED_LANGUAGES,
            gpu=False,
            verbose=False,
            download_enabled=True,
        )
        print(f"✅ EasyOCR chargé en {time.time() - start:.1f}s", flush=True)
    except Exception as e:
        _loading_error = str(e)
        print(f"❌ EasyOCR échec: {e}", flush=True)
    finally:
        _loading_done = True

def start_loading():
    global _loading_started
    if not _loading_started:
        _loading_started = True
        t = threading.Thread(target=_load_model, daemon=True)
        t.start()

def get_reader():
    if not _loading_started:
        start_loading()
    return _reader  # None si pas prêt ou en erreur

def _ocr_one_frame(frame_path):
    """OCR d'une seule frame, appelé dans le ThreadPoolExecutor."""
    results = _reader.readtext(frame_path, detail=0)
    return " ".join(results)

def extract_text_from_images(frames, max_images=6):
    if not frames:
        return ""
    reader = get_reader()
    if reader is None:
        print("⚠️ EasyOCR pas prêt → OCR côté client", flush=True)
        return ""

    texts = []
    for frame_path in frames[:max_images]:
        try:
            if not os.path.exists(frame_path):
                continue
            # Timeout de 8s par frame pour éviter le blocage total
            future = _ocr_executor.submit(_ocr_one_frame, frame_path)
            text = future.result(timeout=8)
            if text.strip():
                texts.append(text.strip())
        except FuturesTimeout:
            print(f"⏱️ OCR timeout sur {os.path.basename(frame_path)}", flush=True)
        except Exception as e:
            print(f"⚠️ OCR frame error: {str(e)[:80]}", flush=True)

    return " ".join(texts)