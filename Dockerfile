FROM python:3.10-slim

# FFmpeg + curl (requis par curl_cffi pour imiter Chrome sur TikTok)
RUN apt-get update && \
    apt-get install -y ffmpeg git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Installation des dépendances + mise à jour yt-dlp à la dernière version
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp && \
    pip install --no-cache-dir curl_cffi

# Pré-téléchargement du modèle Whisper tiny au moment du build
# → evite le téléchargement au premier démarrage
RUN python -c "import whisper; whisper.load_model('tiny')"

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]