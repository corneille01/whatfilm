import os
import uuid
import json
import asyncio
import PIL.Image
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai

# --- CONFIGURATION (Assure-toi de mettre tes 2 vraies clés ici) ---
GEMINI_API_KEY = "AIzaSyCqA4MZT13G4XPdFT7pk1LopM7gqxOMdYo"
TMDB_API_KEY = "f97fba4e5fe525209b66fc86ee0ed227"

# Les clés Meta sont en attente, on les commente :
# META_VERIFY_TOKEN = "MON_MOT_DE_PASSE_SECRET_META"
# META_ACCESS_TOKEN = "TON_TOKEN_INSTAGRAM"

client = genai.Client(api_key=GEMINI_API_KEY)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class LienVideo(BaseModel):
    url: str

# 1. LA ROUTE POUR AFFICHER TON SITE WEB
@app.get("/")
async def afficher_site():
    # Quand quelqu'un va sur ton lien, le serveur lui donne le fichier HTML
    return FileResponse("index.html")

# 2. FONCTION POUR INTERROGER TMDB (L'annuaire des films)
async def chercher_sur_tmdb(titre):
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={titre}&language=fr-FR"
    async with httpx.AsyncClient() as client_http:
        reponse = await client_http.get(url)
        data = reponse.json()
        if data.get("results") and len(data["results"]) > 0:
            premier_resultat = data["results"][0]
            chemin_affiche = premier_resultat.get("poster_path")
            return {
                "titre": premier_resultat.get("title", premier_resultat.get("name", titre)),
                "affiche": f"https://image.tmdb.org/t/p/w500{chemin_affiche}" if chemin_affiche else "",
                "lien_streaming": f"https://www.justwatch.com/fr/recherche?q={titre}"
            }
    return {"titre": titre, "affiche": "", "lien_streaming": "Non trouvé"}

# 3. LE CERVEAU : L'ANALYSE DE LA VIDÉO
@app.post("/analyser")
async def analyser_video(lien: LienVideo):
    id_unique = str(uuid.uuid4())
    fichier_video = f"temp_{id_unique}.mp4"
    fichier_image = f"capture_{id_unique}.jpg"
    
    try:
        commande_yt = f"yt-dlp -o {fichier_video} -f best --quiet {lien.url}"
        proc1 = await asyncio.create_subprocess_shell(commande_yt)
        await proc1.communicate()

        commande_ffmpeg = f"ffmpeg -y -i {fichier_video} -ss 00:00:03 -vframes 1 {fichier_image}"
        proc2 = await asyncio.create_subprocess_shell(commande_ffmpeg, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc2.communicate()

        if os.path.exists(fichier_video):
            os.remove(fichier_video)

        if os.path.exists(fichier_image):
            img = PIL.Image.open(fichier_image)
            prompt = 'Analyse cette image. De quel film, série ou anime est-elle tirée ? Réponds UNIQUEMENT avec ce format JSON : {"titre": "Nom du film"}'
            
            reponse_ia = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, img])
            
            # ---> LA CORRECTION EST ICI <---
            trois_accents = chr(96) * 3
            texte_ia = reponse_ia.text.strip().replace(f"{trois_accents}json", "").replace(trois_accents, "").strip()
            # --------------------------------
            
            data_ia = json.loads(texte_ia)
            titre_trouve = data_ia.get("titre", "")

            os.remove(fichier_image)

            infos_film = await chercher_sur_tmdb(titre_trouve)
            return infos_film
        else:
            return {"erreur": "Capture impossible"}

    except Exception as e:
        if os.path.exists(fichier_video): os.remove(fichier_video)
        if os.path.exists(fichier_image): os.remove(fichier_image)
        return {"erreur": str(e)}

# ==========================================
# 4. LA SONNETTE : LE WEBHOOK INSTAGRAM
# (En pause le temps d'avoir les clés)
# ==========================================
# @app.get("/webhook")
# async def verifier_webhook(request: Request):
#     mode = request.query_params.get("hub.mode")
#     token = request.query_params.get("hub.verify_token")
#     challenge = request.query_params.get("hub.challenge")
#
#     if mode == "subscribe" and token == META_VERIFY_TOKEN:
#         return int(challenge)
#     raise HTTPException(status_code=403, detail="Token invalide")
#
# @app.post("/webhook")
# async def recevoir_message(request: Request):
#     data = await request.json()
#     print("🔔 Dring ! Meta a sonné à la porte :", data)
#     return {"status": "ok"}