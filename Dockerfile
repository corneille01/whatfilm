# Système Linux léger avec Python
FROM python:3.10-slim

# FFmpeg + dépendances système en UNE SEULE commande (bonne pratique Docker)
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# On installe d'abord les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# On pré-télécharge le modèle Whisper "tiny" au moment du BUILD
# → Comme ça il est dans l'image Docker, pas besoin de le télécharger à chaque démarrage
# → Si tu veux plus de précision (plan Render 7$/mois), remplace "tiny" par "base"
RUN python -c "import whisper; whisper.load_model('tiny')"

# On copie le code
COPY . .

# Lancement sur le port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]