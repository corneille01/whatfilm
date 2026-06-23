import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

REDIS_URL = os.getenv(
    "REDIS_URL",
    ""
)

MAX_CANDIDATES = 15
MIN_CONFIDENCE = 75

TMP_DIR = "temp"
CACHE_DIR = "cache"