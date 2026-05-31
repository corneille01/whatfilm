# vision/ocr_engine.py

import easyocr

# Initialisation différée : le modèle ne sera chargé qu'au premier appel
_reader = None

def _get_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(
            [
                'ch_sim', 'ch_tra', 'en', 'fr', 'es', 'de', 'it', 'pt',
                'nl', 'pl', 'sv', 'da', 'fi', 'no', 'cs', 'sk', 'hu',
                'ro', 'el', 'bg', 'uk', 'be', 'sr', 'hr', 'sl', 'lt',
                'lv', 'et', 'tr', 'mt', 'ga', 'cy', 'is', 'sq', 'mk',
                'bs', 'ja', 'ko', 'vi', 'th', 'ms', 'id', 'tl', 'km',
                'lo', 'hi', 'bn', 'ta', 'te', 'kn', 'mr', 'gu', 'pa',
                'ne', 'si', 'ar', 'he', 'fa', 'ur', 'ps', 'sd', 'ku',
                'ug', 'sw', 'af', 'am', 'ha', 'yo', 'zu', 'so', 'ig',
                'ru', 'be', 'uk', 'ka', 'hy', 'kk', 'uz', 'az', 'tk',
                'mi', 'sm', 'to', 'eo', 'la', 'my', 'dv', 'ti'
            ],
            gpu=False
        )
    return _reader

def extract_text_from_images(frames, max_images=8):
    reader = _get_reader()
    texts = []
    for frame in frames[:max_images]:
        try:
            results = reader.readtext(frame, detail=0)
            text = " ".join(results)
            if text.strip():
                texts.append(text.strip())
        except Exception as e:
            print("OCR ERROR =", str(e))
    final_text = " ".join(texts)
    print("FINAL OCR =", final_text)
    return final_text