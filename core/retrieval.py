async def build_search_query(extraction):

    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    terms = []

    description = extraction.get("description")

    objets = extraction.get("objets", [])

    actions = extraction.get("actions", [])

    genre = extraction.get("genre", [])

    possible_titles = extraction.get(
        "possible_titles",
        []
    )

    if description:
        terms.append(description)

    if isinstance(objets, list):
        terms += objets

    if isinstance(actions, list):
        terms += actions

    if isinstance(genre, list):
        terms += genre

    if isinstance(possible_titles, list):
        terms += possible_titles

    query = " ".join([
        str(t)
        for t in terms
        if t
    ])

    return query[:150]