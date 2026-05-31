# vision/ocr_engine.py - VERSION RAPIDE
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

# Langues principales uniquement (chargement 2x plus rapide)
SUPPORTED_LANGUAGES = [
    'en', 'fr', 'es', 'de', 'it', 'pt',
    'ch_sim', 'ch_tra', 'ja', 'ko',
    'nl', 'pl', 'sv', 'da', 'no', 'cs', 'sk', 'hu',
    'ro', 'hr', 'sl', 'et', 'lv', 'lt',
    'tr', 'ru', 'bg', 'uk', 'be',
    'vi', 'th', 'ms', 'id', 'tl',
    'hi', 'bn', 'ta', 'te', 'kn', 'mr', 'ne',
    'ar', 'fa', 'ur', 'sw', 'af'
]

def _load_model():
    global _reader, _loading_done, _loading_error
    try:
        print("🔄 Chargement EasyOCR en arrière-plan...")
        sys.stdout.flush()
        start = time.time()
        
        _reader = easyocr.Reader(SUPPORTED_LANGUAGES, gpu=False, verbose=False)
        
        elapsed = time.time() - start
        print(f"✅ EasyOCR chargé en {elapsed:.1f}s")
        sys.stdout.flush()
        _loading_done = True
        
    except Exception as e:
        print(f"❌ Erreur chargement EasyOCR: {e}")
        sys.stdout.flush()
        _loading_error = str(e)
        _loading_done = True

def start_loading():
    global _loading_started, _loading_thread
    if not _loading_started:
        _loading_started = True
        _loading_thread = threading.Thread(target=_load_model, daemon=True)
        _loading_thread.start()
        print("🚀 Thread EasyOCR démarré")
        sys.stdout.flush()

def get_reader():
    global _reader, _loading_done, _loading_error
    if not _loading_started:
        start_loading()
    if _reader is not None:
        return _reader
    if _loading_error:
        raise Exception(f"EasyOCR loading failed: {_loading_error}")
    if not _loading_done:
        return None
    return _reader

def extract_text_from_images(frames, max_images=8):
    if not frames:
        return ""
    
    reader = get_reader()
    if reader is None:
        print("⚠️ EasyOCR pas prêt → OCR côté client")
        return ""
    
    texts = []
    for i, frame_path in enumerate(frames[:max_images]):
        try:
            if not os.path.exists(frame_path):
                continue
            results = reader.readtext(frame_path, detail=0)
            text = " ".join(results)
            if text.strip():
                texts.append(text.strip())
        except Exception as e:
            print(f"OCR ERROR: {str(e)[:100]}")
    
    final_text = " ".join(texts)
    print(f"✅ OCR: {len(final_text)} caractères")
    return final_text