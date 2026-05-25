EXTRACTION_PROMPT = """
Analyse uniquement les éléments observables.

Retourne STRICTEMENT un JSON.

{
  "personnages": [],
  "objets": [],
  "lieux": [],
  "actions": [],
  "genre": [],
  "dialogues_importants": [],
  "ambiance": [],
  "probable_fake_ai": 0
}
"""

RERANK_PROMPT = """
Tu es un moteur de vérification de films.

Tu ne dois JAMAIS inventer.

Retourne uniquement JSON :

{
  "meilleur_titre": "",
  "score": 0,
  "raison": ""
}
"""