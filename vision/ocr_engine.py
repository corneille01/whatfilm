# vision/ocr_engine.py
import easyocr
import time
import threading
import sys

_reader = None
_loading_thread = None
_loading_started = False
_loading_done = False
_loading_error = None

def _load_model():
    """Charge le modèle dans un thread séparé"""
    global _reader, _loading_done, _loading_error
    try:
        print("🔄 Chargement EasyOCR en arrière-plan...")
        sys.stdout.flush()
        start = time.time()
        
        _reader = easyocr.Reader(
            ['fr', 'en', 'es', 'de', 'it', 'pt', 'ch_sim', 'ch_tra', 'ja',
             'nl', 'pl', 'sv', 'da', 'fi', 'no', 'cs', 'sk', 'hu',
             'ro', 'el', 'bg', 'uk', 'sr', 'hr', 'sl', 'lt', 'lv', 'et',
             'tr', 'ja', 'ko', 'vi', 'th', 'ms', 'id', 'tl',
             'hi', 'bn', 'ta', 'te', 'kn', 'mr', 'gu', 'pa', 'ne', 'si',
             'ar', 'he', 'fa', 'ur', 'sw', 'af',
             'ru', 'ka', 'hy', 'kk', 'uz', 'az', 'tk'],
            gpu=False,
            verbose=False
        )
        
        elapsed = time.time() - start
        print(f"✅ EasyOCR chargé en {elapsed:.1f}s")
        sys.stdout.flush()
        _loading_done = True
        
    except Exception as e:
        print(f"❌ Erreur chargement EasyOCR: {e}")
        _loading_error = str(e)
        _loading_done = True

def start_loading():
    """Démarre le chargement en arrière-plan"""
    global _loading_started, _loading_thread
    if not _loading_started:
        _loading_started = True
        _loading_thread = threading.Thread(target=_load_model, daemon=True)
        _loading_thread.start()
        print("🚀 Thread EasyOCR démarré")

def get_reader():
    """Retourne le reader, charge si nécessaire"""
    global _reader, _loading_done, _loading_error
    
    # Démarrer le chargement si pas encore fait
    if not _loading_started:
        start_loading()
    
    # Si déjà chargé, retourner directement
    if _reader is not None:
        return _reader
    
    # Si erreur, la remonter
    if _loading_error:
        raise Exception(f"EasyOCR loading failed: {_loading_error}")
    
    # Si pas encore prêt, retourner None (le frontend fera l'OCR)
    if not _loading_done:
        print("⏳ EasyOCR pas encore prêt")
        return None
    
    return _reader

def extract_text_from_images(frames, max_images=8):
    """
    Extrait le texte des images.
    Si le modèle n'est pas prêt, retourne une chaîne vide
    (le frontend fera l'OCR côté client)
    """
    if not frames:
        return ""
    
    reader = get_reader()
    
    # Si le modèle n'est pas encore chargé, on skip l'OCR serveur
    if reader is None:
        print("⚠️ EasyOCR pas prêt → OCR sera fait côté client")
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
    print(f"OCR: {len(final_text)} caractères extraits")
    return final_text

# Ajouter l'import manquant
import os