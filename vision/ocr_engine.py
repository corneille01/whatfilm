# vision/ocr_engine.py

import easyocr

# Initialisation unique du lecteur EasyOCR avec une large couverture linguistique
# Les codes ci-dessous couvrent la plupart des langues et écritures utilisées dans les vidéos internationales.
reader = easyocr.Reader(
    [
        # Langues à écriture chinoise
        'ch_sim',   # Chinois simplifié
        'ch_tra',   # Chinois traditionnel
        # Langues européennes majeures
        'en',       # Anglais
        'fr',       # Français
        'es',       # Espagnol
        'de',       # Allemand
        'it',       # Italien
        'pt',       # Portugais
        'nl',       # Néerlandais
        'pl',       # Polonais
        'sv',       # Suédois
        'da',       # Danois
        'fi',       # Finnois
        'no',       # Norvégien
        'cs',       # Tchèque
        'sk',       # Slovaque
        'hu',       # Hongrois
        'ro',       # Roumain
        'el',       # Grec
        'bg',       # Bulgare
        'uk',       # Ukrainien
        'be',       # Biélorusse
        'sr',       # Serbe (cyrillique)
        'hr',       # Croate
        'sl',       # Slovène
        'lt',       # Lituanien
        'lv',       # Letton
        'et',       # Estonien
        'tr',       # Turc
        'mt',       # Maltais
        'ga',       # Irlandais
        'cy',       # Gallois
        'is',       # Islandais
        'sq',       # Albanais
        'mk',       # Macédonien
        'bs',       # Bosniaque
        # Langues d'Asie orientale
        'ja',       # Japonais
        'ko',       # Coréen
        # Langues d'Asie du Sud-Est
        'vi',       # Vietnamien
        'th',       # Thaï
        'ms',       # Malais
        'id',       # Indonésien
        'tl',       # Philippin (tagalog)
        'km',       # Khmer (cambodgien) – nécessite le support EasyOCR
        'lo',       # Lao – nécessite le support EasyOCR
        # Langues d'Asie du Sud
        'hi',       # Hindi
        'bn',       # Bengali
        'ta',       # Tamoul
        'te',       # Télougou
        'kn',       # Kannada
        'mr',       # Marathi
        'gu',       # Gujarati
        'pa',       # Pendjabi
        'ne',       # Népalais
        'si',       # Cinghalais
        # Langues du Moyen-Orient
        'ar',       # Arabe
        'he',       # Hébreu
        'fa',       # Persan (farsi)
        'ur',       # Ourdou
        'ps',       # Pachto
        'sd',       # Sindhi
        'ku',       # Kurde (latin)
        'ug',       # Ouïghour (arabe)
        # Langues d'Afrique
        'sw',       # Swahili
        'af',       # Afrikaans
        'am',       # Amharique (éthiopien)
        'ha',       # Haoussa (latin)
        'yo',       # Yoruba
        'zu',       # Zoulou
        'so',       # Somali
        'ig',       # Igbo
        # Langues slaves orientales et baltes
        'ru',       # Russe
        'be',       # Biélorusse
        'uk',       # Ukrainien
        # Langues caucasiennes (si supportées)
        'ka',       # Géorgien
        'hy',       # Arménien
        # Langues d'Asie centrale
        'kk',       # Kazakh (cyrillique)
        'uz',       # Ouzbek (latin/cyrillique)
        'az',       # Azéri (latin)
        'tk',       # Turkmène (latin)
        # Langues d'Océanie (si disponibles)
        'mi',       # Maori
        'sm',       # Samoan
        'to',       # Tongien
        # Langues construites / divers
        'eo',       # Espéranto
        'la',       # Latin
        'my',       # Birman (si supporté)
        'dv',       # Dhivehi (si supporté)
        'ti',       # Tigrigna (si supporté)
    ],
    gpu=False  # Mets True si tu as un GPU disponible
)

def extract_text_from_images(frames, max_images=8):
    """
    Extrait le texte de toutes les frames fournies en utilisant EasyOCR.
    La détection de la langue est automatique.
    """
    texts = []
    for frame in frames[:max_images]:
        try:
            # detail=0 renvoie directement le texte reconnu
            results = reader.readtext(frame, detail=0)
            text = " ".join(results)
            if text.strip():
                texts.append(text.strip())
        except Exception as e:
            print("OCR ERROR =", str(e))

    final_text = " ".join(texts)
    print("FINAL OCR =", final_text)
    return final_text