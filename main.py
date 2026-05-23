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
# 🌟 LE CACHE MÉMOIRE
# ==========================================
CACHE_RECHERCHES = {}


# ==========================================
# 1. LA ROUTE D'ACCUEIL (Celle qui manquait !)
# ==========================================
@app.get("/")
async def afficher_site():
    return FileResponse("index.html")


# ==========================================
# 2. FONCTION TMDB (Celle qui manquait !)
# ==========================================
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


# ==========================================
# 3. LE CERVEAU IA : ANALYSE DE LA VIDÉO
# ==========================================
@app.post("/analyser")
async def analyser_video(lien: LienVideo):
    # 1. VÉRIFICATION DU CACHE
    if lien.url in CACHE_RECHERCHES:
        return CACHE_RECHERCHES[lien.url]

    id_unique = str(uuid.uuid4())
    fichier_video = f"temp_{id_unique}.mp4"
    fichier_audio = f"audio_{id_unique}.mp3"
    fichier_info_json = f"temp_{id_unique}.info.json"
    fichiers_images = [f"capture_{id_unique}_{i}.jpg" for i in [2, 4, 6, 10]]
    fichier_gemini_audio = None
    
    try:
        # OPTIMISATION : yt-dlp télécharge aussi la description
        commande_yt = f"yt-dlp -o {fichier_video} -f worst --write-info-json --quiet {lien.url}"
        proc1 = await asyncio.create_subprocess_shell(commande_yt)
        await proc1.communicate()

        if not os.path.exists(fichier_video):
            return {"erreur": "Impossible de récupérer la vidéo."}

        # Récupération du texte de la publication (titre, hashtags, description)
        texte_publication = ""
        if os.path.exists(fichier_info_json):
            with open(fichier_info_json, "r", encoding="utf-8") as f:
                info = json.load(f)
                texte_publication = f"Titre du post : {info.get('title', '')} | Description : {info.get('description', '')}"
            os.remove(fichier_info_json)

        # Extraction des images et de l'audio
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

        os.remove(fichier_video)

        contenu_requete = []
        for img_path in fichiers_images:
            if os.path.exists(img_path):
                contenu_requete.append(PIL.Image.open(img_path))

        if not contenu_requete:
            return {"erreur": "Impossible de capturer des images."}

        if os.path.exists(fichier_audio):
            fichier_gemini_audio = client.files.upload(file=fichier_audio)
            contenu_requete.append(fichier_gemini_audio)

        # PROMPT : Le mode "Détective TikTok"
        prompt = f"""Tu es un expert en cinéma. Identifie le film, la série ou l'anime présent dans ces images et cet audio.
ATTENTION : Il s'agit d'une vidéo TikTok/Instagram.
1. La musique est souvent modifiée (Lo-Fi) : ignore-la.
2. S'il y a une voix robotique (IA), c'est un résumé de l'intrigue. ÉCOUTE ce qu'elle raconte pour déduire l'œuvre !
3. LIS les sous-titres incrustés sur les images, ils contiennent les dialogues.
4. Voici la description et les hashtags originaux du post (qui contiennent souvent le titre caché) : {texte_publication}

Analyse tout cela. Réponds UNIQUEMENT avec ce format JSON : {{"titre": "Nom du film", "confiance": 95}}. Si tu es sûr grâce au résumé ou aux hashtags, mets une confiance de 90 ou plus."""
        
        contenu_requete.insert(0, prompt)

        config = types.GenerateContentConfig(temperature=0.0)
        reponse_ia = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=contenu_requete,
            config=config
        )
        
        # Nettoyage
        for img_path in fichiers_images:
            if os.path.exists(img_path): os.remove(img_path)
        if os.path.exists(fichier_audio): os.remove(fichier_audio)
        if fichier_gemini_audio:
            client.files.delete(name=fichier_gemini_audio.name)

        trois_accents = chr(96) * 3
        texte_ia = reponse_ia.text.strip().replace(f"{trois_accents}json", "").replace(trois_accents, "").strip()
        
        try:
            data_ia = json.loads(texte_ia)
            titre_trouve = data_ia.get("titre", "")
            confiance_ia = data_ia.get("confiance", 0)
        except json.JSONDecodeError:
            return {"erreur": "L'IA a mal formaté sa réponse."}

        if not titre_trouve or titre_trouve.lower() in ["inconnu", "unknown"]:
            return {"erreur": "Film non reconnu malgré l'analyse."}

        infos_film = await chercher_sur_tmdb(titre_trouve)
        infos_film["confiance"] = confiance_ia
        
        CACHE_RECHERCHES[lien.url] = infos_film
        
        return infos_film

    except Exception as e:
        if os.path.exists(fichier_video): os.remove(fichier_video)
        if os.path.exists(fichier_audio): os.remove(fichier_audio)
        if os.path.exists(fichier_info_json): os.remove(fichier_info_json)
        for img_path in fichiers_images:
            if os.path.exists(img_path): os.remove(img_path)
        if fichier_gemini_audio:
            try: client.files.delete(name=fichier_gemini_audio.name)
            except: pass
        return {"erreur": str(e)}

# ==========================================
# 4. LA SONNETTE : LE WEBHOOK INSTAGRAM
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