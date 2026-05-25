async def build_search_query(extraction):

    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    terms = []

    terms += extraction.get("objets", [])
    terms += extraction.get("actions", [])
    terms += extraction.get("genre", [])
    terms += extraction.get("possible_titles", [])

    description = extraction.get("description", "")

    if description:
        terms.append(description)

    query = " ".join(terms)

    return query[:200]