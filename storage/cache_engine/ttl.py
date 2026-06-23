# storage/cache_engine/ttl.py

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# Cache par URL TikTok / Instagram / YouTube
TTL_URL = 30 * DAY

# Cache basé sur transcript + OCR
TTL_CONTENT = 90 * DAY

# Résultat incertain
TTL_UNCERTAIN = 1 * HOUR

# Résultat Gemini
TTL_GEMINI = 90 * DAY

# Résultat TMDB
TTL_TMDB = 30 * DAY

# OCR
TTL_OCR = 90 * DAY

# Sous-titres
TTL_SUBTITLE = 90 * DAY

# Verrou Redis pour éviter plusieurs appels Gemini simultanés
TTL_LOCK = 60