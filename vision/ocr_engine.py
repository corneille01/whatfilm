# vision/ocr_engine.py
import easyocr
import time
import threading
import sys
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

_reader = None
_loading_started = False
_loading_done = False
_loading_error = None

# ═══════════════════════════════════════════════════════════════════
# RÈGLE EASYOCR : les scripts ne peuvent PAS être mélangés.
#   - Latin  (en, fr, es, de…) → un Reader
#   - Cyrillique (ru, bg, uk…) → Reader séparé INCOMPATIBLE avec Latin
#   - Arabe (ar…)              → Reader séparé INCOMPATIBLE avec Latin
#
# On utilise Latin uniquement : suffisant pour lire les titres de films
# dans les sous-titres/affiches en TikTok/Reels.
# ═══════════════════════════════════════════════════════════════════
SUPPORTED_LANGUAGES = ['en', 'fr', 'es', 'de', 'it', 'pt', 'nl', 'pl', 'sv', 'da', 'cs', 'hu', 'ro', 'tr', 'vi', 'id']

_ocr_executor = ThreadPoolExecutor(max_workers=1)


def _load_model():
    global _reader, _loading_done, _loading_error
    try:
        print("🔄 Chargement EasyOCR (latin uniquement)...", flush=True)
        start = time.time()
        _reader = easyocr.Reader(
            SUPPORTED_LANGUAGES,
            gpu=False,
            verbose=False,
            download_enabled=True,
        )
        print(f"✅ EasyOCR prêt en {time.time() - start:.1f}s", flush=True)
    except Exception as e:
        _loading_error = str(e)
        print(f"❌ EasyOCR échec: {e}", flush=True)
    finally:
        _loading_done = True


def start_loading():
    global _loading_started
    if not _loading_started:
        _loading_started = True
        threading.Thread(target=_load_model, daemon=True).start()


def get_reader():
    if not _loading_started:
        start_loading()
    return _reader  # None si pas encore prêt ou en erreur


def _ocr_one_frame(frame_path):
    return " ".join(_reader.readtext(frame_path, detail=0))


def extract_text_from_images(frames, max_images=6):
    if not frames:
        return ""
    reader = get_reader()
    if reader is None:
        print("⚠️ EasyOCR pas prêt → fallback client", flush=True)
        return ""

    texts = []
    for frame_path in frames[:max_images]:
        if not os.path.exists(frame_path):
            continue
        try:
            future = _ocr_executor.submit(_ocr_one_frame, frame_path)
            text = future.result(timeout=8)
            if text.strip():
                texts.append(text.strip())
        except FuturesTimeout:
            print(f"⏱️ OCR timeout: {os.path.basename(frame_path)}", flush=True)
        except Exception as e:
            print(f"⚠️ OCR erreur: {str(e)[:80]}", flush=True)

    return " ".join(texts)