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
from google.genai import types

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyCqA4MZT13G4XPdFT7pk1LopM7gqxOMdYo"
TMDB_API_KEY = "f97fba4e5fe525209b66fc86ee0ed227"

client = genai.Client(api_key=GEMINI_API_KEY)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class LienVideo(BaseModel):
    url: str

# ==========================================
# 🌟 NOUVEAU : LE CACHE MÉMOIRE
# ==========================================
# Ce dictionnaire va stocker les résultats. 
# Format : {"url_de_la_video": {infos_du_film}}
CACHE_RECHERCHES = {}


@app.get("/")
async def afficher_site():
    return FileResponse("index.html")


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


@app.post("/analyser")
async def analyser_video(lien: LienVideo):
    # 🌟 1. VÉRIFICATION DU CACHE : Si on connaît déjà la vidéo, on répond instantanément !
    if lien.url in CACHE_RECHERCHES:
        print("⚡ Résultat servi depuis le CACHE !")
        return CACHE_RECHERCHES[lien.url]

    id_unique = str(uuid.uuid4())
    fichier_video = f"temp_{id_unique}.mp4"
    fichier_audio = f"audio_{id_unique}.mp3"
    fichiers_images = [f"capture_{id_unique}_{i}.jpg" for i in [2, 4, 6, 10]]
    fichier_gemini_audio = None
    
    try:
        # Téléchargement ultra-rapide
        commande_yt = f"yt-dlp -o {fichier_video} -f worst --quiet {lien.url}"
        proc1 = await asyncio.create_subprocess_shell(commande_yt)
        await proc1.communicate()

        if not os.path.exists(fichier_video):
            return {"erreur": "Impossible de récupérer la vidéo."}

        # 🌟 2. EXTRACTION IMAGES + AUDIO SIMULTANÉE
        # On extrait les 4 images ET les 15 premières secondes de la piste audio (-map a? évite le crash s'il n'y a pas de son)
        commande_ffmpeg = (
            f"ffmpeg -y -i {fichier_video} "
            f"-ss 00:00:02 -vframes 1 {fichiers_images[0]} "
            f"-ss 00:00:04 -vframes 1 {fichiers_images[1]} "
            f"-ss 00:00:06 -vframes 1 {fichiers_images[2]} "
            f"-ss 00:00:10 -vframes 1 {fichiers_images[3]} "
            f"-t 15 -q:a 9 -map a? {fichier_audio}"
        )
        proc2 = await asyncio.create_subprocess_shell(commande_ffmpeg, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc2.communicate()

        os.remove(fichier_video) # Nettoyage vidéo

        # Préparation des images
        contenu_requete = []
        for img_path in fichiers_images:
            if os.path.exists(img_path):
                contenu_requete.append(PIL.Image.open(img_path))

        if not contenu_requete:
            return {"erreur": "Impossible de capturer des images."}

        # 🌟 3. AJOUT DE L'AUDIO POUR L'IA
        if os.path.exists(fichier_audio):
            # On upload temporairement l'audio sur les serveurs de Gemini pour qu'il l'écoute
            fichier_gemini_audio = client.files.upload(file=fichier_audio)
            contenu_requete.append(fichier_gemini_audio)

        prompt = 'Analyse ces images et cet extrait audio (s\'il est présent). De quel film, série ou anime proviennent-ils ? Écoute attentivement les dialogues et les voix. Évalue aussi ta certitude. Réponds UNIQUEMENT avec ce format JSON : {"titre": "Nom du film", "confiance": 95}. Si tu ne sais pas, renvoie un taux de confiance bas.'
        contenu_requete.insert(0, prompt)

        # 🌟 4. TEMPÉRATURE = 0 (ZÉRO HALLUCINATION)
        config = types.GenerateContentConfig(temperature=0.0)
        reponse_ia = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=contenu_requete,
            config=config
        )
        
        # Nettoyage des fichiers locaux et distants
        for img_path in fichiers_images:
            if os.path.exists(img_path): os.remove(img_path)
        if os.path.exists(fichier_audio): os.remove(fichier_audio)
        if fichier_gemini_audio:
            client.files.delete(name=fichier_gemini_audio.name)

        # Traitement du JSON
        trois_accents = chr(96) * 3
        texte_ia = reponse_ia.text.strip().replace(f"{trois_accents}json", "").replace(trois_accents, "").strip()
        
        try:
            data_ia = json.loads(texte_ia)
            titre_trouve = data_ia.get("titre", "")
            confiance_ia = data_ia.get("confiance", 0)
        except json.JSONDecodeError:
            return {"erreur": "L'IA a mal formaté sa réponse."}

        if not titre_trouve:
            return {"erreur": "Film non reconnu."}

        # Recherche TMDB et préparation du résultat final
        infos_film = await chercher_sur_tmdb(titre_trouve)
        infos_film["confiance"] = confiance_ia
        
        # 🌟 5. ENREGISTREMENT DANS LE CACHE POUR LA PROCHAINE FOIS
        CACHE_RECHERCHES[lien.url] = infos_film
        
        return infos_film

    except Exception as e:
        if os.path.exists(fichier_video): os.remove(fichier_video)
        if os.path.exists(fichier_audio): os.remove(fichier_audio)
        for img_path in fichiers_images:
            if os.path.exists(img_path): os.remove(img_path)
        if fichier_gemini_audio:
            try: client.files.delete(name=fichier_gemini_audio.name)
            except: pass
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