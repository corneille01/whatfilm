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
# 🌟 CACHE MÉMOIRE (résultats + échecs)
# ==========================================
CACHE_RECHERCHES: dict = {}
CACHE_ECHECS: dict = {}  # Pour ne pas re-analyser les vidéos inconnues


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
    url = (
        f"https://api.themoviedb.org/3/search/multi"
        f"?api_key={TMDB_API_KEY}&query={titre}&language=fr-FR"
    )
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        data = r.json()

    if data.get("results"):
        res = data["results"][0]
        chemin = res.get("poster_path")
        return {
            "titre": res.get("title", res.get("name", titre)),
            "affiche": f"https://image.tmdb.org/t/p/w500{chemin}" if chemin else "",
            "lien_streaming": f"https://www.justwatch.com/fr/recherche?q={titre}",
        }
    return {"titre": titre, "affiche": "", "lien_streaming": "Non trouvé"}


# ==========================================
# 3. EXTRACTION DES SOUS-TITRES INCRUSTÉS
#    via Whisper (speech-to-text local)
# ==========================================
async def extraire_sous_titres_whisper(fichier_audio: str) -> str:
    """
    Transcrit l'audio avec whisper-cli si disponible.
    Retourne le texte ou une chaîne vide en cas d'échec.
    On utilise le modèle 'base' pour la rapidité (< 3s sur un audio de 30s).
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            # Modèle "tiny" = gratuit, léger (~400MB RAM), parfait pour Render plan gratuit
            # Si tu passes au plan 7$/mois → remplace "tiny" par "base" pour plus de précision
            f"whisper {fichier_audio} --model tiny --language fr --output_format txt --output_dir /tmp --quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        base = os.path.splitext(os.path.basename(fichier_audio))[0]
        txt_path = f"/tmp/{base}.txt"
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                contenu = f.read().strip()
            os.remove(txt_path)
            return contenu
    except Exception:
        pass
    return ""


# ==========================================
# 4. STRATÉGIE ANTI-HALLUCINATION
#    → Extraction MAXIMALE avant d'envoyer à Gemini
# ==========================================
async def extraire_contexte_complet(url: str, id_unique: str) -> dict:
    """
    Télécharge la vidéo, extrait :
    - title + description + hashtags du post (yt-dlp)
    - transcription audio complète (whisper)
    - 8 captures d'écran réparties sur toute la durée
    - durée totale de la vidéo
    Retourne un dictionnaire de contexte.
    """
    fichier_video = f"temp_{id_unique}.mp4"
    fichier_audio = f"audio_{id_unique}.mp3"
    fichier_info = f"temp_{id_unique}.info.json"
    contexte = {
        "texte_publication": "",
        "transcription": "",
        "duree": 30,
        "images": [],
        "fichier_audio": None,
        "fichier_video": fichier_video,
        "fichier_audio_path": fichier_audio,
    }

    # --- Téléchargement vidéo + métadonnées ---
    # On prend la qualité la plus basse pour la vitesse
    cmd_dl = (
        f"yt-dlp -o {fichier_video} "
        f"-f 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst' "
        f"--download-sections \"*0-30\" --force-keyframes-at-cuts --write-info-json --no-playlist --user-agent 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' --quiet {url}"
    )
    proc = await asyncio.create_subprocess_shell(cmd_dl)
    await asyncio.wait_for(proc.communicate(), timeout=90)

    if not os.path.exists(fichier_video):
        return contexte  # Téléchargement échoué

    # --- Métadonnées du post ---
    if os.path.exists(fichier_info):
        with open(fichier_info, "r", encoding="utf-8") as f:
            info = json.load(f)
        os.remove(fichier_info)

        titre_post = info.get("title", "")
        desc = info.get("description", "")
        tags = " ".join(info.get("tags", []))
        duree = int(info.get("duration", 30))
        contexte["duree"] = duree
        contexte["texte_publication"] = (
            f"TITRE DU POST: {titre_post}\n"
            f"DESCRIPTION: {desc}\n"
            f"HASHTAGS: {tags}"
        ).strip()

    # --- Captures d'écran réparties sur toute la durée ---
    duree = contexte["duree"]
    # On prend 8 captures réparties uniformément
    timestamps = [max(1, int(duree * i / 9)) for i in range(1, 9)]
    fichiers_images = [f"cap_{id_unique}_{i}.jpg" for i in range(len(timestamps))]

    args_ffmpeg_img = " ".join(
        f"-ss {t} -vframes 1 {p}"
        for t, p in zip(timestamps, fichiers_images)
    )

    # Audio complet (max 60s pour ne pas exploser la mémoire Gemini)
    cmd_ffmpeg = (
        f"ffmpeg -y -i {fichier_video} "
        f"{args_ffmpeg_img} "
        f"-t 30 -q:a 5 -map a? {fichier_audio} "
        f"-loglevel error"
    )
    proc2 = await asyncio.create_subprocess_shell(cmd_ffmpeg)
    await proc2.communicate()

    os.remove(fichier_video)

    contexte["images"] = [p for p in fichiers_images if os.path.exists(p)]

    # --- Transcription Whisper (local, rapide) ---
    if os.path.exists(fichier_audio):
        contexte["transcription"] = await extraire_sous_titres_whisper(fichier_audio)
        contexte["fichier_audio_path"] = fichier_audio
    
    return contexte


# ==========================================
# 5. PROMPT ANTI-HALLUCINATION (le cœur)
# ==========================================
PROMPT_TEMPLATE = """Tu es un détective spécialisé dans l'identification de films, séries et animes.

━━━ INDICES DISPONIBLES ━━━

{texte_publication}

TRANSCRIPTION AUDIO (voix IA ou dialogues) :
{transcription}

