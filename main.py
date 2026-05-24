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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LienVideo(BaseModel):
    url: str

# ==========================================
# 🌟 CACHE MÉMOIRE
# ==========================================
CACHE_RECHERCHES = {}
CACHE_ECHECS = {}

# ==========================================
# 1. ROUTE D'ACCUEIL
# ==========================================
@app.get("/")
async def afficher_site():
    return FileResponse("index.html")

# ==========================================
# 2. TMDB : RECHERCHE DU FILM
# ==========================================
async def chercher_sur_tmdb(titre: str) -> dict:
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={titre}&language=fr-FR"
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        data = r.json()

    if data.get("results") and len(data["results"]) > 0:
        res = data["results"][0]
        chemin = res.get("poster_path")
        return {
            "titre": res.get("title", res.get("name", titre)),
            "affiche": f"https://image.tmdb.org/t/p/w500{chemin}" if chemin else "",
            "lien_streaming": f"https://www.justwatch.com/fr/recherche?q={titre}",
        }
    return {"titre": titre, "affiche": "", "lien_streaming": "Non trouvé"}

# ==========================================
# 3. EXTRACTION DES SOUS-TITRES VIA WHISPER
# ==========================================
async def extraire_sous_titres_whisper(fichier_audio: str) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            f"whisper {fichier_audio} --model tiny --language fr --output_format txt --output_dir /tmp --quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=45)
        base = os.path.splitext(os.path.basename(fichier_audio))[0]
        txt_path = f"/tmp/{base}.txt"
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                contenu = f.read().strip()
            os.remove(txt_path)
            return contenu
    except Exception as e:
        print(f"[DEBUG] Erreur Whisper: {e}")
    return ""

# ==========================================
# 4. LE PROMPT MAÎTRE ANTI-HALLUCINATION
# ==========================================
PROMPT_TEMPLATE = """Tu es un détective spécialisé dans l'identification de films, séries et animes.

━━━ INDICES DISPONIBLES ━━━
{texte_publication}

TRANSCRIPTION AUDIO (voix IA ou dialogues) :
{transcription}

Les images et l'audio joints complètent ces indices.

━━━ RÈGLES STRICTES ━━━
RÈGLE 1 — PRIORITÉ DES INDICES (dans cet ordre) :
  1. Les HASHTAGS et la DESCRIPTION du post contiennent souvent le titre exact → cherche "#NomDuFilm"
  2. La TRANSCRIPTION contient le résumé de l'intrigue → déduis le film à partir de l'histoire racontée
  3. Les DIALOGUES visibles sur les images (sous-titres incrustés)
  4. Les acteurs/décors sur les images

RÈGLE 2 — ZÉRO HALLUCINATION :
  - Si tu n'es pas sûr, DIS-LE avec une confiance basse (< 50)
  - Mieux vaut confiance = 20 que d'inventer un titre
  - Ne te base PAS sur la musique de fond (souvent modifiée/Lo-Fi)

RÈGLE 3 — FORMAT DE RÉPONSE STRICT :
  Réponds UNIQUEMENT avec ce JSON :
  {{"titre": "Titre exact du film", "confiance": 85, "raison": "explication brève"}}
  
  Si introuvable : 
  {{"titre": "inconnu", "confiance": 0, "raison": "Aucun indice"}}
"""

