FROM python:3.10-slim

# Installation des dépendances système
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    tesseract-ocr-deu \
    tesseract-ocr-ita \
    tesseract-ocr-por \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Variables d'environnement
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV EASYOCR_MODULE_PATH=/root/.EasyOCR

# Copie et installation des dépendances Python
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Installation de Playwright avec Chromium
RUN pip install --no-cache-dir playwright
RUN playwright install --with-deps chromium

# Installation de curl-cffi pour l'impersonation yt-dlp
RUN pip install --no-cache-dir curl-cffi

# Pré-téléchargement des modèles EasyOCR (évite le téléchargement au premier appel)
RUN python -c "
print('=== PRÉ-TÉLÉCHARGEMENT DES MODÈLES EASYOCR ===')
print('Ceci peut prendre 5-10 minutes...')
import easyocr
import time

start = time.time()

# Télécharger les langues principales + asiatiques
reader = easyocr.Reader(
    ['fr', 'en', 'es', 'de', 'it', 'pt', 'ch_sim', 'ch_tra', 'ja'],
    gpu=False,
    verbose=True
)

elapsed = time.time() - start
print(f'=== MODÈLES EASYOCR TÉLÉCHARGÉS EN {elapsed:.1f}s ===')
"

# Copie du projet
COPY . .

# Création des dossiers nécessaires
RUN mkdir -p temp frontend vision core data storage

# Port exposé
EXPOSE 10000

# Commande de démarrage
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000", "--workers", "1", "--timeout-keep-alive", "300"]