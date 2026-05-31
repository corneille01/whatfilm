# vision/ocr_engine.py

import easyocr
import time
import sys

# Initialisation différée : le modèle ne sera chargé qu'au premier appel
_reader = None
_reader_loading = False
_reader_start_time = 0

def _get_reader():
    global _reader, _reader_loading, _reader_start_time
    
    # Si déjà chargé, retourner directement
    if _reader is not None:
        return _reader
    
    # Si en cours de chargement, attendre (avec timeout)
    if _reader_loading:
        print("⏳ EasyOCR déjà en cours de chargement, patience...")
        timeout = 300  # 5 minutes max
        while _reader_loading and (time.time() - _reader_start_time) < timeout:
            time.sleep(2)
            print("   ...attente chargement EasyOCR...")
        if _reader is None:
            raise Exception(f"Timeout après {timeout}s de chargement EasyOCR")
        return _reader
    
    # Premier chargement
    _reader_loading = True
    _reader_start_time = time.time()
    
    try:
        print("🔄 Début chargement EasyOCR (1ère fois = téléchargement des modèles)...")
        print("   Ceci peut prendre 2-5 minutes selon votre connexion...")
        sys.stdout.flush()  # Forcer l'affichage immédiat
        
        start = time.time()
        
        _reader = easyocr.Reader(
            [
                # Langues principales (chargées en premier)
                'fr', 'en', 'es', 'de', 'it', 'pt',
                # Langues asiatiques
                'ch_sim', 'ch_tra', 'ja', 'ko', 'vi', 'th',
                # Langues européennes
                'nl', 'pl', 'sv', 'da', 'fi', 'no', 'cs', 'sk', 'hu',
                'ro', 'el', 'bg', 'uk', 'be', 'sr', 'hr', 'sl', 'lt',
                'lv', 'et', 'tr', 'mt', 'ga', 'cy', 'is', 'sq', 'mk',
                'bs',
                # Langues d'Asie du Sud-Est
                'ms', 'id', 'tl', 'km', 'lo', 'my',
                # Langues indiennes
                'hi', 'bn', 'ta', 'te', 'kn', 'mr', 'gu', 'pa', 'ne', 'si',
                # Langues moyen-orientales
                'ar', 'he', 'fa', 'ur', 'ps', 'sd', 'ku', 'ug',
                # Langues africaines
                'sw', 'af', 'am', 'ha', 'yo', 'zu', 'so', 'ig',
                # Langues slaves
                'ru', 'ka', 'hy', 'kk', 'uz', 'az', 'tk',
                # Langues océaniennes
                'mi', 'sm', 'to',
                # Autres
                'eo', 'la', 'dv', 'ti'
            ],
            gpu=False,
            verbose=True  # Pour voir la progression
        )
        
        elapsed = time.time() - start
        print(f"✅ EasyOCR chargé en {elapsed:.1f} secondes")
        sys.stdout.flush()
        
        return _reader
        
    except Exception as e:
        print(f"❌ ERREUR chargement EasyOCR: {e}")
        raise
    finally:
        _reader_loading = False


def extract_text_from_images(frames, max_images=8):
    """
    Extrait le texte des images avec timeout et gestion d'erreurs
    """
    if not frames:
        print("⚠️ OCR: Aucune frame fournie")
        return ""
    
    print(f"🔍 OCR: Début extraction sur {min(len(frames), max_images)} images...")
    sys.stdout.flush()
    
    try:
        reader = _get_reader()
    except Exception as e:
        print(f"❌ OCR: Impossible de charger EasyOCR: {e}")
        return ""
    
    texts = []
    start_time = time.time()
    
    for i, frame_path in enumerate(frames[:max_images]):
        # Timeout par image : 30 secondes max
        if time.time() - start_time > 120:  # 2 minutes total max
            print(f"⏱️ OCR: Timeout global après {len(texts)} images traitées")
            break
            
        print(f"   OCR image {i+1}/{min(len(frames), max_images)}...")
        sys.stdout.flush()
        
        try:
            # Vérifier que le fichier existe
            import os
            if not os.path.exists(frame_path):
                print(f"   ⚠️ Fichier introuvable: {frame_path}")
                continue
                
            results = reader.readtext(frame_path, detail=0)
            text = " ".join(results)
            
            if text.strip():
                texts.append(text.strip())
                print(f"   ✅ Texte extrait: {len(text)} caractères")
            else:
                print(f"   ℹ️ Aucun texte détecté")
                
        except Exception as e:
            print(f"   ❌ OCR ERROR image {i}: {str(e)[:100]}")
            continue
    
    final_text = " ".join(texts)
    elapsed = time.time() - start_time
    print(f"🏁 OCR terminé en {elapsed:.1f}s: {len(final_text)} caractères extraits")
    print(f"   Texte: {final_text[:200]}...")
    sys.stdout.flush()
    
    return final_text