Les images et l'audio ci-dessous complètent ces indices.

━━━ RÈGLES STRICTES ━━━

RÈGLE 1 — PRIORITÉ DES INDICES (dans cet ordre) :
  1. Les HASHTAGS et la DESCRIPTION du post contiennent souvent le titre exact → cherche "#NomDuFilm"
  2. La TRANSCRIPTION contient le résumé de l'intrigue → déduis le film à partir de l'histoire racontée
  3. Les DIALOGUES visibles sur les images (sous-titres incrustés)
  4. Les visages d'acteurs et les décors visibles sur les images

RÈGLE 2 — ZÉRO HALLUCINATION :
  - Si tu n'es pas sûr, DIS-LE avec une confiance basse (< 50)
  - Mieux vaut confiance = 20 que d'inventer un titre
  - Ne confonds PAS un remix musical Lo-Fi avec la BO officielle du film
  - Ne te base PAS sur la musique de fond (souvent modifiée/Lo-Fi)

RÈGLE 3 — FORMAT DE RÉPONSE :
  Réponds UNIQUEMENT avec ce JSON, sans aucun texte avant ou après :
  {{"titre": "Titre exact du film/série/anime", "confiance": 85, "raison": "hashtag #TitreFilm trouvé dans la description"}}
  
  Si aucun indice ne permet d'identifier l'œuvre :
  {{"titre": "inconnu", "confiance": 0, "raison": "Aucun indice suffisant"}}
"""


# ==========================================
# 6. ANALYSE PRINCIPALE
# ==========================================
@app.post("/analyser")
async def analyser_video(lien: LienVideo):
    url = lien.url.strip()

    # Cache des succès
    if url in CACHE_RECHERCHES:
        return CACHE_RECHERCHES[url]

    # Cache des échecs (évite de re-traiter une vidéo inconnue)
    if url in CACHE_ECHECS:
        return {"erreur": "Film non reconnu (résultat en cache)"}

    id_unique = str(uuid.uuid4())[:8]
    fichier_gemini_audio = None
    contexte = {"images": [], "fichier_audio_path": ""}  # sécurité si erreur avant extraction

    try:
        # --- Extraction maximale du contexte ---
        contexte = await asyncio.wait_for(
            extraire_contexte_complet(url, id_unique),
            timeout=180,  # 3 min max sur Render gratuit (CPU lent)
        )

        if not contexte["images"]:
            return {"erreur": "Impossible de capturer des images de la vidéo."}

        # --- Construction du prompt enrichi ---
        prompt = PROMPT_TEMPLATE.format(
            texte_publication=contexte["texte_publication"] or "Non disponible",
            transcription=contexte["transcription"] or "Non disponible (audio sans paroles ou muet)",
        )

        # --- Assemblage du contenu pour Gemini ---
        contenu_requete = [prompt]

        for img_path in contexte["images"]:
            try:
                contenu_requete.append(PIL.Image.open(img_path))
            except Exception:
                pass

        audio_path = contexte.get("fichier_audio_path")
        if audio_path and os.path.exists(audio_path):
            fichier_gemini_audio = client.files.upload(file=audio_path)
            contenu_requete.append(fichier_gemini_audio)

        # --- Appel Gemini avec température 0 (déterministe) ---
        config = types.GenerateContentConfig(temperature=0.0)
        reponse_ia = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contenu_requete,
            config=config,
        )

    except asyncio.TimeoutError:
        return {"erreur": "Délai dépassé (vidéo trop longue ou connexion lente)."}
    except Exception as e:
        return {"erreur": f"Erreur d'analyse : {str(e)}"}
    finally:
        # Nettoyage systématique des fichiers temporaires
        for img_path in contexte.get("images", []):
            if os.path.exists(img_path):
                os.remove(img_path)
        audio_path = contexte.get("fichier_audio_path", "")
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if fichier_gemini_audio:
            try:
                client.files.delete(name=fichier_gemini_audio.name)
            except Exception:
                pass

    # --- Parsing de la réponse JSON ---
    trois_accents = chr(96) * 3
    texte_ia = (
        reponse_ia.text.strip()
        .replace(f"{trois_accents}json", "")
        .replace(trois_accents, "")
        .strip()
    )

    try:
        data_ia = json.loads(texte_ia)
    except json.JSONDecodeError:
        # Tentative de récupération si l'IA a quand même mis du texte autour
        import re
        match = re.search(r"\{.*\}", texte_ia, re.DOTALL)
        if match:
            try:
                data_ia = json.loads(match.group())
            except Exception:
                return {"erreur": "Réponse IA mal formatée."}
        else:
            return {"erreur": "Réponse IA mal formatée."}

    titre_trouve = data_ia.get("titre", "").strip()
    confiance_ia = int(data_ia.get("confiance", 0))
    raison = data_ia.get("raison", "")

    # Titre inconnu ou confiance trop basse → on ne cherche pas sur TMDB
    if not titre_trouve or titre_trouve.lower() in ["inconnu", "unknown", "non identifié"]:
        CACHE_ECHECS[url] = True
        return {
            "erreur": f"Film non reconnu. Raison IA : {raison}",
        }

    if confiance_ia < 40:
        # On retourne quand même le résultat mais avec un avertissement
        infos_film = await chercher_sur_tmdb(titre_trouve)
        infos_film["confiance"] = confiance_ia
        infos_film["avertissement"] = f"Confiance faible ({confiance_ia}%) — {raison}"
        return infos_film

    # --- Résultat fiable → TMDB + mise en cache ---
    infos_film = await chercher_sur_tmdb(titre_trouve)
    infos_film["confiance"] = confiance_ia
    infos_film["raison"] = raison

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