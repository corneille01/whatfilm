FAKE_KEYWORDS = [
    "film 2026",
    "movie 2027",
    "concept trailer",
    "fan made",
    "ai movie"
]


def detect_fake(description):
    description = description.lower()

    score = 0

    for kw in FAKE_KEYWORDS:
        if kw in description:
            score += 20

    return min(score, 100)