# vision/visual_matcher.py

def analyze_visuals(frames):
    """
    Analyse visuelle des frames vidéo.
    Retourne objets + style + ambiance.
    """

    objects = []
    style = "unknown"
    mood = "unknown"

    # pseudo logique IA
    for frame in frames:
        # placeholder detection
        if "neon" in frame:
            style = "cyberpunk"
            mood = "dark futuristic"

        if "car" in frame:
            objects.append("car")

    return {
        "objects": list(set(objects)),
        "style": style,
        "mood": mood,
        "confidence": 0.75
    }