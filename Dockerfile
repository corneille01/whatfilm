FROM python:3.10-slim

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
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp && \
    pip install --no-cache-dir gunicorn playwright curl-cffi

RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p temp

EXPOSE 10000

# ─────────────────────────────────────────────────────────────────
# Gunicorn + worker Uvicorn :
#   - Pas de --limit-max-requests (l'ancien "10" crashait le process
#     après 10 health checks de Render, avant même un vrai visiteur)
#   - --timeout 120 : laisse le temps à yt-dlp + EasyOCR de tourner
#   - --keep-alive 5 : connexions persistantes pour les health checks
#   - 1 worker : instance Render free tier = 512 Mo RAM, 1 CPU
# ─────────────────────────────────────────────────────────────────
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:10000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]