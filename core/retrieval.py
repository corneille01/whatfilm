async def build_search_query(extraction):

    if isinstance(extraction, dict):

        terms = []

        description = extraction.get("description", "")

        objets = extraction.get("objets", [])

        actions = extraction.get("actions", [])

        genre = extraction.get("genre", [])

        if description:
            terms.append(description)

        terms += objets
        terms += actions
        terms += genre

        query = " ".join(terms)

        return query[:150]

    return str(extraction)[:150]