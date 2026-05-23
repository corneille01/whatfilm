# On prend un système Linux léger avec Python
FROM python:3.10-slim

# On installe FFmpeg dans la boîte
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# On prépare le dossier de travail
WORKDIR /app

# On copie nos outils
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# On copie le code
COPY . .

# On lance l'application sur le port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]