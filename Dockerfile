FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── Cache HuggingFace désactivé (embeddings retirés — contrainte mémoire Render Free 512MB)
# ENV HF_HOME=/app/.cache/huggingface
# ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
# ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    tesseract-ocr \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY . .

# ── Pré-téléchargement du modèle sentence-transformers désactivé
# (pipeline embeddings retiré — contrainte mémoire Render Free 512MB)
# RUN mkdir -p /app/.cache/huggingface /app/.cache/sentence_transformers && \
#     python3 -c "\
# from sentence_transformers import SentenceTransformer; \
# model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
# print('✅ Modèle sentence-transformers pré-chargé OK'); \
# "

RUN mkdir -p temp temp/cache

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

CMD ["gunicorn", "app:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:10000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "0", \
     "--max-requests-jitter", "0"]