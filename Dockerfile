FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y ffmpeg git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Installation dans le bon ordre :
# 1. curl_cffi d'abord (binaires précompilés via wheel)
# 2. yt-dlp ensuite pour qu'il détecte curl_cffi au démarrage
# 3. Mise à jour yt-dlp à la toute dernière version
RUN pip install --no-cache-dir curl_cffi && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Vérifie que curl_cffi est bien détecté par yt-dlp
RUN yt-dlp --list-impersonate-targets 2>&1 | head -20 || true

# Pré-téléchargement modèle Whisper tiny
RUN python -c "import whisper; whisper.load_model('tiny')"

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]