# ==========================================
# 5. ANALYSE PRINCIPALE
# ==========================================
@app.post("/analyser")
async def analyser_video(lien: LienVideo):
    url = lien.url.strip()

    # VÉRIFICATION DU CACHE
    if url in CACHE_RECHERCHES:
        return CACHE_RECHERCHES[url]
    if url in CACHE_ECHECS:
        return {"erreur": "Film non reconnu (résultat en cache)"}

    id_unique = str(uuid.uuid4())[:8]
    fichier_video = f"temp_{id_unique}.mp4"
    fichier_audio = f"audio_{id_unique}.mp3"
    fichier_info = f"temp_{id_unique}.info.json"
    fichier_gemini_audio = None
    
    texte_publication = ""
    transcription = ""
    images_valides = []

    try:
        # 🌟 TÉLÉCHARGEMENT
        print(f"[DEBUG] Lancement yt-dlp classique sur : {url}")
        commande_yt = f"yt-dlp -o {fichier_video} -f worst --write-info-json --quiet {url}"
        proc1 = await asyncio.create_subprocess_shell(commande_yt)
        await asyncio.wait_for(proc1.communicate(), timeout=60)

        if not os.path.exists(fichier_video):
            return {"erreur": "Impossible de télécharger la vidéo avec yt-dlp."}

        # 🌟 LECTURE DES MÉTADONNÉES
        if os.path.exists(fichier_info):
            with open(fichier_info, "r", encoding="utf-8") as f:
                info = json.load(f)
            os.remove(fichier_info)
            tags = " ".join(info.get("tags", []))
            texte_publication = f"TITRE: {info.get('title', '')}\nDESC: {info.get('description', '')}\nHASHTAGS: {tags}"

        # 🌟 EXTRACTION 8 IMAGES ET AUDIO
        cmd_ffmpeg = (
            f"ffmpeg -y -i {fichier_video} "
            f"-vf fps=8/30 "
            f"cap_{id_unique}_%d.jpg "
            f"-t 30 -q:a 5 -map a? {fichier_audio} -loglevel error"
        )
        proc2 = await asyncio.create_subprocess_shell(cmd_ffmpeg)
        await proc2.communicate()

        os.remove(fichier_video)

        for i in range(1, 10):
            img = f"cap_{id_unique}_{i}.jpg"
            if os.path.exists(img):
                images_valides.append(img)

        if not images_valides:
            return {"erreur": "Impossible de capturer des images de la vidéo."}

        # 🌟 TRANSCRIPTION WHISPER
        if os.path.exists(fichier_audio):
            transcription = await extraire_sous_titres_whisper(fichier_audio)

        # 🌟 CONSTRUCTION DE LA REQUÊTE IA
        prompt = PROMPT_TEMPLATE.format(
            texte_publication=texte_publication or "Non disponible",
            transcription=transcription or "Non disponible (audio muet ou musical)",
        )
        
        contenu_requete = [prompt]
        
        # ==========================================
        # 🔎 LOGS DÉTAILLÉS (MODE DEBUG EXTRÊME)
        # ==========================================
        print("\n" + "="*60)
        print("🤖 [DEBUG EXTRÊME] ENVOI À L'IA")
        print("="*60)
        print("📝 PROMPT ET TEXTE :")
        print(prompt)
        print("-" * 60)
        print("📸 IMAGES JOINTES :")
        
        for img_path in images_valides:
            try: 
                img_obj = PIL.Image.open(img_path)
                taille_ko = os.path.getsize(img_path) / 1024
                print(f"  - {img_path} | {img_obj.width}x{img_obj.height} px | {taille_ko:.1f} Ko")
                contenu_requete.append(img_obj)
            except Exception as e:
                print(f"  - Erreur chargement image {img_path} : {e}")

        print("-" * 60)
        if os.path.exists(fichier_audio):
            fichier_gemini_audio = client.files.upload(file=fichier_audio)
            contenu_requete.append(fichier_gemini_audio)
            print(f"🎵 AUDIO JOINT : Oui | URI Google: {fichier_gemini_audio.uri}")
        else:
            print("🎵 AUDIO JOINT : Non (Fichier inexistant)")
        print("="*60 + "\n")
        # ==========================================

        # 🌟 APPEL GEMINI
        config = types.GenerateContentConfig(temperature=0.0)
        reponse_ia = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=contenu_requete,
            config=config
        )

        # ==========================================
        # 🔎 LOG DE LA RÉPONSE DE L'IA
        # ==========================================
        print("\n" + "="*60)
        print("🧠 [DEBUG EXTRÊME] RÉPONSE BRUTE DE L'IA :")
        print("="*60)
        print(reponse_ia.text)
        print("="*60 + "\n")
        # ==========================================

    except asyncio.TimeoutError:
        return {"erreur": "Délai dépassé. La vidéo est trop longue à analyser."}
    except Exception as e:
        return {"erreur": f"Erreur système : {str(e)}"}
    finally:
        # Nettoyage méticuleux en cas de succès ou de plantage
        if os.path.exists(fichier_video): os.remove(fichier_video)
        if os.path.exists(fichier_audio): os.remove(fichier_audio)
        if os.path.exists(fichier_info): os.remove(fichier_info)
        for img in images_valides:
            if os.path.exists(img): os.remove(img)
        # On supprime toutes les images potentielles restantes
        for i in range(1, 15):
            img = f"cap_{id_unique}_{i}.jpg"
            if os.path.exists(img): os.remove(img)
        if fichier_gemini_audio:
            try: client.files.delete(name=fichier_gemini_audio.name)
            except: pass

    # 🌟 PARSING DU RÉSULTAT JSON
    trois_accents = chr(96) * 3
    texte_ia = reponse_ia.text.strip().replace(f"{trois_accents}json", "").replace(trois_accents, "").strip()
    
    try:
        data_ia = json.loads(texte_ia)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", texte_ia, re.DOTALL)
        if match:
            try: data_ia = json.loads(match.group())
            except: return {"erreur": "L'IA a mal formaté sa réponse."}
        else:
            return {"erreur": "L'IA a mal formaté sa réponse."}

    titre_trouve = data_ia.get("titre", "").strip()
    confiance_ia = int(data_ia.get("confiance", 0))
    raison = data_ia.get("raison", "")

    # Traitement des échecs (inconnu ou confiance très basse)
    if not titre_trouve or titre_trouve.lower() in ["inconnu", "unknown"] or confiance_ia < 20:
        CACHE_ECHECS[url] = True
        return {"erreur": f"Film non reconnu. Raison : {raison}"}

    # Recherche TMDB
    infos_film = await chercher_sur_tmdb(titre_trouve)
    infos_film["confiance"] = confiance_ia
    infos_film["raison"] = raison
    
    # Enregistrement en cache
    CACHE_RECHERCHES[url] = infos_film
    
    return infos_film


