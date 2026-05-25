# core/retrieval.py

async def build_search_query(extraction):

    if isinstance(extraction, dict):

        terms = []

        if extraction.get("objets"):
            terms += extraction.get("objets", [])

        if extraction.get("actions"):
            terms += extraction.get("actions", [])

        if extraction.get("genre"):

            genre = extraction.get("genre")

            if isinstance(genre, list):
                terms += genre
            else:
                terms.append(str(genre))

        if extraction.get("description"):
            terms.append(extraction.get("description"))

        query = " ".join(terms)

        return query[:150]

    return str(extraction)[:150]