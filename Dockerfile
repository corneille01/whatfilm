FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    tesseract-ocr libcurl4-openssl-dev libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Playwright : pas de download auto au runtime, on l'a déjà installé au build
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp && \
    pip install --no-cache-dir gunicorn playwright curl-cffi uvicorn

# Installer Chromium une seule fois au build (pas au runtime)
RUN playwright install --with-deps chromium

COPY . .
RUN mkdir -p temp

EXPOSE 10000

# Healthcheck : Render détecte que le service est prêt
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

CMD ["gunicorn", "app:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:10000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "500", \
     "--max-requests-jitter", "50", \
     "--preload"]