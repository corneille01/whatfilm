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
    
    # Noms prévus pour nos 4 images
    fichiers_images = [f"capture_{id_unique}_{i}.jpg" for i in [2, 4, 6, 10]]
    
    try:
        # OPTIMISATION 1 : On télécharge la pire qualité ('worst') pour aller extrêmement vite
        commande_yt = f"yt-dlp -o {fichier_video} -f worst --quiet {lien.url}"
        proc1 = await asyncio.create_subprocess_shell(commande_yt)
        await proc1.communicate()

        # Sécurité : vérifier que le téléchargement a bien fonctionné
        if not os.path.exists(fichier_video):
            return {"erreur": "Impossible de récupérer la vidéo (lien privé ou protégé)."}

        # OPTIMISATION 2 : Extraire les 4 images en UNE SEULE commande ffmpeg
        commande_ffmpeg = (
            f"ffmpeg -y -i {fichier_video} "
            f"-ss 00:00:02 -vframes 1 {fichiers_images[0]} "
            f"-ss 00:00:04 -vframes 1 {fichiers_images[1]} "
            f"-ss 00:00:06 -vframes 1 {fichiers_images[2]} "
            f"-ss 00:00:10 -vframes 1 {fichiers_images[3]}"
        )
        proc2 = await asyncio.create_subprocess_shell(commande_ffmpeg, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc2.communicate()

        # On supprime la vidéo immédiatement pour libérer de l'espace
        os.remove(fichier_video)

        # OPTIMISATION 3 : Charger dynamiquement les images réussies 
        # (Si la vidéo dure 5 secondes, on n'aura que les images de 2s et 4s, et ça marchera quand même)
        images_a_envoyer = []
        for img_path in fichiers_images:
            if os.path.exists(img_path):
                images_a_envoyer.append(PIL.Image.open(img_path))

        if not images_a_envoyer:
            return {"erreur": "Impossible de capturer des images."}

        # On prépare la requête IA avec le texte ET la liste des images
        prompt = 'Analyse ces images extraites d\'une même vidéo. De quel film, série ou anime sont-elles tirées ? Évalue aussi ta certitude. Réponds UNIQUEMENT avec ce format JSON : {"titre": "Nom du film", "confiance": 95} (où confiance est un nombre entier entre 0 et 100).'
        
        # L'API Gemini accepte une liste combinant texte et multiples images
        contenu_requete = [prompt] + images_a_envoyer
        reponse_ia = client.models.generate_content(model='gemini-2.5-flash', contents=contenu_requete)
        
        # Nettoyage des images du serveur
        for img_path in fichiers_images:
            if os.path.exists(img_path):
                os.remove(img_path)

        # Traitement du JSON (avec une sécurité try/except)
        trois_accents = chr(96) * 3
        texte_ia = reponse_ia.text.strip().replace(f"{trois_accents}json", "").replace(trois_accents, "").strip()
        
        try:
            data_ia = json.loads(texte_ia)
            titre_trouve = data_ia.get("titre", "")
            confiance_ia = data_ia.get("confiance", 0) # On récupère la confiance ici
        except json.JSONDecodeError:
            return {"erreur": "L'IA a mal formaté sa réponse."}

        if not titre_trouve:
            return {"erreur": "Film non reconnu."}

        # On cherche sur TMDB
        infos_film = await chercher_sur_tmdb(titre_trouve)
        
        # On injecte la confiance dans le résultat final pour que le site web l'affiche
        infos_film["confiance"] = confiance_ia
        
        return infos_film

    except Exception as e:
        # Nettoyage de secours en cas de crash
        if os.path.exists(fichier_video): os.remove(fichier_video)
        for img_path in fichiers_images:
            if os.path.exists(img_path): os.remove(img_path)
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