# ==========================================
# 7. WEBHOOK META (prêt pour le bot)
# ==========================================
# META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "mon_token_secret")


# @app.get("/webhook")
# async def verifier_webhook(request: Request):
#     mode = request.query_params.get("hub.mode")
#     token = request.query_params.get("hub.verify_token")
#     challenge = request.query_params.get("hub.challenge")
#     if mode == "subscribe" and token == META_VERIFY_TOKEN:
#         return int(challenge)
#     raise HTTPException(status_code=403, detail="Token invalide")


# @app.post("/webhook")
# async def recevoir_message(request: Request):
#     """
#     Reçoit les messages Instagram/Facebook et déclenche l'analyse.
#     Format attendu : l'utilisateur mentionne @BotName + colle un lien vidéo.
#     """
#     data = await request.json()

#     try:
#         # Extraction du message entrant (format Meta Messenger)
#         entries = data.get("entry", [])
#         for entry in entries:
#             for event in entry.get("messaging", []):
#                 message = event.get("message", {})
#                 texte = message.get("text", "")
#                 sender_id = event.get("sender", {}).get("id")

#                 # Cherche un lien vidéo dans le message
#                 import re
#                 liens = re.findall(
#                     r"https?://(?:www\.)?(?:tiktok\.com|instagram\.com|youtube\.com|youtu\.be)\S+",
#                     texte,
#                 )
#                 if liens and sender_id:
#                     # Lance l'analyse en arrière-plan (ne bloque pas la réponse webhook)
#                     asyncio.create_task(
#                         analyser_et_repondre_messenger(liens[0], sender_id)
#                     )
#     except Exception as e:
#         print(f"Erreur webhook : {e}")

#     return {"status": "ok"}


# async def analyser_et_repondre_messenger(url: str, sender_id: str):
#     """Analyse la vidéo et envoie le résultat via l'API Messenger."""
#     resultat = await analyser_video(LienVideo(url=url))
#     PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
#     if not PAGE_ACCESS_TOKEN:
#         return

#     if "erreur" in resultat:
#         texte_reponse = f"❌ {resultat['erreur']}"
#     else:
#         conf = resultat.get("confiance", "?")
#         titre = resultat.get("titre", "?")
#         lien = resultat.get("lien_streaming", "")
#         texte_reponse = (
#             f"🎬 *{titre}*\n"
#             f"Confiance IA : {conf}%\n"
#             f"Où regarder : {lien}"
#         )

#     async with httpx.AsyncClient() as c:
#         await c.post(
#             f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
#             json={
#                 "recipient": {"id": sender_id},
#                 "message": {"text": texte_reponse},
#             },
#         )