# vision/ocr_engine.py
# EasyOCR retiré : charge 400 MB+ de modèles PyTorch → OOM sur Render free (512 MB)
# L'OCR est délégué à Tesseract.js côté client (déjà dans index.html)
# Le serveur retourne toujours "" → app.py déclenche le fallback client

def start_loading():
    print("ℹ️  OCR côté client actif (Tesseract.js)", flush=True)

def get_reader():
    return None

def extract_text_from_images(frames, max_images=6):
    return ""