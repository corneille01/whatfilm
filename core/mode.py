def should_use_deep(extraction, fake_score):

    confidence_hint = len(extraction.get("objets", []))

    # FAST mode default
    if fake_score > 70:
        return False

    if confidence_hint > 10:
        return True

    return False