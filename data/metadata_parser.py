# data/metadata_parser.py

def parse_metadata(tiktok_data):
    """
    Extrait infos TikTok utiles.
    """

    return {
        "hashtags": tiktok_data.get("hashtags", []),
        "caption": tiktok_data.get("description", ""),
        "music": tiktok_data.get("music", ""),
        "language": "auto",
        "trend_score": 0.5
    }