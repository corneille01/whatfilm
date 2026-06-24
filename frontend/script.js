// ════ CACHE ════
const apiCache = {};
const CACHE_TTL = 300000;
function getCached(key) { const e = apiCache[key]; if (e && (Date.now() - e.time) < CACHE_TTL) return e.data; return null; }
function setCache(key, data) { apiCache[key] = { data, time: Date.now() }; }

// ════ LAZY LOAD SCRIPT ════
function loadScriptOnce(src, id) {
  return new Promise((resolve, reject) => {
    if (id && document.getElementById(id)) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    if (id) script.id = id;

    script.onload = resolve;
    script.onerror = () => reject(new Error("Impossible de charger : " + src));

    document.head.appendChild(script);
  });
}

async function ensureTesseractReady() {
  if (window.Tesseract) return;

  await loadScriptOnce(
    "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js",
    "tesseract-js"
  );
}

let _whisperPromise = null;

window.getWhisperPipeline = async function () {
  if (_whisperPromise) return _whisperPromise;

  _whisperPromise = import("https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.1")
    .then(async ({ pipeline, env }) => {
      env.useBrowserCache = true;
      env.allowLocalModels = false;

      return pipeline(
        "automatic-speech-recognition",
        "Xenova/whisper-tiny"
      );
    });

  return _whisperPromise;
};

async function ensureTurfReady() {
  if (window.turf) return;

  await loadScriptOnce(
    "https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js",
    "turf-js"
  );
}







// ════ SAFE FETCH ════
async function safeFetch(url, options = {}) {
    const res = await fetch(url, options);
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) throw new Error(`Réponse inattendue du serveur (${res.status}).`);
    return res.json();
}




function getRegionCode() {
  const navLang = navigator.language || navigator.userLanguage || 'fr';
  const lang = navLang.toLowerCase();

  const map = {
    'fr': 'FR', 'fr-fr': 'FR', 'fr-be': 'BE', 'fr-ca': 'CA', 'fr-ch': 'CH',
    'en': 'US', 'en-us': 'US', 'en-gb': 'GB', 'en-ca': 'CA', 'en-au': 'AU',
    'es': 'ES', 'es-es': 'ES', 'es-mx': 'MX', 'es-ar': 'AR',
    'de': 'DE', 'de-de': 'DE', 'de-at': 'AT', 'de-ch': 'CH',
    'it': 'IT', 'it-it': 'IT',
    'pt': 'BR', 'pt-br': 'BR', 'pt-pt': 'PT',
    'nl': 'NL', 'nl-nl': 'NL', 'nl-be': 'BE',
    'pl': 'PL', 'ru': 'RU', 'ja': 'JP', 'ko': 'KR',
    'zh': 'CN', 'zh-cn': 'CN', 'zh-tw': 'TW',
    'ar': 'AE', 'he': 'IL', 'tr': 'TR',
    'sv': 'SE', 'da': 'DK', 'no': 'NO', 'fi': 'FI'
  };

  return map[lang] || map[lang.split('-')[0]] || 'US';
}
// ════ ÉTAT GLOBAL ════
let currentLang = "fr";
// Détection langue navigateur (ex: "fr-FR" → "fr", "en-US" → "en-US")
function detectBrowserLang() {
  const nav = navigator.language || navigator.userLanguage || "fr";
  const code = nav.toLowerCase();
  if (code.startsWith("en-gb")) return "en-GB";
  if (code.startsWith("en"))    return "en-US";
  if (code.startsWith("fr"))    return "fr";
  if (code.startsWith("es"))    return "es";
  if (code.startsWith("de"))    return "de";
  if (code.startsWith("zh"))    return "zh";
  return "fr"; // fallback
}

// Code court pour le backend (fr, en, es, de, zh)
function getBrowserLangShort() {
  const m = {
    "en-US": "en", "en-GB": "en",
    "fr": "fr", "es": "es", "de": "de", "zh": "zh"
  };
  return m[detectBrowserLang()] || "fr";
}
let lastGrid = null;
let currentPage = 1;
let currentGenreName = "";
let _allResults = [];
let _currentTotalPages = 1;
let currentMovieId = null;
let currentMediaType = "movie";
let analysisAbortController = null;
let navStack = [];


// ════ ÉTAT GLOBAL FILMING ════
let _filmingMap = null;
let _filmingMarkerClusterGroup = null;
let _filmingHotelLayer = null;
let _filmingTourismLayer = null;
let _filmingFilmLayer = null;
let _filmingHeatmapLayer = null;
let _filmingRestaurantLayer = null;
let _filmingTransportLayer = null;
let _filmingCurrentPage = 1;
let _filmingCurrentCountry = "";
let _filmingCurrentYear = "";
let _filmingCurrentType = "";
let _filmingCurrentQ = "";
let _filmingStats = null;
let _filmingCountries = [];
let _filmingAllMarkers = [];
let _filmingLeafletReady = false;
let _activeFilmMarkers = [];
let _bounceInterval = null;
let _isochroneLayer = null;
let _routeLayer = null;
let _filmingMoveTimeout = null;


// ─── SON IMMERSIF (fond spatial) ──────────────────────────
let _immersiveAudioCtx = null;
let _immersiveGain = null;
let _immersiveOsc = null;
let _immersiveInterval = null;

function playImmersiveSound() {
  try {
    if (_immersiveAudioCtx) return; // déjà joué

    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    _immersiveAudioCtx = ctx;

    // Créer un gain pour contrôler le volume
    const gain = ctx.createGain();
    gain.gain.value = 0.04; // très bas, ambiance
    gain.connect(ctx.destination);

    // Oscillateur principal (basse fréquence, type sine)
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = 80; // grave
    osc.connect(gain);
    osc.start();

    // Un second oscillateur pour créer un effet de battement spatial (désaccord léger)
    const osc2 = ctx.createOscillator();
    osc2.type = 'sine';
    osc2.frequency.value = 82; // légèrement désaccordé
    const gain2 = ctx.createGain();
    gain2.gain.value = 0.03;
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start();

    // Ajouter un peu de bruit blanc en fond (faible)
    const bufferSize = 2 * ctx.sampleRate;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * 0.01; // très faible
    }
    const noise = ctx.createBufferSource();
    noise.buffer = buffer;
    noise.loop = true;
    const gainNoise = ctx.createGain();
    gainNoise.gain.value = 0.02;
    noise.connect(gainNoise);
    gainNoise.connect(ctx.destination);
    noise.start();

    // Variation lente de la fréquence pour un effet spatial (modulation)
    let freq = 80;
    _immersiveInterval = setInterval(() => {
      freq += (Math.random() - 0.5) * 0.3;
      freq = Math.max(78, Math.min(84, freq));
      osc.frequency.setTargetAtTime(freq, ctx.currentTime, 0.1);
      osc2.frequency.setTargetAtTime(freq + 2, ctx.currentTime, 0.1);
    }, 500);

    // Garder une référence pour nettoyer
    _immersiveOsc = osc;
    _immersiveGain = gain;

    // Augmenter progressivement le volume (effet fade-in)
    gain.gain.setTargetAtTime(0.04, ctx.currentTime, 2);
    gain2.gain.setTargetAtTime(0.03, ctx.currentTime, 2);
    gainNoise.gain.setTargetAtTime(0.02, ctx.currentTime, 2);

    // Arrêter automatiquement après 8 secondes (pour ne pas gêner)
    setTimeout(() => {
      if (_immersiveAudioCtx) {
        _immersiveAudioCtx.close();
        _immersiveAudioCtx = null;
        clearInterval(_immersiveInterval);
        _immersiveInterval = null;
      }
    }, 8000);
  } catch (e) {
    // Silencieux (API Audio non supportée)
  }
}
// ════ DICTIONNAIRE INTERNATIONAL ════
const dict = {
  "en-US": {
    filming_no_result: "No result.",
filming_load_error: "Loading error.",
filming_no_movie: "No movie found.",
filming_see_one: "View filming location",
filming_see_many: "View locations",
filming_you_are_here: "You are here",
filming_geo_denied: "Geolocation denied",
    title:"WHICH MOVIE?",tagline:"Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder:"Paste TikTok/Insta link or type a movie name...",badge:"Shazam for movies",
    back_home:"Home",back_list:"Back to list",ai_conf:"Confidence",reset:"Reset",
    year:"Year",min_score:"Min score",sort_pop:"🔥 Popularity",sort_top:"⭐ Top rated",
    sort_asc:"Score ascending",sort_new:"🆕 Newest",sort_old:"📼 Oldest",
    no_streaming_country:"No streaming available in the US currently.",cancel:"Cancel",
    game_hint:"TAP / SPACE to jump",
    game_playing_msg:"<i class=\"fas fa-film\"></i> We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",
    food_title:"Ready to watch?",food_desc:"Order popcorn & snacks via DoorDash!",food_btn:"Order",
    streaming_title:"Available on",searching:"Manual search",loading_home:"Loading trending...",
    not_found_title:"Movie not found",similar_title:"<i class=\"fas fa-film\"></i> Similar movies",cast_title:"Cast",series_tag:"TV Series",
    trailer_title:"Trailer",scene_identified:"Scene identified",no_synopsis:"No synopsis available.",
    see_trailer:"Watch trailer",search_trailer:"Find trailer on YouTube",
    seasons_title:"Seasons",episodes_title:"Episodes",loading_episodes:"Loading episodes...",
    providers_country:"US",game_over:"GAME OVER — Score: ",
    filming_btn:"Filmed Here",filming_title:"FILMING LOCATIONS",
    filming_subtitle:"Explore real-world locations from cinema & TV worldwide",
    filming_search:"Search a film…",filming_movies_only:"Movies",filming_all_media:"All",
    err_server_busy:"The server is busy. Please retry in 30 seconds.",
    err_private:"This video is private or requires a login.",
    err_geo:"This video is not available in your region.",
    err_deleted:"This video has been deleted or no longer exists.",
    err_download:"Unable to download this video. Make sure it's public.",
    err_no_frames:"Could not extract images from this video.",
    err_timeout:"Analysis timed out. Try a shorter video.",
    err_session:"Session expired. Please retry.",
    err_generic:"An error occurred. Please try again.",
    err_low_confidence:"Movie not identified with enough confidence. Try searching manually.",
    search_manually:"Search manually",
    err_rate_limited:"Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily:"Daily limit reached. Come back tomorrow.",
    err_video_too_short:"Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large:"File too large. Try a shorter video.",
    err_video_blocked:"Video blocked for copyright reasons.",
    err_unsupported:"Unsupported platform or format.",
    step1:"Paste a film or anime clip link (TikTok, Reel, Short) or upload a video",
    step2:"We analyze the video",step3:"Get the movie in seconds",
    step4:"Discover the filming locations of movies & series",
    cta:"Identify",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> Tap a card for details, streaming and similar movies.",
    results:"results",
    seo_summary:"How to find a movie from TikTok?",
    seo_h2:"How to find a movie from a TikTok, Instagram, YouTube or any other social media video?",
    seo_intro:"Many viral scenes on TikTok, Instagram or YouTube Shorts come from unknown movies, series or anime. With Pelify, just paste the link to identify the film in seconds.",
    seo_li1:"Identify a movie from TikTok",seo_li2:"Find a movie from a video",
    seo_li3:"Recognize a movie scene",seo_li4:"What movie is in this video?",
    genres:{horror:"Horror",action:"Action",comedy:"Comedy",scifi:"Sci-Fi",trending:"Trending",romance:"Romance",animation:"Animation",thriller:"Thriller",drama:"Drama",crime:"Crime",documentary:"Documentary",fantasy:"Fantasy",series:"TV Series",family:"Family"}
    
  },
  "en-GB": {
    filming_no_result: "No result.",
filming_load_error: "Loading error.",
filming_no_movie: "No movie found.",
filming_see_one: "View filming location",
filming_see_many: "View locations",
filming_you_are_here: "You are here",
filming_geo_denied: "Geolocation denied",
    title:"WHICH MOVIE?",tagline:"Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder:"Paste TikTok/Insta link or type a movie name...",badge:"Shazam for movies",
    back_home:"Home",back_list:"Back to list",ai_conf:"AI Confidence",reset:"Reset",
    year:"Year",min_score:"Min score",sort_pop:"🔥 Popularity",sort_top:"⭐ Top rated",
    sort_asc:"Score ascending",sort_new:"🆕 Newest",sort_old:"📼 Oldest",
    no_streaming_country:"No streaming available in the UK currently.",cancel:"Cancel",
    game_hint:"TAP / SPACE to jump",
    game_playing_msg:"<i class=\"fas fa-film\"></i> We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",
    food_title:"Ready to watch?",food_desc:"Order popcorn & snacks via Deliveroo!",food_btn:"Order",
    streaming_title:"Available on",searching:"Manual search",loading_home:"Loading trending...",
    not_found_title:"Movie not found",similar_title:"<i class=\"fas fa-film\"></i> Similar movies",cast_title:"Cast",series_tag:"TV Series",
    trailer_title:"Trailer",scene_identified:"Scene identified",no_synopsis:"No synopsis available.",
    see_trailer:"Watch trailer",search_trailer:"Find trailer on YouTube",
    seasons_title:"Seasons",episodes_title:"Episodes",loading_episodes:"Loading episodes...",
    providers_country:"GB",game_over:"GAME OVER — Score: ",
    filming_btn:"Filmed Here",filming_title:"FILMING LOCATIONS",
    filming_subtitle:"Explore real-world locations from cinema & TV worldwide",
    filming_search:"Search a film…",filming_movies_only:"Movies",filming_all_media:"All",
    err_server_busy:"The server is busy. Please retry in 30 seconds.",
    err_private:"This video is private or requires a login.",
    err_geo:"This video is not available in your region.",
    err_deleted:"This video has been deleted or no longer exists.",
    err_download:"Unable to download this video. Make sure it's public.",
    err_no_frames:"Could not extract images from this video.",
    err_timeout:"Analysis timed out. Try a shorter video.",
    err_session:"Session expired. Please retry.",
    err_generic:"An error occurred. Please try again.",
    err_low_confidence:"Movie not identified with enough confidence. Try searching manually.",
    search_manually:"Search manually",
    err_rate_limited:"Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily:"Daily limit reached. Come back tomorrow.",
    err_video_too_short:"Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large:"File too large. Try a shorter video.",
    err_video_blocked:"Video blocked for copyright reasons.",
    err_unsupported:"Unsupported platform or format.",
    step1:"Paste a film or anime clip link (TikTok, Reel, Short) or upload a video",
    step2:"We analyse the video",step3:"Get the movie in seconds",
    step4:"Discover the filming locations of movies & series",
    cta:"Identify",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> Tap a card for details, streaming and similar movies.",
    results:"results",
    seo_summary:"How to find a movie from TikTok?",
    seo_h2:"How to find a movie from a TikTok, Instagram, YouTube or any other social media video?",
    seo_intro:"Many viral scenes on TikTok, Instagram or YouTube Shorts come from unknown movies, series or anime. With Pelify, just paste the link to identify the film in seconds.",
    seo_li1:"Identify a movie from TikTok",seo_li2:"Find a movie from a video",
    seo_li3:"Recognise a movie scene",seo_li4:"What movie is in this video?",
    genres:{horror:"Horror",action:"Action",comedy:"Comedy",scifi:"Sci-Fi",trending:"Trending",romance:"Romance",animation:"Animation",thriller:"Thriller",drama:"Drama",crime:"Crime",documentary:"Documentary",fantasy:"Fantasy",series:"TV Series",family:"Family"}
  },
  fr: {
    filming_no_result: "Aucun résultat.",
filming_load_error: "Erreur de chargement.",
filming_no_movie: "Aucun film trouvé.",
filming_see_one: "Voir le lieu de tournage",
filming_see_many: "Voir les lieux",
filming_you_are_here: "Vous êtes ici",
filming_geo_denied: "Géolocalisation refusée",
    title:"QUEL FILM ?",tagline:"Colle un lien TikTok, Reel ou YouTube — l'IA identifie le film en secondes",
    placeholder:"Coller un lien TikTok/Reel ou taper un titre de film...",badge:"Shazam pour les films",
    back_home:"Accueil",back_list:"Retour à la liste",ai_conf:"Confiance IA",reset:"Reset",
    year:"Année",min_score:"Note min",sort_pop:"🔥 Popularité",sort_top:"⭐ Mieux notés",
    sort_asc:"Note croissante",sort_new:"🆕 Plus récents",sort_old:"📼 Plus anciens",
    no_streaming_country:"Pas de streaming disponible en France actuellement.",cancel:"Annuler",
    game_hint:"TAP / ESPACE pour sauter",
    game_playing_msg:"<i class=\"fas fa-film\"></i> On cherche le film de votre lien…\nJouez pendant l'analyse — ça prend environ 30 secondes !",
    food_title:"Prêt à regarder ce film ?",food_desc:"Commandez vos snacks via UberEats !",food_btn:"Commander",
    streaming_title:"Disponible sur",searching:"Recherche manuelle",loading_home:"Chargement des tendances...",
    not_found_title:"Film non identifié",similar_title:"<i class=\"fas fa-film\"></i> Films similaires",cast_title:"Au casting",series_tag:"Série TV",
    trailer_title:"Bande-annonce",scene_identified:"Scène identifiée",no_synopsis:"Pas de synopsis disponible.",
    see_trailer:"Voir la bande-annonce",search_trailer:"Chercher la bande-annonce",
    seasons_title:"Saisons",episodes_title:"Épisodes",loading_episodes:"Chargement des épisodes...",
    providers_country:"FR",game_over:"GAME OVER — Score : ",
    filming_btn:"Lieux de tournage",filming_title:"LIEUX DE TOURNAGE",
    filming_subtitle:"Explorez les vrais décors du cinéma mondial",
    filming_search:"Rechercher un film…",filming_movies_only:"Films",filming_all_media:"Tout",
    err_server_busy:"Le serveur est actuellement surchargé. Réessayez dans 30 secondes.",
    err_private:"Cette vidéo est privée ou nécessite une connexion.",
    err_geo:"Cette vidéo n'est pas disponible dans votre région.",
    err_deleted:"Cette vidéo a été supprimée ou n'existe plus.",
    err_download:"Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique et accessible.",
    err_no_frames:"Impossible d'extraire des images de cette vidéo.",
    err_timeout:"L'analyse a pris trop de temps. Essayez avec une vidéo plus courte.",
    err_session:"Session expirée. Relancez l'analyse.",
    err_generic:"Une erreur s'est produite. Réessayez dans quelques instants.",
    err_low_confidence:"Film non identifié avec certitude. Essayez de le rechercher manuellement.",
    search_manually:"Rechercher manuellement",
    err_rate_limited:"Trop de requêtes. Attendez une minute avant de réessayer.",
    err_rate_limited_daily:"Limite journalière atteinte. Revenez demain.",
    err_video_too_short:"Vidéo trop courte. Essayez un extrait d'au moins 3 secondes.",
    err_file_too_large:"Fichier trop volumineux. Essayez une vidéo plus courte.",
    err_video_blocked:"Vidéo bloquée pour droits d'auteur.",
    err_unsupported:"Plateforme ou format non supporté.",
    step1:"Coller un lien TikTok, Reel, Short..., ou importer une vidéo",
    step2:"Nous analysons la vidéo",step3:"Découvrir le film en secondes",
    step4:"Découvrir les lieux de tournage des films et séries",
    cta:"Identifier",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> Cliquer sur une carte pour voir les détails, le streaming et les films similaires.",
    results:"résultats",
    seo_summary:"Comment trouver un film depuis un extrait TikTok, instagram, youtube... ?",
    seo_h2:"Comment trouver un film à partir d'une vidéo TikTok, Instagram, YouTube ou tout autre réseau social ?",
    seo_intro:"Beaucoup de scènes virales sur TikTok, Instagram ou YouTube Shorts proviennent de films, séries ou animes inconnus. Avec Pelify, il suffit de coller le lien pour identifier le film en quelques secondes.",
    seo_li1:"Identifier un film depuis TikTok",seo_li2:"Trouver un film à partir d'une vidéo",
    seo_li3:"Reconnaître une scène de film",seo_li4:"Quel film est dans cette vidéo ?",
    genres:{horror:"Horreur",action:"Action",comedy:"Comédie",scifi:"Sci-Fi",trending:"Tendances",romance:"Romance",animation:"Animation",thriller:"Thriller",drama:"Drame",crime:"Crime",documentary:"Documentaire",fantasy:"Fantastique",series:"Séries TV",family:"Famille"}
  },
  es: {
    filming_no_result: "Sin resultados.",
filming_load_error: "Error de carga.",
filming_no_movie: "No se encontró ninguna película.",
filming_see_one: "Ver localización de rodaje",
filming_see_many: "Ver localizaciones",
filming_you_are_here: "Estás aquí",
filming_geo_denied: "Geolocalización rechazada",
    title:"¿QUÉ PELÍCULA?",tagline:"Pega un enlace de TikTok o Reel — la IA identifica la película",
    placeholder:"Pegar enlace TikTok/Reel o escribir un título...",badge:"Shazam para películas",
    back_home:"Inicio",back_list:"Volver a la lista",ai_conf:"Confianza IA",reset:"Restablecer",
    year:"Año",min_score:"Nota mínima",sort_pop:"🔥 Popularidad",sort_top:"⭐ Mejor valoradas",
    sort_asc:"Nota ascendente",sort_new:"🆕 Más recientes",sort_old:"📼 Más antiguas",
    no_streaming_country:"Sin streaming disponible actualmente.",cancel:"Cancelar",
    game_hint:"TAP / ESPACIO para saltar",
    game_playing_msg:"<i class=\"fas fa-film\"></i> Estamos identificando la película…\n¡Juega mientras esperas, tarda unos 30 segundos!",
    food_title:"¿Listo para ver la película?",food_desc:"¡Pide snacks y palomitas!",food_btn:"Pedir",
    streaming_title:"Disponible en",searching:"Buscar manualmente",loading_home:"Cargando tendencias...",
    not_found_title:"Película no encontrada",similar_title:"<i class=\"fas fa-film\"></i> Películas similares",cast_title:"Reparto",series_tag:"Serie TV",
    trailer_title:"Tráiler",scene_identified:"Escena identificada",no_synopsis:"Sin sinopsis disponible.",
    see_trailer:"Ver tráiler",search_trailer:"Buscar tráiler en YouTube",
    seasons_title:"Temporadas",episodes_title:"Episodios",loading_episodes:"Cargando episodios...",
    providers_country:"ES",game_over:"GAME OVER — Puntuación: ",
    filming_btn:"Rodado aquí",filming_title:"LOCALIZACIONES DE RODAJE",
    filming_subtitle:"Explora los escenarios reales del cine mundial",
    filming_search:"Buscar una película…",filming_movies_only:"Películas",filming_all_media:"Todo",
    err_server_busy:"El servidor está ocupado. Reintenta en 30 segundos.",
    err_private:"Este vídeo es privado o requiere inicio de sesión.",
    err_geo:"Este vídeo no está disponible en tu región.",
    err_deleted:"Este vídeo fue eliminado o ya no existe.",
    err_download:"No se puede descargar este vídeo. Verifica que sea público.",
    err_no_frames:"No se pudieron extraer imágenes del vídeo.",
    err_timeout:"El análisis tardó demasiado. Prueba con un vídeo más corto.",
    err_session:"Sesión expirada. Reinicia el análisis.",
    err_generic:"Ocurrió un error. Inténtalo de nuevo.",
    err_low_confidence:"Película no identificada con certeza. Busca manualmente.",
    search_manually:"Buscar manualmente",
    err_rate_limited:"Demasiadas solicitudes. Espera un minuto antes de reintentar.",
    err_rate_limited_daily:"Límite diario alcanzado. Vuelve mañana.",
    err_video_too_short:"Video demasiado corto. Prueba con un clip de al menos 3 segundos.",
    err_file_too_large:"Archivo demasiado grande. Prueba con un video más corto.",
    err_video_blocked:"Video bloqueado por derechos de autor.",
    err_unsupported:"Plataforma o formato no compatible.",
    step1:"Pegar un enlace de clip de película o anime (TikTok, Reel, Short) o subir un vídeo",
    step2:"Analizamos el vídeo",step3:"Descubrir la película en segundos",
    step4:"Descubrir las localizaciones de rodaje de películas y series",
    cta:"Identificar",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> Tocar una tarjeta para ver detalles, streaming y películas similares.",
    results:"resultados",
    seo_summary:"¿Cómo encontrar una película desde TikTok?",
    seo_h2:"¿Cómo encontrar una película a partir de un vídeo de TikTok, Instagram, YouTube o cualquier otra red social?",
    seo_intro:"Muchas escenas virales en TikTok, Instagram o YouTube Shorts provienen de películas, series o animes desconocidos. Con Pelify, solo tienes que pegar el enlace para identificar la película en segundos.",
    seo_li1:"Identificar una película desde TikTok",seo_li2:"Encontrar una película a partir de un vídeo",
    seo_li3:"Reconocer una escena de película",seo_li4:"¿Qué película aparece en este vídeo?",
    genres:{horror:"Terror",action:"Acción",comedy:"Comedia",scifi:"Ciencia Ficción",trending:"Tendencias",romance:"Romance",animation:"Animación",thriller:"Thriller",drama:"Drama",crime:"Crimen",documentary:"Documental",fantasy:"Fantasía",series:"Series TV",family:"Familia"}
  },
  de: {
  filming_no_result: "Kein Ergebnis.",
filming_load_error: "Fehler beim Laden.",
filming_no_movie: "Kein Film gefunden.",
filming_see_one: "Drehort ansehen",
filming_see_many: "Drehorte ansehen",
filming_you_are_here: "Sie sind hier",
filming_geo_denied: "Geolokalisierung abgelehnt",
    title:"WELCHER FILM?",tagline:"TikTok- oder Reel-Link einfügen — KI erkennt den Film in Sekunden",
    placeholder:"TikTok/Insta Link oder Filmtitel eingeben...",badge:"Shazam für Filme",
    back_home:"Startseite",back_list:"Zurück zur Liste",ai_conf:"KI-Konfidenz",reset:"Zurücksetzen",
    year:"Jahr",min_score:"Mindestbewertung",sort_pop:"🔥 Beliebtheit",sort_top:"⭐ Bestbewertet",
    sort_asc:"Bewertung aufsteigend",sort_new:"🆕 Neueste",sort_old:"📼 Älteste",
    no_streaming_country:"Kein Streaming in Deutschland verfügbar.",cancel:"Abbrechen",
    game_hint:"TAP / LEERTASTE zum Springen",
    game_playing_msg:"<i class=\"fas fa-film\"></i> Wir identifizieren den Film…\nSpiel während du wartest — dauert ca. 30 Sekunden!",
    food_title:"Bereit zum Anschauen?",food_desc:"Bestelle Snacks und Popcorn!",food_btn:"Bestellen",
    streaming_title:"Verfügbar auf",searching:"Manuell suchen",loading_home:"Trends werden geladen...",
    not_found_title:"Film nicht gefunden",similar_title:"<i class=\"fas fa-film\"></i> Ähnliche Filme",cast_title:"Besetzung",series_tag:"TV-Serie",
    trailer_title:"Trailer",scene_identified:"Szene identifiziert",no_synopsis:"Keine Beschreibung verfügbar.",
    see_trailer:"Trailer ansehen",search_trailer:"Trailer auf YouTube suchen",
    seasons_title:"Staffeln",episodes_title:"Folgen",loading_episodes:"Folgen werden geladen...",
    providers_country:"DE",game_over:"GAME OVER — Punkte: ",
    filming_btn:"Drehorte",filming_title:"DREHORTE",
    filming_subtitle:"Entdecke echte Filmschauplätze weltweit",
    filming_search:"Film suchen…",filming_movies_only:"Filme",filming_all_media:"Alle",
    err_server_busy:"Der Server ist ausgelastet. Versuche es in 30 Sekunden.",
    err_private:"Dieses Video ist privat oder erfordert einen Login.",
    err_geo:"Dieses Video ist in deiner Region nicht verfügbar.",
    err_deleted:"Dieses Video wurde gelöscht oder existiert nicht mehr.",
    err_download:"Video kann nicht heruntergeladen werden. Stelle sicher, dass es öffentlich ist.",
    err_no_frames:"Bilder konnten nicht aus dem Video extrahiert werden.",
    err_timeout:"Analyse hat zu lange gedauert. Versuche ein kürzeres Video.",
    err_session:"Sitzung abgelaufen. Starte die Analyse neu.",
    err_generic:"Ein Fehler ist aufgetreten. Versuche es erneut.",
    err_low_confidence:"Film nicht sicher identifiziert. Suche manuell.",
    search_manually:"Manuell suchen",
    err_rate_limited:"Zu viele Anfragen. Warte eine Minute, bevor du es erneut versuchst.",
    err_rate_limited_daily:"Tägliches Limit erreicht. Komm morgen wieder.",
    err_video_too_short:"Video zu kurz. Versuche einen Clip von mindestens 3 Sekunden.",
    err_file_too_large:"Datei zu groß. Versuche ein kürzeres Video.",
    err_video_blocked:"Video aus urheberrechtlichen Gründen gesperrt.",
    err_unsupported:"Nicht unterstützte Plattform oder Format.",
    step1:"Film- oder Anime-Clip-Link einfügen (TikTok, Reel, Short) oder ein Video hochladen",
    step2:"Wir analysieren das Video",step3:"Den Film in Sekunden entdecken",
    step4:"Die Drehorte von Filmen und Serien entdecken",
    cta:"Identifizieren",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> Auf eine Karte tippen für Details, Streaming und ähnliche Filme.",
    results:"Ergebnisse",
    seo_summary:"Wie findet man einen Film über TikTok?",
    seo_h2:"Wie findet man einen Film anhand eines TikTok-, Instagram-, YouTube- oder anderen Social-Media-Videos?",
    seo_intro:"Viele virale Szenen auf TikTok, Instagram oder YouTube Shorts stammen aus unbekannten Filmen, Serien oder Animes. Mit Pelify fügst du einfach den Link ein, um den Film in Sekunden zu erkennen.",
    seo_li1:"Einen Film über TikTok identifizieren",seo_li2:"Einen Film anhand eines Videos finden",
    seo_li3:"Eine Filmszene erkennen",seo_li4:"Welcher Film ist in diesem Video?",
    genres:{horror:"Horror",action:"Action",comedy:"Komödie",scifi:"Science-Fiction",trending:"Trends",romance:"Romantik",animation:"Animation",thriller:"Thriller",drama:"Drama",crime:"Krimi",documentary:"Dokumentarfilm",fantasy:"Fantasy",series:"TV-Serien",family:"Familie"}
  },
  zh: {
  filming_no_result: "没有结果。",
filming_load_error: "加载错误。",
filming_no_movie: "未找到电影。",
filming_see_one: "查看拍摄地点",
filming_see_many: "查看拍摄地点",
filming_you_are_here: "您在这里",
filming_geo_denied: "地理位置访问被拒绝",
    title:"什么电影？",tagline:"粘贴 TikTok 或 Reel 链接 — AI 即刻识别电影",
    placeholder:"粘贴链接或输入电影名...",badge:"电影识别神器",
    back_home:"首页",back_list:"返回列表",ai_conf:"AI 置信度",reset:"重置",
    year:"年份",min_score:"最低评分",sort_pop:"🔥 热度",sort_top:"⭐ 最高评分",
    sort_asc:"评分升序",sort_new:"🆕 最新",sort_old:"📼 最早",
    no_streaming_country:"暂无可用的流媒体。",cancel:"取消",
    game_hint:"点击 / 空格键跳跃",
    game_playing_msg:"<i class=\"fas fa-film\"></i> 正在识别您视频中的电影…\n请玩游戏等待，大约需要30秒！",
    food_title:"准备好看电影了吗？",food_desc:"立即订购爆米花和零食！",food_btn:"下单",
    streaming_title:"可在以下平台观看",searching:"手动搜索",loading_home:"加载热门中...",
    not_found_title:"未找到影片",similar_title:"<i class=\"fas fa-film\"></i> 相似影片",cast_title:"演员表",series_tag:"电视剧",
    trailer_title:"预告片",scene_identified:"识别场景",no_synopsis:"暂无简介。",
    see_trailer:"观看预告片",search_trailer:"在 YouTube 上搜索预告片",
    seasons_title:"季",episodes_title:"集",loading_episodes:"加载剧集中...",
    providers_country:"CN",game_over:"游戏结束 — 得分：",
    filming_btn:"拍摄地",filming_title:"拍摄地点",
    filming_subtitle:"探索全球电影真实拍摄地",
    filming_search:"搜索电影…",filming_movies_only:"电影",filming_all_media:"全部",
    err_server_busy:"服务器繁忙，请30秒后重试。",
    err_private:"该视频为私密视频或需要登录。",
    err_geo:"该视频在您所在地区不可用。",
    err_deleted:"该视频已被删除或不再存在。",
    err_download:"无法下载此视频，请确认视频为公开状态。",
    err_no_frames:"无法从视频中提取图像。",
    err_timeout:"分析超时，请尝试较短的视频。",
    err_session:"会话已过期，请重新分析。",
    err_generic:"发生错误，请重试。",
    err_low_confidence:"无法确定识别电影，请手动搜索。",
    search_manually:"手动搜索",
    err_rate_limited:"请求过多。请等待一分钟后再试。",
    err_rate_limited_daily:"已达每日限额。请明天再来。",
    err_video_too_short:"视频太短。请尝试至少3秒的片段。",
    err_file_too_large:"文件太大。请尝试较短的视频。",
    err_video_blocked:"视频因版权原因被屏蔽。",
    err_unsupported:"不支持的平台或格式。",
    step1:"粘贴电影或动漫片段链接（TikTok、Reel、Short）或上传视频",
    step2:"我们分析视频",step3:"几秒内找到电影",
    step4:"探索电影和剧集的拍摄地点",
    cta:"识别",hero_hint:"<i class=\"fas fa-hand-pointer\"></i> 点击卡片查看详情、播放平台和相似电影。",
    results:"个结果",
    seo_summary:"如何通过 TikTok 找电影？",
    seo_h2:"如何通过 TikTok、Instagram、YouTube 或其他社交媒体视频找到电影？",
    seo_intro:"TikTok、Instagram 或 YouTube Shorts 上的许多热门片段来自不知名的电影、剧集或动漫。使用 Pelify，只需粘贴链接即可在几秒内识别影片。",
    seo_li1:"通过 TikTok 识别电影",seo_li2:"通过视频找到电影",
    seo_li3:"识别电影场景",seo_li4:"这个视频里是什么电影？",
    genres:{horror:"恐怖",action:"动作",comedy:"喜剧",scifi:"科幻",trending:"热门",romance:"爱情",animation:"动画",thriller:"惊悚",drama:"剧情",crime:"犯罪",documentary:"纪录片",fantasy:"奇幻",series:"电视剧",family:"家庭"}
  }
};




// ════ CONFIG STREAMING ════
const STREAMING_META = {
  Netflix:{color:"#e50914",logo:"https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/24px-Netflix_2015_logo.svg.png"},
  "Amazon Prime Video":{color:"#00a8e0",logo:""},"Disney+":{color:"#113ccf",logo:""},
  "Apple TV+":{color:"#a2aaad",logo:""},"Paramount+":{color:"#0064ff",logo:""},
  "Canal+":{color:"#000",logo:""},OCS:{color:"#e85d04",logo:""},
  Crunchyroll:{color:"#f47521",logo:""},Mubi:{color:"#2196f3",logo:""},Hulu:{color:"#1ce783",logo:""}
};
const STREAMING_LINKS = {
  Netflix:"https://www.netflix.com/search?q=",

  "Disney+":"https://www.disneyplus.com/search/",
  "Apple TV+":"https://tv.apple.com/search?term=",
  "Canal+":"https://www.canalplus.com/recherche/",
  OCS:"https://www.ocs.fr/recherche/",
  "Paramount+":"https://www.paramountplus.com/search/",
  Crunchyroll:"https://www.crunchyroll.com/search?q=",
  Mubi:"https://mubi.com/search/",
  Hulu:"https://www.hulu.com/search?query="
};

// ════ AMAZON PAR MARCHÉ (détection navigateur) ════
const AMAZON_DOMAINS = {
  FR:"www.amazon.fr", BE:"www.amazon.com.be", ES:"www.amazon.es", DE:"www.amazon.de",
  AT:"www.amazon.de", IT:"www.amazon.it", NL:"www.amazon.nl", SE:"www.amazon.se",
  PL:"www.amazon.pl", GB:"www.amazon.co.uk", IE:"www.amazon.co.uk", US:"www.amazon.com",
  CA:"www.amazon.ca", MX:"www.amazon.com.mx", BR:"www.amazon.com.br", JP:"www.amazon.co.jp",
  IN:"www.amazon.in", AU:"www.amazon.com.au", AE:"www.amazon.ae", SA:"www.amazon.sa",
  SG:"www.amazon.sg", TR:"www.amazon.com.tr",
};
function _amazonTag(domain){
  if (domain.endsWith(".com")) return "pelify-20";
  if (domain.endsWith(".ca"))  return "pelify-20";
  return "pelify-21";
}
function _detectCountry(){
  for (const l of (navigator.languages || [navigator.language || ""])) {
    const m = l.toUpperCase().match(/-([A-Z]{2})$/);
    if (m && AMAZON_DOMAINS[m[1]]) return m[1];
  }
  const uiToCC = { fr:"FR", es:"ES", de:"DE", "en-GB":"GB", "en-US":"US", zh:"US" };
  return uiToCC[currentLang] || "US";
}
function getAmazonSearch(title){
  const domain = AMAZON_DOMAINS[_detectCountry()] || "www.amazon.com";
  return `https://${domain}/s?k=${encodeURIComponent(title||"")}&i=instant-video&tag=${_amazonTag(domain)}`;
}
// ════ CONFIG AFFILIATION ════
const AFFILIATE_CONFIG = {
  deliveroo:    { base: "https://deliveroo.fr",            aff_param: "" },
  ubereats:     { base: "https://www.ubereats.com",        aff_param: "" },
  doordash:     { base: "https://www.doordash.com",        aff_param: "" },
  lieferando:   { base: "https://www.lieferando.de",       aff_param: "" },
  glovo:        { base: "https://glovoapp.com",            aff_param: "" },
  amazon_prime: { base: "https://www.amazon.fr/amazonprime", aff_param: "?tag=pelify-21" }, // → "?tag=TON_TAG-21" quand accepté
};

function getFoodLink(lang) {
  const cfg = AFFILIATE_CONFIG;
  if (lang === "fr")    return `${cfg.ubereats.base}${cfg.ubereats.aff_param}`;
  if (lang === "en-GB") return `${cfg.deliveroo.base}${cfg.deliveroo.aff_param}`;
  if (lang === "en-US") return `${cfg.doordash.base}${cfg.doordash.aff_param}`;
  if (lang === "de")    return `${cfg.lieferando.base}${cfg.lieferando.aff_param}`;
  if (lang === "es")    return `${cfg.glovo.base}${cfg.glovo.aff_param}`;
  return `${cfg.ubereats.base}`;
}

// ════ UTILITAIRES LANGUE ════
function getLangCode(){const m={"en-US":"en-US","en-GB":"en-GB",fr:"fr-FR",es:"es-ES",de:"de-DE",zh:"zh-CN"};return m[currentLang]||"fr-FR";}
// function getRegionCode(){return(dict[currentLang]||dict.fr).providers_country||"FR";}
function getTMDBLang(){const m={"en-US":"en","en-GB":"en",fr:"fr",es:"es",de:"de",zh:"zh"};return m[currentLang]||"fr";}
function t(key){return(dict[currentLang]||dict.fr)[key]||key;}
function tg(key){return((dict[currentLang]||dict.fr).genres||{})[key]||key;}
function tErr(code){
  const d=dict[currentLang]||dict.fr;
  const map={server_busy:d.err_server_busy,video_private:d.err_private,video_geo:d.err_geo,video_deleted:d.err_deleted,download_failed:d.err_download,download_empty:d.err_download,no_frames:d.err_no_frames,timeout:d.err_timeout,session_expired:d.err_session,unexpected:d.err_generic,low_confidence:d.err_low_confidence,rate_limited:d.err_rate_limited||"Trop de requêtes.",rate_limited_daily:d.err_rate_limited_daily||"Limite journalière atteinte.",video_too_short:d.err_video_too_short||"Vidéo trop courte.",file_too_large:d.err_file_too_large||"Fichier trop volumineux.",download_timeout:d.err_timeout,video_blocked:d.err_video_blocked||"Vidéo bloquée.",unsupported_platform:d.err_unsupported||"Plateforme non supportée.",unsupported:d.err_unsupported||"Format non supporté."};
  return map[code]||d.err_generic;
}

// ════ INIT LANGUE ════
function initLang(){
  const pathLang=window.location.pathname.replace(/\//g,"");
  const pathMap={en:"en-US","en-US":"en-US","en-GB":"en-GB",fr:"fr",es:"es",de:"de",zh:"zh"};
  if(pathMap[pathLang])currentLang=pathMap[pathLang];
  document.getElementById("lang-selector").value=currentLang;
  applyLang();genererNav();
}
function applyLang(){
   const ld=dict[currentLang]||dict.fr;
  document.querySelectorAll("[data-i18n]").forEach(el=>{
    const k=el.getAttribute("data-i18n");
    if(ld[k]==null) return;
    if(el.tagName==="OPTION") el.textContent=ld[k];   // les <option> ne rendent que du texte
    else el.innerHTML=ld[k];                           // le reste rend les <i>
  });
  const inp=document.getElementById("input_global");if(inp)inp.placeholder=ld.placeholder||"";
  const heroInp=document.getElementById("hero-search-input");
  if(heroInp)heroInp.placeholder=ld.placeholder||"";
  const optMap={pop:"sort_pop",note_desc:"sort_top",note_asc:"sort_asc",recent:"sort_new",ancien:"sort_old"};
  document.querySelectorAll("#filtre-tri option").forEach(opt=>{const k=optMap[opt.value];if(k&&ld[k])opt.textContent=ld[k];});
  const selNote=document.querySelector("#filtre-note option");if(selNote)selNote.textContent="⭐ "+(ld.min_score||"Note min");
  const selAnnee=document.querySelector("#filtre-annee option");if(selAnnee)selAnnee.textContent="📅 "+(ld.year||"Année");
  const btr=document.getElementById("btn-reset");if(btr)btr.innerHTML=`<i class="fas fa-times"></i> ${ld.reset||"Reset"}`;
  const btnFilming=document.getElementById("btn-genre-filming");
  if(btnFilming)btnFilming.innerHTML=`<i class="fas fa-map-marker-alt"></i> ${ld.filming_btn||"📍 Lieux de tournage"}`;
}

function genererNav() {
  const g = dict[currentLang]?.genres || dict.fr.genres;
  const ld = dict[currentLang] || dict.fr;

  const genreNav = document.getElementById("genre-nav");
  const secondNav = document.getElementById("platform-nav");

  if (!genreNav || !secondNav) return;

  genreNav.innerHTML = `
    <a class="btn-genre home-action prime" href="/plateforme/amazon"
       onclick="chargerParPlateformeAsync('amazon'); return false;">
      <i class="fas fa-play"></i>
      <span>Prime Video</span>
    </a>

    <a class="btn-genre home-action animation" href="/genre/animation"
       onclick="ouvrirCategorieAccueil('animation'); return false;">
      <i class="fas fa-dragon"></i>
      <span>${g.animation || "Animation"}</span>
    </a>

    <a class="btn-genre home-action films" href="/genre/films"
       onclick="ouvrirFilmsAccueil(); return false;">
      <i class="fas fa-film"></i>
      <span>Films</span>
    </a>

    <a class="btn-genre home-action series" href="/series"
       onclick="ouvrirCategorieAccueil('series'); return false;">
      <i class="fas fa-tv"></i>
      <span>${g.series || "Séries"}</span>
    </a>

    <a class="btn-genre home-action filming" href="/lieux-de-tournage"
       onclick="chargerLieuxDeTournage(); return false;">
      <i class="fas fa-map-marker-alt"></i>
      <span>${ld.filming_btn || "Lieux de tournage"}</span>
    </a>
  `;

  secondNav.innerHTML = "";
  secondNav.classList.remove("visible");
}

function afficherNavCategoriesFilms(active = "trending") {
  const g = dict[currentLang]?.genres || dict.fr.genres;
  const nav = document.getElementById("platform-nav");
  if (!nav) return;

  const items = [
    ["trending", "fas fa-bolt", g.trending || "Tendances"],
    ["action", "fas fa-fire", g.action || "Action"],
    ["horror", "fas fa-ghost", g.horror || "Horreur"],
    ["scifi", "fas fa-rocket", g.scifi || "Sci-Fi"],
    ["thriller", "fas fa-eye", g.thriller || "Thriller"],
    ["drama", "fas fa-theater-masks", g.drama || "Drame"],
    ["comedy", "fas fa-laugh", g.comedy || "Comédie"],
    ["romance", "fas fa-heart", g.romance || "Romance"],
    ["crime", "fas fa-user-secret", g.crime || "Crime"],
    ["documentary", "fas fa-video", g.documentary || "Documentaire"],
    ["fantasy", "fas fa-hat-wizard", g.fantasy || "Fantastique"],
    ["family", "fas fa-users", g.family || "Famille"],
    
    
  ];

  nav.innerHTML = items.map(([key, icon, label]) => `
    <a class="btn-platform ${active === key ? "active" : ""}"
       href="${key === "trending" ? "/" : `/genre/${key}`}"
       onclick="${key === "trending"
          ? "chargerTrending();"
          : `chargerGenre('${key}');`} return false;">
      <i class="${icon}"></i>
      <span>${label}</span>
    </a>
  `).join("");

  nav.classList.add("visible");
}

function afficherNavPlateformes(active = "amazon") {
  const nav = document.getElementById("platform-nav");
  if (!nav) return;

  const items = [
    ["netflix", "#e50914", "Netflix"],
    ["amazon", "#00a8e0", "Prime Video"],
    ["disney", "#113ccf", "Disney+"],
    ["apple", "#a2aaad", "Apple TV+"],
    ["paramount", "#0064ff", "Paramount+"],
    ["hulu", "#1ce783", "Hulu"],
  ];

  nav.innerHTML = items.map(([key, color, label]) => `
    <a class="btn-platform ${active === key ? "active" : ""}"
       href="/plateforme/${key}"
       onclick="chargerParPlateforme('${key}'); return false;"
       style="border-color:${color}">
      <span class="plat-dot" style="background:${color}"></span>
      <span>${label}</span>
    </a>
  `).join("");

  nav.classList.add("visible");
}
function ouvrirFilmsAccueil() {
 
  chargerFilms();
}
function ouvrirCategorieAccueil(type) {
  if (type === "animation") {
    afficherNavCategoriesFilms("animation");
    chargerGenre("animation");
    return;
  }

 if (type === "series") {
  document.getElementById("platform-nav").classList.remove("visible");
  chargerSeries();
  return;
}
}
function changerLangueManuellement(){
  const newLang=document.getElementById("lang-selector").value;
  currentLang=newLang;applyLang();genererNav();
  const langPath={"en-US":"en","en-GB":"en-GB",fr:"fr",es:"es",de:"de",zh:"zh"}[currentLang]||"fr";
  history.replaceState(null,"","/"+langPath);
  const detailPage=document.getElementById("page-film-detail"),gridPage=document.getElementById("genre-grid");
  if(currentMovieId&&detailPage.style.display!=="none"){afficherDetails(currentMovieId,currentMediaType);return;}
  if (gridPage.style.display !== "none") {
  if (currentGenreName === "trending") chargerTrending();
  else if (currentGenreName === "films") chargerFilms(currentPage);
  else if (currentGenreName === "series") chargerSeries();
  else if (currentGenreName === "filming") chargerLieuxDeTournage();
  else if (currentGenreName) chargerGenre(currentGenreName, currentPage);
  return;
}
  setHomeMode();
document.getElementById("hero").style.display = "block";
document.getElementById("genre-nav").style.display = "flex";
document.getElementById("platform-nav").classList.remove("visible");
document.getElementById("genre-grid").style.display = "none";
document.getElementById("filming-page").style.display = "none";
document.getElementById("page-film-detail").style.display = "none";
}

// ════ ERREURS & TOAST ════
function afficherErreur(msg){const el=document.getElementById("error-message");document.getElementById("error-text").textContent=msg;el.classList.add("visible");el.style.display="flex";setTimeout(cacherErreur,10000);}
function cacherErreur(){const el=document.getElementById("error-message");el.classList.remove("visible");el.style.display="none";}
function toast(msg,dur=3000){const t=document.getElementById("toast");if(!t)return;t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),dur);}

function afficherErreurRiche(data){
  // ── Contenu généré par IA ────────────────────────────────────
  if (data.code === "ai_generated" || data.is_ai_generated) {
    document.getElementById("loading-overlay").classList.remove("active");
    stopGame();
    document.getElementById("genre-grid").style.display = "block";
    document.getElementById("page-film-detail").style.display = "none";
    document.getElementById("hero").style.display = "none";
    document.getElementById("filtres-bar").style.display = "none";
    document.getElementById("genre-title").innerText = "";
    document.getElementById("movie-cards").innerHTML = `
      <div style="grid-column:1/-1;display:flex;flex-direction:column;
                  align-items:center;justify-content:center;text-align:center;
                  padding:48px 24px;max-width:520px;margin:0 auto;gap:16px;">
        <div style="font-size:4rem;line-height:1">🤖</div>
        <h3 style="color:var(--text);font-size:1.3rem;margin:0">
          Contenu généré par IA
        </h3>
        <p style="color:var(--muted);font-size:.9rem;margin:0;line-height:1.7">
          Cette vidéo semble avoir été créée par une intelligence artificielle
          <br><span style="color:var(--primary);font-size:.8rem">
            Sora · Runway · Midjourney · Pika · Kling · Gen-2
          </span>
        </p>
        <p style="color:var(--muted);font-size:.82rem;margin:0">
          Aucun film réel ne correspond à ce clip.
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:8px">
          <button class="btn-stream" onclick="retourAccueil()">
            <i class="fas fa-home"></i> Accueil
          </button>
          <button class="btn-stream" onclick="document.getElementById('input_global').value='';document.getElementById('input_global').focus();">
            <i class="fas fa-search"></i> Nouvelle recherche
          </button>
        </div>
      </div>`;
    window.scrollTo({ top: 0, behavior: "smooth" });
    return; // ← sortir avant le reste de la fonction
  }

  // ── Suite du code existant inchangé ─────────────────────────
  const d = dict[currentLang] || dict.fr;
  const code = data.code || "unexpected";
  const msg=data.message||tErr(code);
  const searchQ=encodeURIComponent(document.getElementById("input_global").value.trim()||"");
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("hero").style.display="none";
  document.getElementById("filtres-bar").style.display="none";
  document.getElementById("genre-title").innerText="";
  const icon={video_private:"🔒",video_geo:"🌍",video_deleted:"🗑️",download_failed:"📵",server_busy:"⏳",no_frames:"🖼️",timeout:"⏱️",session_expired:"🔄",low_confidence:"🔍"}[code]||"⚠️";
  const retryBtn=(code==="server_busy"||code==="timeout"||code==="unexpected")?`<button class="btn-stream" style="margin-top:8px" onclick="retourAccueil()"><i class="fas fa-redo"></i> Réessayer</button>`:"";
  document.getElementById("movie-cards").innerHTML = `
<div style="grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 24px;max-width:520px;margin:0 auto;gap:16px;">
    <div style="font-size:3.5rem;line-height:1;">${icon}</div>
    <h3 style="color:var(--text);font-size:1.2rem;margin:0;">${msg}</h3>
    <p style="color:var(--muted);font-size:0.85rem;margin:0;line-height:1.6;">
        ${d.search_manually || "Recherchez le film manuellement :"}
    </p>

    <div class="streaming-buttons" style="gap:10px;flex-wrap:wrap;justify-content:center;">
        <button class="btn-stream"
            onclick="document.getElementById('input_global').value='';document.getElementById('input_global').focus();">
            <i class="fas fa-search"></i>
            ${d.search_manually || "Rechercher"}
        </button>

        ${searchQ ? `
        <a href="https://www.youtube.com/results?search_query=${encodeURIComponent(searchQ + ' film trailer')}"
           target="_blank"
           rel="noopener"
           class="btn-stream"
           style="border-color:#ff0000">
            <i class="fab fa-youtube"></i> YouTube
        </a>
        ` : ""}

        ${retryBtn}
    </div>
</div>`;
}

// ════ BARRE RECHERCHE ════
function majBtnClear(){document.getElementById("btn-clear").classList.toggle("visible",document.getElementById("input_global").value.length>0);}
function effacerRecherche(){document.getElementById("input_global").value="";document.getElementById("btn-clear").classList.remove("visible");document.getElementById("input_global").focus();}

// ════ NAVIGATION ════
function _hideAllPages(){
  ["page-film-detail","genre-grid","privacy-page","filming-page","hero","genre-nav"].forEach(id=>{
    const el=document.getElementById(id);if(el)el.style.display="none";
  });
}
function retourAccueil(pushHistory = true){
  setHomeMode();
  if (pushHistory) _pushNav("/", { type: "home" });
  cacherErreur();_hideAllPages();
  document.getElementById("hero").style.display="block";
  document.getElementById("genre-nav").style.display="flex";
  document.getElementById("platform-nav").classList.remove("visible");
  lastGrid=null;currentMovieId=null;navStack=[];
  
}
function retourArriere(){
  if(navStack.length>0){const prev=navStack.pop();afficherDetails(prev.id,prev.type);}
  else{document.getElementById("page-film-detail").style.display="none";if(lastGrid)document.getElementById("genre-grid").style.display="block";else retourAccueil();}
}
function hideHero(){document.getElementById("hero").style.display="none";document.getElementById("genre-nav").style.display="flex";}
function chargerParPlateformeAsync(platform) {
  deferInteraction(() => {
    chargerParPlateforme(platform);
  });
}

function retourAccueilAsync() {
  deferInteraction(() => {
    retourAccueil();
  });
}
// ════ RECHERCHE GLOBALE ════
async function gererRechercheGlobal(){
 
  const input=document.getElementById("input_global").value.trim();
  if(!input)return;
  await new Promise(requestAnimationFrame);
  cacherErreur();
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  const isLink=/^https?:\/\//i.test(input)&&(/tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com/.test(input)||/instagram\.com/.test(input)||/youtube\.com|youtu\.be/.test(input)||/twitter\.com|x\.com/.test(input)||/facebook\.com|fb\.watch/.test(input)||/dailymotion\.com|dai\.ly/.test(input)||/bilibili\.com/.test(input)||/snapchat\.com/.test(input)||/vimeo\.com/.test(input)||/twitch\.tv/.test(input)||/linkedin\.com/.test(input)||/reddit\.com|redd\.it/.test(input)||/pinterest\.|pin\.it/.test(input)||/bit\.ly|t\.co|tinyurl\.com|ow\.ly|buff\.ly|short\.io|lnk\.to/.test(input))||/^https?:\/\//i.test(input);
if (isLink) { demarrerPub(); analyserVideo(input); }
  else{
    hideHero();
    try{const data=await safeFetch(`/rechercher?query=${encodeURIComponent(input)}&lang=${getTMDBLang()}`);if(data.status==="error"){afficherErreur(data.message||t("err_generic"));return;}afficherResultatsRecherche(data,input);}
    catch(e){afficherErreur(t("err_generic")+" — "+e.message);}
  }
}



function deferInteraction(callback) {
  requestAnimationFrame(() => {
    setTimeout(callback, 0);
  });
}
function rechercheHero() {
  const el = document.getElementById("hero-search-input");
  if (!el) return;

  const v = el.value.trim();
  if (!v) return;

  document.getElementById("input_global").value = v;

  deferInteraction(() => {
    gererRechercheGlobal();
  });
}

// ════ ANNULER ANALYSE ════
function annulerAnalyse(){
  if(analysisAbortController)analysisAbortController.abort();
  _adFinished=true;_analysisResult=null;
  document.getElementById('ad-modal').style.display='none';
  clearInterval(_adCountdownInterval);
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();retourAccueil();
}

// ════ AUDIO ════
let audioCtx=null,bgMusicGain=null,bgMusicInterval=null;
function initAudio(){if(audioCtx)return;try{audioCtx=new(window.AudioContext||window.webkitAudioContext)();bgMusicGain=audioCtx.createGain();bgMusicGain.gain.value=0.12;bgMusicGain.connect(audioCtx.destination);}catch(e){}}
function playTone(freq,duration,type='square',volume=0.1){if(!audioCtx)return;try{const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();osc.type=type;osc.frequency.value=freq;gain.gain.setValueAtTime(volume,audioCtx.currentTime);gain.gain.exponentialRampToValueAtTime(0.001,audioCtx.currentTime+duration);osc.connect(gain);gain.connect(audioCtx.destination);osc.start();osc.stop(audioCtx.currentTime+duration);}catch(e){}}
function playCoinSound(){playTone(988,0.08);setTimeout(()=>playTone(1319,0.1),60);}
function playGameOverSound(){playTone(330,0.2,'sawtooth',0.2);setTimeout(()=>playTone(262,0.3,'sawtooth',0.2),150);setTimeout(()=>playTone(196,0.5,'sawtooth',0.15),350);}
function startBgMusic(){if(!audioCtx||bgMusicInterval)return;const notes=[523,587,659,698,784,880,988,1047];const durations=[0.15,0.15,0.15,0.15,0.15,0.15,0.2,0.4];let i=0;bgMusicInterval=setInterval(()=>{const freq=notes[i%notes.length],dur=durations[i%durations.length];try{const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();osc.type='square';osc.frequency.value=freq;gain.gain.setValueAtTime(0.08,audioCtx.currentTime);gain.gain.exponentialRampToValueAtTime(0.001,audioCtx.currentTime+dur);osc.connect(gain);gain.connect(bgMusicGain);osc.start();osc.stop(audioCtx.currentTime+dur);}catch(e){}i++;},250);}
function stopBgMusic(){clearInterval(bgMusicInterval);bgMusicInterval=null;}

// ════ MINI-JEU ════
let gameState={running:false,score:0,lives:3,level:1,heroY:0,heroVY:0,jumping:false,obstacles:[],coins:[],frame:0,speed:3,rafId:null,dead:false,started:false,lastTime:0};
function gameJump(){if(!gameState.running||gameState.dead){startGame();return;}if(!gameState.jumping){gameState.heroVY=-9;gameState.jumping=true;}}
function _hideGameMsgBanner(){const b=document.getElementById("game-msg-banner");if(b)b.style.display="none";}
function startGame(){
  stopGame();
  Object.assign(gameState,{running:true,score:0,lives:3,level:1,heroY:0,heroVY:0,jumping:false,obstacles:[],coins:[],frame:0,speed:3,dead:false,started:true,lastTime:0});
  const canvas=document.getElementById("game-canvas");if(canvas)canvas.querySelectorAll(".game-obstacle,.game-coin").forEach(el=>el.remove());
  const banner=document.getElementById("game-msg-banner");if(banner){banner.innerHTML=(t("game_playing_msg")||"🎬 On cherche votre film…").replace(/\n/g,"<br>");banner.style.display="block";}
  const hint=document.getElementById("game-hint");if(hint){hint.textContent=t("game_hint")||"TAP / ESPACE pour sauter";hint.style.display="block";}
  initAudio();startBgMusic();
  gameState.rafId=requestAnimationFrame(gameLoop);
}
function stopGame(){if(gameState.rafId){cancelAnimationFrame(gameState.rafId);gameState.rafId=null;}gameState.running=false;stopBgMusic();const canvas=document.getElementById("game-canvas");if(canvas)canvas.querySelectorAll(".game-obstacle,.game-coin").forEach(el=>el.remove());_hideGameMsgBanner();}
let _lastFrameTime=0;
const TARGET_FPS=60,FRAME_MS=1000/TARGET_FPS;
function gameLoop(timestamp){
  if(!gameState.running)return;
  const delta=timestamp-_lastFrameTime;if(delta<FRAME_MS-2){gameState.rafId=requestAnimationFrame(gameLoop);return;}
  _lastFrameTime=timestamp;gameState.frame++;
  const canvas=document.getElementById("game-canvas");if(!canvas)return;
  const W=canvas.offsetWidth||380;
  const hero=document.getElementById("game-hero");if(!hero)return;
  if(gameState.jumping){gameState.heroVY+=0.55;gameState.heroY-=gameState.heroVY;if(gameState.heroY<=0){gameState.heroY=0;gameState.heroVY=0;gameState.jumping=false;}}
  hero.style.bottom=28+gameState.heroY+"px";
  gameState.speed=3+Math.floor(gameState.score/50)*0.4;gameState.level=Math.floor(gameState.score/50)+1;
  const lvlEl=document.getElementById("game-level");if(lvlEl)lvlEl.textContent="LVL "+gameState.level;
  const obsInterval=Math.max(55,110-gameState.level*4);
  if(gameState.frame%obsInterval===0){const obs=document.createElement("div");obs.className="game-obstacle";obs.textContent=["🌵","🧱","🔮","💀","⚡"][Math.floor(Math.random()*5)];obs.style.cssText=`left:${W}px;bottom:28px;`;canvas.appendChild(obs);gameState.obstacles.push({el:obs,x:W});}
  if(gameState.frame%80===40){const coin=document.createElement("div");coin.className="game-coin";coin.textContent="🪙";const cy=50+Math.random()*60;coin.style.cssText=`left:${W}px;bottom:${28+cy}px;`;canvas.appendChild(coin);gameState.coins.push({el:coin,x:W,y:cy});}
  gameState.obstacles=gameState.obstacles.filter(ob=>{ob.x-=gameState.speed;ob.el.style.left=ob.x+"px";const hit=ob.x>40&&ob.x<90&&gameState.heroY<35;if(hit){gameState.lives--;const livesEl=document.getElementById("game-lives");if(livesEl)livesEl.textContent="❤️".repeat(Math.max(0,gameState.lives));ob.el.remove();if(gameState.lives<=0){gameOver();return false;}return false;}if(ob.x<-40){ob.el.remove();return false;}return true;});
  gameState.coins=gameState.coins.filter(c=>{c.x-=gameState.speed;c.el.style.left=c.x+"px";const hit=c.x>40&&c.x<90&&gameState.heroY>c.y-15&&gameState.heroY<c.y+35;if(hit){gameState.score+=5;c.el.remove();playCoinSound();return false;}if(c.x<-40){c.el.remove();return false;}return true;});
  if(gameState.frame%10===0)gameState.score++;
  const scoreEl=document.getElementById("game-score");if(scoreEl)scoreEl.textContent=gameState.score;
  gameState.rafId=requestAnimationFrame(gameLoop);
}
function gameOver(){
  gameState.running=false;gameState.dead=true;
  if(gameState.rafId){cancelAnimationFrame(gameState.rafId);gameState.rafId=null;}
  playGameOverSound();stopBgMusic();_hideGameMsgBanner();
  const hint=document.getElementById("game-hint");if(hint){hint.textContent=t("game_over")+gameState.score+" — TAP";hint.style.display="block";}
}

// ════ ANALYSE VIDÉO ════
async function analyserVideo(lien){
  hideHero();_adFinished=false;_analysisResult=null;
  const lastAd=parseInt(localStorage.getItem('last_ad')||'0');
  const showAd=Date.now()-lastAd>30*60*1000;
  if(showAd){localStorage.setItem('last_ad',Date.now().toString());demarrerPub();}else{_adFinished=true;}
  const overlay=document.getElementById("loading-overlay");overlay.classList.add("active");startGame();
  let progress=0;const progressBar=document.getElementById("prog-fill");const percentLabel=document.getElementById("prog-percent");
  let progInterval=setInterval(()=>{if(progress<88){progress+=Math.random()*8+3;if(progress>88)progress=88;if(progressBar)progressBar.style.width=progress+"%";if(percentLabel)percentLabel.textContent=Math.round(progress)+"%";}},900);
  analysisAbortController=new AbortController();const signal=analysisAbortController.signal;
  try{
   const res=await fetch("/analyser",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:lien,lang:getTMDBLang(),browser_lang:getBrowserLangShort()}),signal});
    if(!res.ok)throw new Error(`http_${res.status}`);
    let data;try{data=await res.json();}catch(e){throw new Error("json_parse");}
    if(data.status==="error"){clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();afficherErreurRiche(data);return;}
    if(data.status==="transcription_needed"){
      clearInterval(progInterval);
      const skipWhisper=data.skip_whisper===true;
      const[ocrText,transcript]=await Promise.allSettled([data.frames_base64?.length?runLocalOCR(data.frames_base64):Promise.resolve(""),(!skipWhisper&&data.audio_base64)?runLocalWhisper(data.audio_base64):Promise.resolve("")]);
      const continueRes=await fetch("/analyser_continue",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:data.session_id,ocr_text:ocrText.status==="fulfilled"?ocrText.value:"",transcript:transcript.status==="fulfilled"?transcript.value:"",browser_lang:getBrowserLangShort()}),signal});
      let finalData;try{finalData=await continueRes.json();}catch(e){throw new Error("json_parse");}_afficherResultatFinal(finalData);return;
    }
    if(data.status==="processing"&&data.session_id){clearInterval(progInterval);const finalResult=await pollAnalysisStatus(data.session_id,signal);await _consumeAnalysis(finalResult,signal);return;}
    clearInterval(progInterval);_afficherResultatFinal(data);
  }catch(e){
    clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
    if(e.name==="AbortError")return;
    if(e.message==="json_parse")afficherErreurRiche({code:"unexpected",message:t("err_generic")});
    else if(e.message?.startsWith("http_")){const status=parseInt(e.message.split("_")[1]);afficherErreurRiche({code:status===502||status===503?"server_busy":"unexpected"});}
    else afficherErreurRiche({code:"unexpected",message:t("err_generic")});
  }
}

async function analyserVideoUpload(file){
  if(!file)return;
  if(file.size > 50*1024*1024){ afficherErreur(t("err_file_too_large")||"Fichier trop volumineux (max 50 Mo)."); return; }
  hideHero();_adFinished=false;_analysisResult=null;
  const lastAd=parseInt(localStorage.getItem('last_ad')||'0');
  if(Date.now()-lastAd>30*60*1000){localStorage.setItem('last_ad',Date.now().toString());demarrerPub();}else{_adFinished=true;}
  const overlay=document.getElementById("loading-overlay");overlay.classList.add("active");startGame();
  const progressBar=document.getElementById("prog-fill"),percentLabel=document.getElementById("prog-percent");
  analysisAbortController=new AbortController();const signal=analysisAbortController.signal;
  const fd=new FormData();fd.append("file",file);fd.append("lang",getTMDBLang());fd.append("browser_lang",getBrowserLangShort());
  try{
    const data=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open("POST","/analyser-upload");
      xhr.upload.onprogress=e=>{if(e.lengthComputable){const p=Math.round((e.loaded/e.total)*40);if(progressBar)progressBar.style.width=p+"%";if(percentLabel)percentLabel.textContent=p+"%";}};
      xhr.onload=()=>{try{resolve(JSON.parse(xhr.responseText));}catch(e){reject(new Error("json_parse"));}};
      xhr.onerror=()=>reject(new Error("network"));
      signal.addEventListener("abort",()=>xhr.abort());
      xhr.send(fd);
    });
    if(data.status==="error"){_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();afficherErreurRiche(data);return;}
    if(data.status==="processing"&&data.session_id){const r=await pollAnalysisStatus(data.session_id,signal);await _consumeAnalysis(r,signal);return;}
    await _consumeAnalysis(data,signal);
  }catch(e){
    _adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
    if(e.name==="AbortError"||signal.aborted)return;
    afficherErreurRiche({code:"unexpected",message:t("err_generic")});
  }
}

async function _consumeAnalysis(data, signal) {
  if (data && data.status === "transcription_needed") {
    const skipWhisper = data.skip_whisper === true;

    const [ocrText, transcript] = await Promise.allSettled([
      data.frames_base64?.length
        ? runLocalOCR(data.frames_base64)
        : Promise.resolve(""),

      (!skipWhisper && data.audio_base64)
        ? runLocalWhisper(data.audio_base64)
        : Promise.resolve("")
    ]);

    const cr = await fetch("/analyser_continue", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        session_id: data.session_id,
        ocr_text: ocrText.status === "fulfilled" ? ocrText.value : "",
        transcript: transcript.status === "fulfilled" ? transcript.value : "",
        browser_lang: getBrowserLangShort()
      }),
      signal
    });

    let finalData;
    try {
      finalData = await cr.json();
    } catch (e) {
      throw new Error("json_parse");
    }

    _afficherResultatFinal(finalData);
    return;
  }

  _afficherResultatFinal(data);
}
async function pollAnalysisStatus(sessionId,signal,maxRetries=80){
  const progressBar=document.getElementById("prog-fill"),percentLabel=document.getElementById("prog-percent");let lastProgress=88;
  for(let i=0;i<maxRetries;i++){
    if(signal.aborted)throw new DOMException("Aborted","AbortError");
    try{
      const res=await fetch(`/analyser_status/${sessionId}`,{signal});if(!res.ok)throw new Error("Polling failed");
      const data=await res.json();
      let stepProgress=88;if(data.step==="downloading")stepProgress=90;else if(data.step==="processing")stepProgress=95;
      if(progressBar&&percentLabel){const tp=Math.min(stepProgress,98);if(tp>lastProgress)lastProgress=tp;progressBar.style.width=lastProgress+"%";percentLabel.textContent=Math.round(lastProgress)+"%";}
      if(data.status!=="processing"){if(progressBar)progressBar.style.width="100%";if(percentLabel)percentLabel.textContent="100%";return data;}
      await new Promise(r=>setTimeout(r,2500));
    }catch(e){if(e.name==="AbortError")throw e;console.warn("Polling error",e);await new Promise(r=>setTimeout(r,3000));}
  }
  return{status:"error",code:"timeout",message:tErr("timeout")};
}
async function runLocalOCR(framesBase64) {
  try {
    if (!framesBase64 || !framesBase64.length) return "";

    await ensureTesseractReady();

    if (!window.Tesseract) return "";

    const worker = await Tesseract.createWorker("fra+eng");
    let fullText = "";

    for (const b64 of framesBase64.slice(0, 4)) {
      try {
        const { data: { text } } = await worker.recognize(
          `data:image/jpeg;base64,${b64}`
        );
        fullText += text + " ";
      } catch (e) {}
    }

    await worker.terminate();
    return fullText.trim();
  } catch (e) {
    return "";
  }
}
async function runLocalWhisper(audioBase64) {
  try {
    if (!audioBase64) return "";

    const audioBlob = base64ToBlob(audioBase64, "audio/mp3");
    const arrayBuffer = await audioBlob.arrayBuffer();

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const audioCtxLocal = new AudioCtx();

    const audioBuffer = await audioCtxLocal.decodeAudioData(arrayBuffer);
    const pcm = audioBuffer.getChannelData(0);

    const pipeline = await window.getWhisperPipeline();

    const result = await pipeline(pcm, {
      language: "french"
    });

    return result.text || "";
  } catch (e) {
    return "";
  }
}
function base64ToBlob(base64,mimeType){const byteChars=atob(base64);const byteArrays=[];for(let offset=0;offset<byteChars.length;offset+=512){const slice=byteChars.slice(offset,offset+512);const byteNumbers=new Array(slice.length);for(let i=0;i<slice.length;i++)byteNumbers[i]=slice.charCodeAt(i);byteArrays.push(new Uint8Array(byteNumbers));}return new Blob(byteArrays,{type:mimeType});}

// ════ GENRES ════
async function chargerGenre(genreName, page = 1, mediaType = "movie", pushHistory = true) {
  setContentMode();
  if (pushHistory) _pushNav(`/genre/${genreName}`, {type:"genre", name:genreName, page, mediaType});
  hideHero(); cacherErreur();
  currentGenreName = genreName; currentPage = page;
  afficherNavCategoriesFilms(genreName);
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(`.btn-genre[href="/genre/${genreName}"]`)?.classList.add("active");

  const cacheKey = `genre_${genreName}_${page}_${getTMDBLang()}`;
  const cached = getCached(cacheKey);
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";

 
  document.getElementById("genre-title").innerText = genreName.toUpperCase();
  lastGrid = genreName; navStack = [];

  if (cached) { renderCards(cached, genreName, page, cached._tp || 10, mediaType); return; }
  document.getElementById("movie-cards").innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  try {
    const url = `/discover/${encodeURIComponent(genreName)}?lang=${getTMDBLang()}&page=${page}${mediaType === "tv" ? "&type=tv" : ""}`;
    const data = await safeFetch(url);
    if (data.status === "success") {
      const results = data.results; results._tp = data.total_pages;
      setCache(cacheKey, results);
      renderCards(data.results, genreName, page, data.total_pages, mediaType);
    } else afficherVideGrid(`<i class="fas fa-exclamation-circle"></i> ${data.message || "Genre introuvable."}`);
  } catch (e) { afficherVideGrid(`<i class="fas fa-wifi"></i> ${t("err_generic")}`); }
}


function setHomeMode() {
  document.body.classList.add("home-mode");
  document.body.classList.remove("content-mode");
}

function setContentMode() {
  document.body.classList.remove("home-mode");
  document.body.classList.add("content-mode");
}
async function chargerSeries(page = 1, pushHistory = true) {
  setContentMode();

  if (pushHistory) _pushNav("/series", { type: "series", page });

  hideHero();
  cacherErreur();

  currentGenreName = "series";
  currentPage = page;

  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(".btn-genre.series")?.classList.add("active");

  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("platform-nav").classList.remove("visible");

  document.getElementById("genre-title").innerText = tg("series").toUpperCase();

  document.getElementById("movie-cards").innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)">
      <i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i>
    </div>`;

  lastGrid = "series";
  navStack = [];

  try {
    const data = await safeFetch(`/trending?lang=${getTMDBLang()}&type=tv`);

    if (data.status === "success") {
      renderCards(
        data.results.map(r => ({ ...r, media_type: "tv" })),
        "series",
        page,
        data.total_pages || 1,
        "tv"
      );
    } else {
      afficherVideGrid(data.message || "Impossible de charger les séries.");
    }
  } catch (e) {
    afficherVideGrid(t("err_generic"));
  }
}

async function chargerTrending(pushHistory = true) {
  setContentMode();
  if (pushHistory) _pushNav('/', {type:"trending"});
  hideHero(); cacherErreur();
  currentGenreName = "trending";
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(".btn-genre.trending")?.classList.add("active");
  const cacheKey = `trending_${getTMDBLang()}`;
  const cached = getCached(cacheKey);
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  afficherNavCategoriesFilms("trending");
  document.getElementById("genre-title").innerText = tg("trending").toUpperCase();
  if (cached) { renderCards(cached, "trending", 1, 1); return; }
  document.getElementById("movie-cards").innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid = "trending"; navStack = [];
  try {
    const data = await safeFetch(`/trending?lang=${getTMDBLang()}`);
    if (data.status === "success") { setCache(cacheKey, data.results); renderCards(data.results, "trending", 1, 1); }
    else afficherVideGrid(data.message || "Impossible de charger les tendances.");
  } catch (e) { afficherVideGrid(t("err_generic")); }
}


async function chargerFilms(page = 1, pushHistory = true) {
  setContentMode();
  if (pushHistory) _pushNav("/genre/films", { type: "genre", name: "films", page });

  hideHero();
  cacherErreur();

  currentGenreName = "films";
  currentPage = page;

  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(".btn-genre.films")?.classList.add("active");

  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";

  // Quand on clique sur Film, on affiche le reste
afficherNavCategoriesFilms("trending");

  document.getElementById("genre-title").innerText = "🎬 FILMS";
  document.getElementById("movie-cards").innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)">
      <i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i>
    </div>`;

  lastGrid = "films";
  navStack = [];

  try {
    const data = await safeFetch(`/trending?lang=${getTMDBLang()}&type=movie`);

    if (data.status === "success") {
      const results = (data.results || []).filter(m => {
        const genreIds = m.genre_ids || [];
        const genreNames = (m.genres || []).map(x => String(x.name || x).toLowerCase());

        return !genreIds.includes(16) && !genreNames.includes("animation");
      });

      renderCards(results, "films", page, data.total_pages || 1, "movie");
    } else {
      afficherVideGrid(data.message || "Impossible de charger les films.");
    }
  } catch (e) {
    afficherVideGrid(t("err_generic"));
  }
}

async function chargerParPlateforme(platformKey, page = 1, pushHistory = true) {
  setContentMode();
  if (pushHistory) _pushNav(`/plateforme/${platformKey}`, {type:"platform", key:platformKey, page});
  hideHero(); cacherErreur();
  const nameMap = { netflix: "NETFLIX", amazon: "PRIME VIDEO", disney: "DISNEY+", apple: "APPLE TV+", paramount: "PARAMOUNT+", hulu: "HULU" };
  currentGenreName = platformKey; currentPage = page;
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
 afficherNavPlateformes(platformKey);
  document.getElementById("genre-title").innerText = "📺 " + (nameMap[platformKey] || platformKey.toUpperCase());
  document.getElementById("movie-cards").innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  document.querySelectorAll(".btn-platform").forEach(b => b.classList.remove("active"));
  document.querySelector(`.btn-platform[href="/plateforme/${platformKey}"]`)?.classList.add("active");
  lastGrid = platformKey; navStack = [];
  try {
    const providerLang = platformKey === "hulu" ? "en" : getBrowserLangShort();

const data = await safeFetch(
  `/discover-provider/${platformKey}?browser_lang=${providerLang}&page=${page}`
);
    if (data.status === "success" && data.results?.length) renderCards(data.results, platformKey, page, data.total_pages || 1);
    else afficherVideGrid(data.message || t("filming_no_result"));
  } catch (e) { afficherVideGrid(t("err_generic")); }
}


function afficherVideGrid(msg){document.getElementById("filtres-bar").style.display="none";document.getElementById("movie-cards").innerHTML=`<p style="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px">${msg}</p>`;}

// ════ RENDER CARDS ════
function renderCards(results, genreName, page, totalPages, mediaType = "movie") {
  _allResults = results || []; _currentTotalPages =  Math.min(totalPages || 1, 500);
  peuplerFiltreAnnee(_allResults);
  document.getElementById("filtres-bar").style.display = _allResults.length > 0 ? "flex" : "none";
  document.getElementById("filtre-count").textContent = `${_allResults.length} ${t("results")}`;
  appliquerFiltres();
  if (genreName !== "trending" && genreName !== "search") {
    setTimeout(() => {
      const container = document.getElementById("movie-cards");
      container.querySelector(".pagination")?.remove();
      const html = _paginationHTML(genreName, page, totalPages);
      if (html) {
        const pag = document.createElement("div");
        pag.className = "pagination";
        pag.innerHTML = html;
        container.appendChild(pag);
      }
    }, 0);
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function _paginationHTML(name, page, totalPages) {
  const MAX_PAGE = 500;
  totalPages = Math.min(totalPages, MAX_PAGE);
  if (!totalPages || totalPages <= 1) return "";
  const PLATFORMS = ["netflix", "amazon", "disney", "apple", "paramount", "hulu"];
  const g = String(name).replace(/'/g, "\\'");
  const call = (p) =>
    name === "series"        ? `chargerSeries(${p})` :
    PLATFORMS.includes(name) ? `chargerParPlateforme('${g}',${p})` :
                               `chargerGenre('${g}',${p})`;

  let html = `<button class="btn-page" onclick="${call(page - 1)}" ${page <= 1 ? "disabled" : ""}><i class="fas fa-chevron-left"></i></button>`;

  // Toujours afficher la 1ʳᵉ et la dernière page + une fenêtre autour de la page courante
  const wanted = new Set([1, totalPages]);
  for (let p = page - 2; p <= page + 2; p++) if (p >= 1 && p <= totalPages) wanted.add(p);
  const list = [...wanted].sort((a, b) => a - b);

  let prev = 0;
  for (const p of list) {
    if (p - prev > 1) html += `<span class="page-ellipsis">…</span>`;
    html += `<button class="btn-page ${p === page ? "active" : ""}" onclick="${call(p)}" ${p === page ? "disabled" : ""}>${p}</button>`;
    prev = p;
  }
  html += `<button class="btn-page" onclick="${call(page + 1)}" ${page >= totalPages ? "disabled" : ""}><i class="fas fa-chevron-right"></i></button>`;
  return html;
}
function peuplerFiltreAnnee(results){
  const sel=document.getElementById("filtre-annee");
  const annees=[...new Set(results.map(m=>(m.release_date||m.first_air_date||"").split("-")[0]).filter(Boolean))].sort((a,b)=>b-a);
  sel.innerHTML=`<option value="">📅 ${t("year")}</option>`+annees.map(a=>`<option value="${a}">${a}</option>`).join("");
}
function appliquerFiltres(){
  const annee=document.getElementById("filtre-annee").value;
  const note=parseFloat(document.getElementById("filtre-note").value)||0;
  const tri=document.getElementById("filtre-tri").value;
  let res=_allResults.filter(m=>{const y=(m.release_date||m.first_air_date||"").split("-")[0];return(!annee||y===annee)&&(m.vote_average||0)>=note;});
  if(tri==="note_desc")res.sort((a,b)=>(b.vote_average||0)-(a.vote_average||0));
  else if(tri==="note_asc")res.sort((a,b)=>(a.vote_average||0)-(b.vote_average||0));
  else if(tri==="recent")res.sort((a,b)=>(b.release_date||b.first_air_date||"").localeCompare(a.release_date||a.first_air_date||""));
  else if(tri==="ancien")res.sort((a,b)=>(a.release_date||a.first_air_date||"").localeCompare(b.release_date||b.first_air_date||""));
 document.getElementById("filtre-count").textContent=`${res.length} ${t("results")}`;
  renderCardsFiltered(res);
}
function reinitFiltres(){document.getElementById("filtre-annee").value="";document.getElementById("filtre-note").value="";document.getElementById("filtre-tri").value="pop";appliquerFiltres();}
function renderCardsFiltered(results){
  const container=document.getElementById("movie-cards"),oldPag=container.querySelector(".pagination");
  [...container.children].forEach(c=>{if(!c.classList.contains("pagination"))c.remove();});
  if(!results||results.length===0){const p=document.createElement("p");p.style.cssText="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px";p.textContent="Aucun résultat avec ces filtres.";if(oldPag)container.insertBefore(p,oldPag);else container.appendChild(p);return;}
  const fragment=document.createDocumentFragment();
  results.forEach((m, index)=>{
    const year=(m.release_date||m.first_air_date||"N/A").split("-")[0];
    const rating=m.vote_average?m.vote_average.toFixed(1):"0";
    const title=m.title||m.name||"Titre inconnu";
    const isTv=m.media_type==="tv"||!!m.first_air_date;
    const poster=m.poster_path?`https://image.tmdb.org/t/p/w300${m.poster_path}`:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
    const div=document.createElement("div");div.className="movie-card";div.setAttribute("role","button");div.setAttribute("tabindex","0");div.setAttribute("aria-label",title);
    div.onclick=()=>afficherDetails(m.id,isTv?"tv":"movie");div.onkeydown=e=>{if(e.key==="Enter")afficherDetails(m.id,isTv?"tv":"movie");};
    div.innerHTML=`${isTv?`<span class="card-type-badge">TV</span>`:""}<img src="${poster}" alt="${title}" ${index === 0 ? 'loading="eager" fetchpriority="high"' : 'loading="lazy" fetchpriority="low"'}><div class="card-body"><h4>${title}</h4><div class="card-meta"><span><i class="fas fa-calendar" style="font-size:.65rem;opacity:.5"></i> ${year}</span><span class="rating"><i class="fas fa-star" style="font-size:.65rem"></i> ${rating}</span></div></div>`;
    fragment.appendChild(div);
  });
  if(oldPag)container.insertBefore(fragment,oldPag);else container.appendChild(fragment);
}
function afficherResultatsRecherche(data,query){
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("genre-title").innerText=`🔍 "${query}"`;
  lastGrid="search";navStack=[];
  renderCards(data.results||[],"search",1,1);
}

// ════════════════════════════════════════════════════════════════
// FILMING PAGE v5.0 — CORRIGÉ
// ════════════════════════════════════════════════════════════════

// Éléments temporaires carte (isochrone, tracés, labels)
let _tempMapLayers = [];

function _clearTempLayers() {
  _tempMapLayers.forEach(l => { try { _filmingMap.removeLayer(l); } catch(e){} });
  _tempMapLayers = [];
  if (_isochroneLayer) { try { _filmingMap.removeLayer(_isochroneLayer); } catch(e){} _isochroneLayer = null; }
}

async function chargerLieuxDeTournage(page = 1, pushHistory = true) {
  setContentMode();

  if (pushHistory) {
    _pushNav("/lieux-de-tournage", { type: "filming", page });
  }

  cacherErreur();
  _hideAllPages();

  currentGenreName = "filming";
  _filmingCurrentPage = page;

  const filmingPage = document.getElementById("filming-page");
  if (!filmingPage) return;

  document.getElementById("genre-nav").style.display = "flex";
  document.getElementById("platform-nav").classList.remove("visible");

  filmingPage.style.display = "grid";
  navStack = [];

  // 1. Afficher l’interface tout de suite
  _renderFilmingPage(filmingPage);

  // 2. Charger rapidement la liste des films
  const results = await _loadFilmingCatalogue();

  // 3. Charger stats + filtres en arrière-plan
  Promise.allSettled([
    _filmingStats
      ? Promise.resolve()
      : safeFetch("/films-tournes/stats")
          .then(d => { _filmingStats = d; })
          .catch(() => {}),

    typeof _chargerMetaFiltres === "function"
      ? _chargerMetaFiltres()
      : Promise.resolve()
  ]).then(() => {
    _updateFilmingFilters();
  });

  // 4. Initialiser la carte après affichage
  requestAnimationFrame(() => {
    setTimeout(() => {
      _ensureLeafletFull(() => {
        _initFilmingLeafletMap();

        setTimeout(() => {
          if (_filmingMap) {
            _filmingMap.invalidateSize();
            _updateFilmingMapMarkers(results || []);
          }
        }, 300);
      });
    }, 0);
  });
}

function _renderFilmingPage(container){
  const ld=dict[currentLang]||dict.fr;
  const stats=_filmingStats;
  const statsHtml=stats?`<div class="filming-stats-bar"><span><strong>${stats.total_films?.toLocaleString()||"—"}</strong> Films</span><span class="filming-stats-sep">·</span><span><strong>${stats.total_locations?.toLocaleString()||"—"}</strong> lieux</span></div>`:"";
  container.innerHTML=`
    <div class="filming-sidebar" id="filming-sidebar">
      <div class="filming-sidebar-header">
        <div class="filming-hero">
          <h1 class="filming-title"><i class="fas fa-map-marked-alt"></i> ${ld.filming_title||"LIEUX DE TOURNAGE"}</h1>
          ${statsHtml}
        </div>
        <div class="filming-filters-wrap">
          <div class="filming-search-box">
            <i class="fas fa-search"></i>
            <input type="text" id="filming-search-input" placeholder="${ld.filming_search||'Rechercher un film…'}" value="${escapeHtml(_filmingCurrentQ)}" oninput="debounceFilmingSearch(this.value)" onkeydown="if(event.key==='Enter')chargerLieuxDeTournage(1)">
          </div>
          <div class="filming-filters-row-2">
            <div class="filming-filter-group">
              <label><i class="fas fa-film"></i> Type</label>
              <div class="filming-media-toggle">
                <button class="fmedia-btn ${!_filmingCurrentType?'active':''}" onclick="setFilmingType('')">Tous</button>
                <button class="fmedia-btn ${_filmingCurrentType==='movie'?'active':''}" onclick="setFilmingType('movie')">Films</button>
              </div>
            </div>
            <div class="filming-filter-group">
              <label><i class="fas fa-map-pin"></i> Lieu</label>
              <select id="filming-filter-country" onchange="setFilmingCountry(this.value)">
                <option value="">Tous</option>
              </select>
            </div>
          </div>
          <div class="filming-filters-row-2">
            <div class="filming-filter-group">
              <label><i class="fas fa-calendar"></i> Année</label>
              <select id="filming-filter-year" onchange="setFilmingYear(this.value)">
                <option value="">Toutes</option>
              </select>
            </div>
            <div class="filming-filter-group filming-filter-empty"></div>
          </div>
          <div class="filming-reset-row">
            <button class="fmap-btn filming-reset-btn" onclick="resetFilmingFilters()"><i class="fas fa-times"></i> Réinitialiser</button>
          </div>
        </div>
      </div>
      <div class="filming-grid-wrap" id="filming-grid-wrap">
        <div id="filming-cards" class="filming-cards"></div>
        <div id="filming-pagination" class="filming-pagination"></div>
      </div>
    </div>
    <div class="filming-map-wrap" id="filming-map-wrap">
      <div class="filming-map-toolbar">
        <div class="filming-map-toolbar-left">
          <button class="fmap-btn active" id="fmap-layer-film" title="Tournages"><i class="fas fa-film"></i> <span>Tournages</span></button>
          <button class="fmap-btn" id="fmap-layer-hotel" onclick="toggleFilmingLayer('hotel')" title="Hôtels"><i class="fas fa-bed"></i> <span>Hôtels</span></button>
          <button class="fmap-btn" id="fmap-layer-restaurant" onclick="toggleFilmingLayer('restaurant')" title="Restaurants"><i class="fas fa-utensils"></i> <span>Restos</span></button>
          <button class="fmap-btn" id="fmap-layer-transport" onclick="toggleFilmingLayer('transport')" title="Transports"><i class="fas fa-train"></i> <span>Transports</span></button>
          <button class="fmap-btn" id="fmap-layer-tourism" onclick="toggleFilmingLayer('tourism')" title="Services"><i class="fas fa-info-circle"></i> <span>Services</span></button>
        </div>
        <div class="filming-map-toolbar-right">
          <button class="fmap-btn" id="fmap-heatmap" onclick="toggleFilmingHeatmap()" title="Heatmap"><i class="fas fa-fire"></i></button>
          <button class="fmap-btn" id="fmap-near-me" onclick="filmingNearMe()" title="Près de moi"><i class="fas fa-crosshairs"></i></button>
          <button class="fmap-btn" id="fmap-fullscreen" onclick="toggleFilmingMapFullscreen()" title="Plein écran"><i class="fas fa-expand"></i></button>
        </div>
      </div>
      <div id="filming-leaflet-map"></div>
      <div class="filming-map-legend">
        <span class="fmap-legend-item"><span class="fmap-dot fmap-dot-film"></span> Tournages</span>
        <span class="fmap-legend-item"><span class="fmap-dot" style="background:#ffd700"></span> Hôtels</span>
        <span class="fmap-legend-item"><span class="fmap-dot" style="background:#f06595"></span> Restos</span>
        <span class="fmap-legend-item"><span class="fmap-dot" style="background:#74c0fc"></span> Transports</span>
        <span class="fmap-legend-item"><span class="fmap-dot" style="background:#4dabf7"></span> Services</span>
      </div>
    </div>`;
  _initFilmingLeafletMap();
  // Peupler filtres depuis cache global
  _peuplerFiltresPays();
  _peuplerFiltresAnnees();
}

// ════ CACHE GLOBAL ANNÉES & PAYS ════
let _filmingAllYears = [];
let _filmingAllCountries = [];

async function _chargerMetaFiltres() {
  if (_filmingAllYears.length > 0 && _filmingAllCountries.length > 0) return;

  // Essai 1 : endpoint /films-tournes/meta (lit le JSON complet côté serveur)
  try {
    const meta = await safeFetch(`/films-tournes/meta`);
    if (meta.years && meta.years.length > 0) {
      _filmingAllYears     = [...new Set(meta.years)].map(Number).sort((a,b)=>b-a);
      // L'endpoint retourne "locations" (noms de villes/pays depuis name)
      const locs = meta.locations || meta.countries || [];
      _filmingAllCountries = [...new Set(locs)].filter(Boolean).sort((a,b)=>a.localeCompare(b));
      console.log(`✅ Meta filtres: ${_filmingAllYears.length} années, ${_filmingAllCountries.length} lieux`);
      return;
    }
  } catch(e) { /* endpoint absent, fallback */ }

  // Essai 2 : charger page par page et extraire depuis les résultats
  console.log("📥 Chargement meta filtres page par page…");
  const yearsSet = new Set();
  const locsSet  = new Set();

  const extractFromResults = (results) => {
    (results||[]).forEach(f => {
      if (f.year) yearsSet.add(Number(f.year));
      (f.locations||[]).forEach(l => {
        // country est toujours "Inconnu" → vrai nom dans l.name
        const nom = (l.country && l.country !== "Inconnu") ? l.country : l.name;
        if (nom && nom.length > 1 && nom !== "Non spécifié" && nom !== "Inconnu") locsSet.add(nom);
      });
    });
  };

  try {
    // Première page avec per_page max
    const first = await safeFetch(`/films-tournes?per_page=500&sort=count_locations&page=1`);
    if (first.status !== "success") return;
    extractFromResults(first.results);

    // Pages suivantes si nécessaire
    const totalPages = first.total_pages || 1;
    if (totalPages > 1) {
      const pages = [];
      for (let p = 2; p <= totalPages; p++) {
        pages.push(safeFetch(`/films-tournes?per_page=500&sort=count_locations&page=${p}`).catch(()=>null));
      }
      const settled = await Promise.allSettled(pages);
      settled.forEach(r => {
        if (r.status === "fulfilled" && r.value?.results) extractFromResults(r.value.results);
      });
    }

    _filmingAllYears     = [...yearsSet].sort((a,b)=>b-a);
    _filmingAllCountries = [...locsSet].sort((a,b)=>a.localeCompare(b));
    console.log(`✅ Meta filtres (fallback): ${_filmingAllYears.length} années, ${_filmingAllCountries.length} lieux`);
  } catch(e) {
    console.warn("Meta filtres KO:", e);
  }
}

// ════ PAYS — extraits depuis le cache global ════
function _peuplerFiltresPays(){
  const sel = document.getElementById("filming-filter-country");
  if (!sel) return;
  const cv = sel.value;
  sel.innerHTML = `<option value="">Tous</option>` +
    _filmingAllCountries.map(c => `<option value="${escapeHtml(c)}" ${cv===c?'selected':''}>${escapeHtml(c)}</option>`).join("");
}

// ════ ANNÉES — depuis le cache global ════
function _peuplerFiltresAnnees(){
  const sel = document.getElementById("filming-filter-year");
  if (!sel) return;
  const cv = sel.value;
  sel.innerHTML = `<option value="">Toutes</option>` +
    _filmingAllYears.map(y => `<option value="${y}" ${cv==y?'selected':''}>${y}</option>`).join("");
}
function _updateFilmingFilters(){
  const btns=document.querySelectorAll(".fmedia-btn");
  const types=['','movie'];
  btns.forEach((btn,idx)=>btn.classList.toggle("active",_filmingCurrentType===(types[idx]??'')));
  // Re-peupler depuis le cache si déjà chargé
  _peuplerFiltresPays();
  _peuplerFiltresAnnees();
  // Restaurer la valeur sélectionnée
  const fy=document.getElementById("filming-filter-year");if(fy)fy.value=_filmingCurrentYear;
  const cs=document.getElementById("filming-filter-country");if(cs)cs.value=_filmingCurrentCountry;
  const si=document.getElementById("filming-search-input");if(si)si.value=_filmingCurrentQ;
}

let _filmingSearchTimeout=null;
function debounceFilmingSearch(val){_filmingCurrentQ=val;clearTimeout(_filmingSearchTimeout);_filmingSearchTimeout=setTimeout(()=>chargerLieuxDeTournage(1),500);}
function setFilmingType(type){_filmingCurrentType=type;_updateFilmingFilters();_loadFilmingCatalogue();}
async function setFilmingCountry(country){_filmingCurrentCountry=country;_updateFilmingFilters();_loadFilmingCatalogue();}
function setFilmingYear(year){_filmingCurrentYear=year;_filmingCurrentPage=1;_loadFilmingCatalogue();}
function resetFilmingFilters(){_filmingCurrentCountry="";_filmingCurrentYear="";_filmingCurrentType="";_filmingCurrentQ="";_filmingCurrentPage=1;_updateFilmingFilters();_loadFilmingCatalogue();}

async function _loadFilmingCatalogue(){
  const cardsEl=document.getElementById("filming-cards");
  if(!cardsEl)return;
  cardsEl.innerHTML=`<div class="filming-loading"><i class="fas fa-circle-notch fa-spin"></i> Chargement…</div>`;

  const params=new URLSearchParams({page:_filmingCurrentPage,per_page:24,sort:"count_locations"});
  if(_filmingCurrentType)params.set("media_type",_filmingCurrentType);
  if(_filmingCurrentQ)params.set("q",_filmingCurrentQ);
  if(_filmingCurrentYear)params.set("year",_filmingCurrentYear);
  // Passer le lieu comme paramètre "city" (filtrage côté serveur)
  if(_filmingCurrentCountry)params.set("city",_filmingCurrentCountry);

  try{
    const data=await safeFetch(`/films-tournes?${params}`);
    if(data.status!=="success"){
      cardsEl.innerHTML=`<p style="color:var(--muted);text-align:center;padding:40px;grid-column:1/-1">Aucun résultat.</p>`;
      return;
    }
   const results = data.results || [];

_renderFilmingCards(cardsEl, results);
_renderFilmingPagination(data.page, data.total_pages);
_updateFilmingMapMarkers(results);

return results;
  }catch(e){
     if (cardsEl) {
    cardsEl.innerHTML = `<p style="color:var(--muted);text-align:center;padding:40px;grid-column:1/-1">Erreur de chargement.</p>`;
  }
   return [];
}
} 

function _renderFilmingCards(container,results){
  if(!results||results.length===0){container.innerHTML=`<p style="color:var(--muted);text-align:center;padding:60px;grid-column:1/-1">Aucun film trouvé.</p>`;return;}
  container.innerHTML=results.map(f=>{
    const poster=f.poster_path?`https://image.tmdb.org/t/p/w300${f.poster_path}`:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
    const rating=f.vote_average?f.vote_average.toFixed(1):"—";
    const year=f.year||"—";
    const locCount=f.location_count||(f.locations||[]).length||0;
    const countryNames=[...new Set((f.locations||[]).map(l=>l.country&&l.country!=="Inconnu"?l.country:l.name).filter(Boolean))].slice(0,2).join(", ");
    const primaryLoc=f.primary_location||(f.locations&&f.locations[0])||null;
    const safeTitle=(f.title||"Inconnu").replace(/'/g,"\\'").replace(/"/g,"&quot;");
    const btnLabel=locCount===1?"Voir le lieu de tournage":`Voir les ${locCount} lieux`;
    return `<div class="filming-card" role="button" tabindex="0">
      <div class="filming-card-img-wrap" onclick="afficherDetails(${f.tmdb_id},'movie')">
        <img src="${poster}" alt="${escapeHtml(f.title)}" loading="lazy">
        <div class="filming-card-loc-badge"><i class="fas fa-map-marker-alt"></i> ${locCount}</div>
      </div>
      <div class="filming-card-body">
        <h4 onclick="afficherDetails(${f.tmdb_id},'movie')">${escapeHtml(f.title)}</h4>
        <div class="filming-card-meta"><span class="filming-card-year">${year}</span><span class="filming-card-rating"><i class="fas fa-star"></i> ${rating}</span></div>
        ${countryNames?`<div class="filming-card-countries"><i class="fas fa-globe-europe"></i> ${escapeHtml(countryNames)}</div>`:""}
        ${primaryLoc?`<div class="filming-card-primary-loc"><i class="fas fa-map-pin"></i> ${escapeHtml(primaryLoc.name)}</div>`:""}
        ${locCount>0?`<button class="filming-show-locations-btn" onclick="showFilmLocationsOnMap(${f.tmdb_id},'${safeTitle}','movie')"><i class="fas fa-map-marked-alt"></i> ${btnLabel}</button>`:""}
      </div>
    </div>`;
  }).join("");
}

function _renderFilmingPagination(page,totalPages){
  const pag=document.getElementById("filming-pagination");
  if(!pag||totalPages<=1){if(pag)pag.innerHTML="";return;}
  const start=Math.max(1,page-2),end=Math.min(totalPages,start+4);
  let html=`<button class="btn-page" onclick="_filmingCurrentPage=${page-1};_loadFilmingCatalogue()" ${page<=1?"disabled":""}><i class="fas fa-chevron-left"></i></button>`;
  for(let i=start;i<=end;i++)html+=`<button class="btn-page ${i===page?"active":""}" onclick="_filmingCurrentPage=${i};_loadFilmingCatalogue()">${i}</button>`;
  html+=`<button class="btn-page" onclick="_filmingCurrentPage=${page+1};_loadFilmingCatalogue()" ${page>=totalPages?"disabled":""}><i class="fas fa-chevron-right"></i></button>`;
  html+=`<span class="page-info">${page} / ${totalPages}</span>`;
  pag.innerHTML=html;
}

// ════ CARTE LEAFLET ════
function _initFilmingLeafletMap(){
  _ensureLeafletFull(()=>{
    const mapEl=document.getElementById("filming-leaflet-map");
    if(!mapEl||!window.L)return;
    if(_filmingMap){_filmingMap.remove();_filmingMap=null;}
    _filmingAllMarkers=[];
    _filmingMap=L.map(mapEl,{center:[20,0],zoom:2,zoomControl:false,scrollWheelZoom:true});
    L.control.zoom({position:"topright"}).addTo(_filmingMap);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(_filmingMap);
    _filmingFilmLayer=L.layerGroup().addTo(_filmingMap);
    _filmingHotelLayer=L.layerGroup();
    _filmingTourismLayer=L.layerGroup();
    _filmingRestaurantLayer=L.layerGroup();
    _filmingTransportLayer=L.layerGroup();
    if(window.L.markerClusterGroup){
      _filmingMarkerClusterGroup=L.markerClusterGroup({maxClusterRadius:60,showCoverageOnHover:false,iconCreateFunction:cluster=>{const n=cluster.getChildCount(),s=n>100?50:n>30?40:32;return L.divIcon({html:`<div class="fmap-cluster" style="width:${s}px;height:${s}px">${n>999?"999+":n}</div>`,className:"",iconSize:[s,s],iconAnchor:[s/2,s/2]});}});
      _filmingMap.addLayer(_filmingMarkerClusterGroup);
    }
    _filmingLeafletReady=true;
    setTimeout(()=>_filmingMap?.invalidateSize(),400);
    _filmingMap.on("moveend",handleMapMove);
  });
}

function _ensureLeafletFull(callback){
  if(window.L&&window.L.markerClusterGroup){callback();return;}
  if(!document.querySelector('link[href*="leaflet.css"]')){const lk=document.createElement("link");lk.rel="stylesheet";lk.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";document.head.appendChild(lk);}
  if(!document.querySelector('link[href*="MarkerCluster.css"]')){const lk2=document.createElement("link");lk2.rel="stylesheet";lk2.href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css";document.head.appendChild(lk2);const lk3=document.createElement("link");lk3.rel="stylesheet";lk3.href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css";document.head.appendChild(lk3);}
  const scripts=[
    {src:"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",check:()=>!!window.L},
    {src:"https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js",check:()=>!!window.L?.markerClusterGroup},
    {src:"https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js",check:()=>!!window.L?.heatLayer},
    {src:"https://unpkg.com/leaflet-ant-path@1.3.0/dist/leaflet-ant-path.js",check:()=>!!window.L?.polyline?.antPath},
  ];
  function loadNext(idx){if(idx>=scripts.length){callback();return;}const{src,check}=scripts[idx];if(check()){loadNext(idx+1);return;}const s=document.createElement("script");s.src=src;s.onload=()=>loadNext(idx+1);s.onerror=()=>loadNext(idx+1);document.head.appendChild(s);}
  loadNext(0);
}

// ════ CACHE LOCAL DES LOCATIONS PAR FILM ════
const _filmLocationsCache = new Map();

// ════ MARQUEURS FILMS (cluster général) ════
function _updateFilmingMapMarkers(films){
  if(!_filmingLeafletReady||!_filmingMap)return;
  if(_filmingMarkerClusterGroup)_filmingMarkerClusterGroup.clearLayers();
  _filmingAllMarkers=[];
  const bounds=L.latLngBounds();

  films.forEach(f=>{
    // Stocker locations en cache local
    const locs=(f.locations||[]).filter(l=>l.lat!=null&&l.lng!=null);
    if(locs.length>0)_filmLocationsCache.set(f.tmdb_id,locs);

    const loc=f.primary_location||locs[0]||null;
    if(!loc||loc.lat==null)return;

    const posterUrl=f.poster_path?`https://image.tmdb.org/t/p/w92${f.poster_path}`:null;

    // Marqueur SVG inline — visible quelle que soit la police chargée
    const bgStyle=posterUrl
      ?`background-image:url('${posterUrl}');background-size:cover;background-position:center;`
      :`background:#1a1a2e;`;
    const iconHtml=`<div style="${bgStyle}width:36px;height:36px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2.5px solid #00ffcc;box-shadow:0 3px 10px rgba(0,255,204,.4);overflow:hidden;"></div>`;

    const icon=L.divIcon({html:iconHtml,className:"",iconSize:[36,36],iconAnchor:[18,36],popupAnchor:[0,-40]});
    const marker=L.marker([loc.lat,loc.lng],{icon});

    marker.on('contextmenu',e=>{
      navigator.clipboard.writeText(`${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`)
        .then(()=>toast("📍 Coordonnées copiées"));
    });

    const bookQ=encodeURIComponent(loc.name);
    const safeT=escapeHtml(f.title).replace(/'/g,"\\'");
    marker.bindPopup(
      `<div class="fmap-popup">
        ${posterUrl?`<img src="${posterUrl}" class="fmap-popup-poster" alt="">`:""}
        <div class="fmap-popup-body">
          <div class="fmap-popup-title">${escapeHtml(f.title)}</div>
          <div class="fmap-popup-meta">${f.year||""}${f.vote_average?` · ⭐ ${f.vote_average.toFixed(1)}`:""}</div>
          <div class="fmap-popup-loc">📍 ${escapeHtml(loc.name)}</div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px;">
            <button class="fmap-popup-btn" onclick="afficherDetails(${f.tmdb_id},'movie')">🎬 Détails</button>
            <button class="fmap-popup-btn" onclick="showFilmLocationsOnMap(${f.tmdb_id},'${safeT}','movie')">🗺 Voir lieux</button>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:4px;">
            <button class="fmap-popup-btn btn-osm-action" data-type="hotel" data-lat="${loc.lat}" data-lng="${loc.lng}">🏨 Hôtels</button>
            <button class="fmap-popup-btn btn-osm-action" data-type="restaurant" data-lat="${loc.lat}" data-lng="${loc.lng}">🍽 Restos</button>
            <button class="fmap-popup-btn btn-osm-action" data-type="transport" data-lat="${loc.lat}" data-lng="${loc.lng}">🚆 Transports</button>
            <button class="fmap-popup-btn btn-osm-action" data-type="isochrone" data-lat="${loc.lat}" data-lng="${loc.lng}">🚶 15 min</button>
          </div>
          <a href="https://www.booking.com/searchresults.html?ss=${bookQ}&aid=Pelify"
             target="_blank" rel="sponsored noopener"
             class="fmap-popup-btn fmap-popup-booking"
             style="margin-top:6px;display:inline-flex;">🛏 Booking.com</a>
        </div>
      </div>`,
      {maxWidth:300}
    );

    if(_filmingMarkerClusterGroup)_filmingMarkerClusterGroup.addLayer(marker);
    _filmingAllMarkers.push({lat:loc.lat,lng:loc.lng,marker,film:f});
    bounds.extend([loc.lat,loc.lng]);
  });

  if(bounds.isValid())_filmingMap.flyToBounds(bounds,{padding:[50,50],duration:1.5});
}

// ════ LIEUX D'UN FILM ════
// Utilise le cache local (données déjà dans le JSON catalogue) en priorité
// Fallback vers l'API Wikidata seulement si pas en cache
async function showFilmLocationsOnMap(tmdbId,title,mediaType='movie'){
  if(!_filmingMap||!_filmingLeafletReady)return;
  _stopBounce();
  _clearTempLayers();

  // Masquer le cluster global
  if(_filmingMarkerClusterGroup&&_filmingMap.hasLayer(_filmingMarkerClusterGroup)){
    _filmingMap.removeLayer(_filmingMarkerClusterGroup);
  }
  if(_filmingFilmLayer&&!_filmingMap.hasLayer(_filmingFilmLayer)){
    _filmingMap.addLayer(_filmingFilmLayer);
  }
  if(_filmingFilmLayer)_filmingFilmLayer.clearLayers();
  _activeFilmMarkers=[];

  // ── Priorité 1 : locations déjà en cache local (depuis le JSON catalogue) ──
  let locations = _filmLocationsCache.get(tmdbId) || [];

  // ── Priorité 2 : appel API Wikidata (fallback) ──
  if(locations.length===0){
    toast(`📍 Chargement des lieux de "${title}"…`);
    try{
      const data=await safeFetch(`/movie/${tmdbId}/locations?type=${mediaType}`);
      locations=(data.locations||[]).filter(l=>l.lat!=null&&l.lng!=null);
      if(locations.length>0)_filmLocationsCache.set(tmdbId, locations);
    }catch(e){ /* silencieux */ }
  }

  if(locations.length===0){
    if(_filmingMarkerClusterGroup)_filmingMap.addLayer(_filmingMarkerClusterGroup);
    toast("Aucun lieu géolocalisé pour ce film.");
    return;
  }

  const bounds=L.latLngBounds();
  locations.forEach(loc=>{
    const marker=_createFilmLocationMarker(loc,title,tmdbId,mediaType);
    _filmingFilmLayer.addLayer(marker);
    _activeFilmMarkers.push(marker);
    bounds.extend([loc.lat,loc.lng]);
  });

  if(bounds.isValid())_filmingMap.flyToBounds(bounds,{padding:[60,60],duration:1.2,maxZoom:13});
  _startBounce();
  // Sur mobile : scroller vers la carte
  const mapWrap=document.getElementById("filming-map-wrap");
  if(mapWrap&&window.innerWidth<=768){mapWrap.scrollIntoView({behavior:"smooth",block:"start"});}
  // POI autour du premier lieu
  if(locations[0])_autoLoadPOIsAround(locations[0].lat,locations[0].lng);
}

function _createFilmLocationMarker(loc,filmTitle,tmdbId,mediaType){
  // Marqueur SVG inline — aucune dépendance FA, toujours visible
  const svgPin=`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="42" viewBox="0 0 32 42">
    <path d="M16 0 C7.16 0 0 7.16 0 16 C0 28 16 42 16 42 C16 42 32 28 32 16 C32 7.16 24.84 0 16 0Z" fill="#ff007f" stroke="#fff" stroke-width="2"/>
    <circle cx="16" cy="16" r="7" fill="#fff"/>
  </svg>`;
  const icon=L.divIcon({
    html:svgPin,
    className:"",
    iconSize:[32,42],
    iconAnchor:[16,42],
    popupAnchor:[0,-44]
  });
  const marker=L.marker([loc.lat,loc.lng],{icon,zIndexOffset:1000});
  marker.on('contextmenu',e=>{
    navigator.clipboard.writeText(`${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`)
      .then(()=>toast("📍 Coordonnées copiées"));
  });
  const bookQ=encodeURIComponent(loc.name);
  const safeT=filmTitle.replace(/'/g,"\\'");
  marker.bindPopup(
    `<div class="fmap-popup-loc">
      <div class="fmap-popup-loc-title">🎬 ${escapeHtml(filmTitle)}</div>
      <div class="fmap-popup-loc-name">📍 ${escapeHtml(loc.name)}</div>
      <div class="fmap-popup-actions" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">
        <button class="fmap-popup-btn" onclick="showAllFilmLocations()">◀ Tous les lieux</button>
        <button class="fmap-popup-btn btn-osm-action" data-type="hotel" data-lat="${loc.lat}" data-lng="${loc.lng}">🏨 Hôtels</button>
        <button class="fmap-popup-btn btn-osm-action" data-type="restaurant" data-lat="${loc.lat}" data-lng="${loc.lng}">🍽 Restos</button>
        <button class="fmap-popup-btn btn-osm-action" data-type="transport" data-lat="${loc.lat}" data-lng="${loc.lng}">🚆 Transports</button>
        <button class="fmap-popup-btn btn-osm-action" data-type="isochrone" data-lat="${loc.lat}" data-lng="${loc.lng}">🚶 15 min</button>
      </div>
      <a href="https://www.booking.com/searchresults.html?ss=${bookQ}&aid=Pelify"
         target="_blank" rel="sponsored noopener"
         class="fmap-popup-btn fmap-popup-booking"
         style="margin-top:6px;display:inline-flex;">
        🛏 Booking.com
      </a>
    </div>`,
    {maxWidth:300}
  );
  return marker;
}

function showAllFilmLocations(){
  if(!_filmingMap||!_filmingLeafletReady)return;
  _stopBounce();
  _clearTempLayers();
  if(_filmingFilmLayer)_filmingFilmLayer.clearLayers();
  _activeFilmMarkers=[];
  if(_filmingMarkerClusterGroup&&!_filmingMap.hasLayer(_filmingMarkerClusterGroup)){
    _filmingMap.addLayer(_filmingMarkerClusterGroup);
  }
  toast("🗺️ Tous les lieux affichés");
}

// ════ BOUNCE ════
function _startBounce(){_stopBounce();_doBounce();_bounceInterval=setInterval(_doBounce,10000);}
function _stopBounce(){if(_bounceInterval){clearInterval(_bounceInterval);_bounceInterval=null;}_activeFilmMarkers.forEach(m=>{const el=m.getElement();if(el)el.classList.remove("fmap-bounce");});}
function _doBounce(){_activeFilmMarkers.forEach(m=>{const el=m.getElement();if(!el)return;el.classList.remove("fmap-bounce");void el.offsetWidth;el.classList.add("fmap-bounce");});}

// ════ POI VIA PROXY BACKEND (évite les blocages Nominatim côté client) ════
// Le backend /api/poi/auto appelle Nominatim côté serveur avec cache 24h.

async function _autoLoadPOIsAround(lat, lng) {
  const cacheKey = `poi_auto_${lat.toFixed(3)}_${lng.toFixed(3)}`;
  // Cache localStorage 24h
  try {
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      const c = JSON.parse(cached);
      if (Date.now() - c.time < 86400000) { _applyAutoPOIs(c.data, lat, lng); return; }
    }
  } catch(e) {}

  try {
    const data = await safeFetch(`/api/poi/auto?lat=${lat}&lng=${lng}`);
    const elements = (data.results || []).slice(0, 12);
    try { localStorage.setItem(cacheKey, JSON.stringify({time: Date.now(), data: elements})); } catch(e) {}
    _applyAutoPOIs(elements, lat, lng);
  } catch(e) {
    // Silencieux
  }
}

function _applyAutoPOIs(elements, originLat, originLng) {
  if (!_filmingMap || !elements.length) return;
  const typeMap  = {hotel:_filmingHotelLayer, restaurant:_filmingRestaurantLayer, transport:_filmingTransportLayer, service:_filmingTourismLayer};
  const colorMap = {hotel:"#ffd700", restaurant:"#f06595", transport:"#74c0fc", service:"#4dabf7"};
  const iconMap  = {hotel:"fa-bed",  restaurant:"fa-utensils", transport:"fa-train", service:"fa-info-circle"};

  elements.forEach(el => {
    if (!el.lat || !el.lon) return;
    const tags = el.tags || {};
    // Type depuis _poiType (Nominatim) ou heuristique (Overpass)
    let type = el._poiType || "service";
    if (!el._poiType) {
      if (tags.tourism) type = "hotel";
      else if (tags.amenity==="restaurant"||tags.amenity==="cafe") type = "restaurant";
      else if (tags.railway) type = "transport";
    }

    const layer = typeMap[type];
    if (!layer) return;
    const color = colorMap[type], icn = iconMap[type];
    const name  = tags.name || type;
    const dist  = Math.round(_haversineM(originLat, originLng, el.lat, el.lon));

    const icon = L.divIcon({
      html:`<div style="background:#0d0d14;border:2px solid ${color};color:${color};width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.5)"><i class="fas ${icn}" style="font-size:8px"></i></div>`,
      className:"",iconSize:[22,22],iconAnchor:[11,11]
    });
    const marker = L.marker([el.lat, el.lon], {icon});

    // Tracé vers le point de tournage
    const lineStyle = {color, weight:1.5, opacity:0.65, dashArray:"5,8"};
    let line;
    if (window.L?.polyline?.antPath) {
      line = L.polyline.antPath([[originLat,originLng],[el.lat,el.lon]], {...lineStyle, dashArray:[5,12], delay:800, pulseColor:"rgba(255,255,255,0.4)"});
    } else {
      line = L.polyline([[originLat,originLng],[el.lat,el.lon]], lineStyle);
    }
    line.addTo(_filmingMap);
    _tempMapLayers.push(line);

    let bookLink = type==="hotel"
      ? `<a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(name)}&aid=Pelify" target="_blank" rel="sponsored noopener" class="fmap-popup-btn fmap-popup-booking" style="margin-top:5px;display:inline-flex;font-size:.62rem"><i class="fas fa-bed"></i> Booking</a>`
      : "";

    marker.bindPopup(`<div class="fmap-popup-small" style="min-width:130px"><span style="font-size:.58rem;color:${color};text-transform:uppercase;font-weight:700">${type}</span><strong style="display:block;font-size:.8rem;margin:2px 0;color:var(--text)">${escapeHtml(name)}</strong><span style="font-size:.68rem;color:var(--muted)">~${dist}m</span>${bookLink}</div>`);

    layer.addLayer(marker);
    _tempMapLayers.push(marker);

    if (!_filmingMap.hasLayer(layer)) {
      _filmingMap.addLayer(layer);
      const btnId = type==="service"?"tourism":type;
      document.getElementById(`fmap-layer-${btnId}`)?.classList.add("active");
    }
  });
}
document.addEventListener("click",function(e){
  const btn=e.target.closest(".btn-osm-action");
  if(!btn)return;
  e.stopPropagation();
  const type=btn.getAttribute("data-type");
  const lat=parseFloat(btn.getAttribute("data-lat"));
  const lng=parseFloat(btn.getAttribute("data-lng"));
  if(isNaN(lat)||isNaN(lng))return;
  handleOSMAction(type,lat,lng);
});

async function handleOSMAction(type,lat,lng){
  if(!_filmingMap)return;
  if (type === "isochrone") {
  await drawIsochrone(lat, lng, "foot", 15);
  return;
}

  const layerMap={hotel:_filmingHotelLayer,restaurant:_filmingRestaurantLayer,transport:_filmingTransportLayer,service:_filmingTourismLayer};
  const labelMap={hotel:"hébergements",restaurant:"restaurants",transport:"transports",service:"services"};
  const colorMap={hotel:"#ffd700",restaurant:"#f06595",transport:"#74c0fc",service:"#4dabf7"};
  const iconMap={hotel:"fa-bed",restaurant:"fa-utensils",transport:"fa-train",service:"fa-info-circle"};

  const layer=layerMap[type];
  if(!layer)return;

  if(!_filmingMap.hasLayer(layer)){
    _filmingMap.addLayer(layer);
    document.getElementById(`fmap-layer-${type==="service"?"tourism":type}`)?.classList.add("active");
  }

  toast(`🔍 ${labelMap[type]||type} à proximité…`);
  const cacheKey=`poi_manual_${type}_${lat.toFixed(3)}_${lng.toFixed(3)}`;

  // Cache localStorage 24h
  try{
    const cached=localStorage.getItem(cacheKey);
    if(cached){const c=JSON.parse(cached);if(Date.now()-c.time<86400000){_applyManualPOIs(c.data,type,lat,lng,layer,colorMap[type],iconMap[type]);return;}}
  }catch(e){}

  try{
    const data=await safeFetch(`/api/poi?lat=${lat}&lng=${lng}&type=${type}`);
    if(!data.results||!data.results.length){toast("Rien trouvé à proximité.");return;}
    // Convertir format backend → format interne
    const elements=data.results.map(r=>({lat:r.lat,lon:r.lon,tags:{name:r.name},_poiType:r.type}));
    try{localStorage.setItem(cacheKey,JSON.stringify({time:Date.now(),data:elements}));}catch(e){}
    _applyManualPOIs(elements,type,lat,lng,layer,colorMap[type],iconMap[type]);
    const nearest=_findNearestFromNominatim(lat,lng,elements);
    if(nearest)toast(`📍 Plus proche : ${nearest.tags?.name||type} (~${nearest._dist}m)`,4000);
  }catch(e){toast("Erreur réseau. Réessayez.");}
}

function _applyManualPOIs(elements,type,lat,lng,layer,color,icn){
  layer.clearLayers();
  elements.forEach(el=>{
    if(!el.lat||!el.lon)return;
    const name=el.tags?.name||type;
    const dist=Math.round(_haversineM(lat,lng,el.lat,el.lon));
    const icon=L.divIcon({html:`<div style="background:#0d0d14;border:2px solid ${color};color:${color};width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.5)"><i class="fas ${icn}" style="font-size:10px"></i></div>`,className:"",iconSize:[26,26],iconAnchor:[13,13]});
    const marker=L.marker([el.lat,el.lon],{icon});
    let bookLink=type==="hotel"?`<a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(name)}&aid=Pelify" target="_blank" rel="sponsored noopener" class="fmap-popup-btn fmap-popup-booking" style="margin-top:5px;display:inline-flex;font-size:.62rem"><i class="fas fa-bed"></i> Booking</a>`:"";
    marker.bindPopup(`<div class="fmap-popup-small"><span style="font-size:.65rem;color:${color};text-transform:uppercase;font-weight:700">${type}</span><strong style="display:block;margin-top:2px;font-size:.85rem;color:var(--text)">${escapeHtml(name)}</strong><span style="font-size:.7rem;color:var(--muted)">~${dist}m</span>${bookLink}</div>`);
    layer.addLayer(marker);
  });
  _filmingMap.flyTo([lat,lng],15,{duration:0.8});
}

function _findNearestFromNominatim(lat,lng,elements){
  let best=null,bestDist=Infinity;
  elements.forEach(el=>{
    if(!el.lat||!el.lon)return;
    const d=_haversineM(lat,lng,el.lat,el.lon);
    if(d<bestDist){bestDist=d;best={...el,_dist:Math.round(d)};}
  });
  return best;
}

// ════ OVERPASS CACHE ════
async function fetchOverpassCached(query,cacheKey){
  try{const cacheStr=localStorage.getItem("ovp_"+cacheKey);if(cacheStr){const c=JSON.parse(cacheStr);if(Date.now()-c.time<86400000)return c.data;}}catch(e){}
  try{
    const response=await fetch("https://overpass-api.de/api/interpreter",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:`data=${encodeURIComponent(query)}`});
    if(response.status===429){toast("Overpass surchargé. Attendez 1 min.");return[];}
    if(!response.ok)throw new Error("Overpass HTTP "+response.status);
    const data=await response.json();
    if(data?.elements){const limited=data.elements.slice(0,30);try{localStorage.setItem("ovp_"+cacheKey,JSON.stringify({time:Date.now(),data:limited}));}catch(e){}return limited;}
  }catch(e){console.error("Erreur Overpass:",e);}
  return[];
}

// ════ ADD MARKER TO LAYER ════
function _addMarkerToLayer(el,type,layer){
  const lat=el.lat||el.center?.lat,lon=el.lon||el.center?.lon;
  if(!lat||!lon)return;
  const tags=el.tags||{};
  const name=tags.name||(type==="hotel"?"Hébergement":type==="restaurant"?"Restaurant":type==="transport"?"Transport":"Service");
  const colorMap={hotel:"#ffd700",restaurant:"#f06595",transport:"#74c0fc",service:"#4dabf7"};
  const iconMap={hotel:"fa-bed",restaurant:"fa-utensils",transport:"fa-train",service:"fa-info-circle"};
  const color=colorMap[type]||"#4dabf7",icon=iconMap[type]||"fa-circle";
  const customIcon=L.divIcon({html:`<div style="background:#1a1a2e;border:2px solid ${color};color:${color};width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.5);"><i class="fas ${icon}" style="font-size:10px"></i></div>`,className:"",iconSize:[26,26],iconAnchor:[13,13]});
  const marker=L.marker([lat,lon],{icon:customIcon});
  const phone=tags.phone?`<div style="margin-top:4px;font-size:.75rem"><i class="fas fa-phone"></i> <a href="tel:${tags.phone}" style="color:${color}">${tags.phone}</a></div>`:"";
  const website=tags.website?`<div style="margin-top:4px;font-size:.75rem"><i class="fas fa-globe"></i> <a href="${tags.website}" target="_blank" style="color:${color}">Site web</a></div>`:"";
  let bookLink="";
  if(type==="hotel"){const bookUrl=`https://www.booking.com/searchresults.html?ss=${encodeURIComponent(name)}&aid=Pelify`;bookLink=`<div style="margin-top:8px"><a href="${bookUrl}" target="_blank" rel="sponsored noopener" class="fmap-popup-btn fmap-popup-booking"><i class="fas fa-bed"></i> Réserver</a></div>`;}
  marker.bindPopup(`<div class="fmap-popup-small"><span style="font-size:.65rem;color:${color};text-transform:uppercase;font-weight:700">${type}</span><strong style="display:block;margin-top:2px;font-size:.85rem">${escapeHtml(name)}</strong>${phone}${website}${bookLink}</div>`);
  layer.addLayer(marker);
}

// ════ NEAREST POI ════
function _findNearest(lat,lng,elements){let best=null,bestDist=Infinity;elements.forEach(el=>{const elLat=el.lat||el.center?.lat,elLon=el.lon||el.center?.lon;if(!elLat||!elLon)return;const d=_haversineM(lat,lng,elLat,elLon);if(d<bestDist){bestDist=d;best={...el,_dist:Math.round(d)};}});return best;}
function _haversineM(lat1,lon1,lat2,lon2){const R=6371000;const dLat=(lat2-lat1)*Math.PI/180,dLon=(lon2-lon1)*Math.PI/180;const a=Math.sin(dLat/2)**2+Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));}

// ════ ISOCHRONE — Turf uniquement (pas de backend) ════
async function drawIsochrone(lat, lng, mode = "foot", minutes = 15) {
  if (!_filmingMap) return;

  _clearTempLayers();

  try {
    await ensureTurfReady();
  } catch (e) {
    toast("Impossible de charger Turf.js");
    return;
  }

  if (!window.turf) {
    toast("Turf.js non chargé");
    return;
  }

  const speedKmh = mode === "foot" ? 5 : 15;
  const distKm = speedKmh * (minutes / 60) * 0.85;

  const circle = turf.circle([lng, lat], distKm, {
    steps: 64,
    units: "kilometers"
  });

  _isochroneLayer = L.geoJSON(circle, {
    style: {
      color: "#00ffcc",
      weight: 2,
      dashArray: "6,4",
      fillColor: "#00ffcc",
      fillOpacity: 0.07
    }
  }).addTo(_filmingMap);

  const labelIcon = L.divIcon({
    html: `<div class="fmap-isochrone-label">🚶 ~${minutes} min</div>`,
    className: "",
    iconSize: [90, 24],
    iconAnchor: [45, 12]
  });

  const labelMarker = L.marker([lat, lng], {
    icon: labelIcon,
    interactive: false,
    zIndexOffset: -100
  }).addTo(_filmingMap);

  _tempMapLayers.push(labelMarker);

  toast(`⏱️ Zone ~${minutes} min à pied tracée`);
}

// ════ TOGGLE LAYERS ════
function toggleFilmingLayer(layerName){
  if(!_filmingMap)return;
  const btn=document.getElementById(`fmap-layer-${layerName}`);
  const layerMap={hotel:_filmingHotelLayer,tourism:_filmingTourismLayer,restaurant:_filmingRestaurantLayer,transport:_filmingTransportLayer};
  const target=layerMap[layerName];if(!target)return;
  if(_filmingMap.hasLayer(target)){_filmingMap.removeLayer(target);btn?.classList.remove("active");}
  else{_filmingMap.addLayer(target);btn?.classList.add("active");}
}
function toggleFilmingHeatmap(){
  if(!_filmingMap||!window.L?.heatLayer)return;
  const btn=document.getElementById("fmap-heatmap");
  if(_filmingHeatmapLayer&&_filmingMap.hasLayer(_filmingHeatmapLayer)){_filmingMap.removeLayer(_filmingHeatmapLayer);btn?.classList.remove("active");}
  else{const points=_filmingAllMarkers.map(m=>[m.lat,m.lng,0.5]);_filmingHeatmapLayer=L.heatLayer(points,{radius:35,blur:25,maxZoom:10,gradient:{0.2:"#ffe3b3",0.5:"#ff8c42",0.8:"#ff4444",1.0:"#cc0000"}}).addTo(_filmingMap);btn?.classList.add("active");}
}
function filmingNearMe(){
  if(!_filmingMap||!navigator.geolocation)return;
  navigator.geolocation.getCurrentPosition(pos=>{
    _filmingMap.flyTo([pos.coords.latitude,pos.coords.longitude],11,{duration:2});
    const pulseIcon=L.divIcon({html:`<div class="fmap-near-me-pulse"></div>`,className:"",iconSize:[24,24],iconAnchor:[12,12]});
    L.marker([pos.coords.latitude,pos.coords.longitude],{icon:pulseIcon}).addTo(_filmingMap).bindPopup(`📍 ${t("filming_you_are_here")}`).openPopup();
  },()=>toast(t("filming_geo_denied")),{timeout:5000});
}
function toggleFilmingMapFullscreen(){
  const wrap=document.getElementById("filming-map-wrap"),btn=document.getElementById("fmap-fullscreen");
  if(!wrap)return;
  if(wrap.classList.contains("fmap-fullscreen-mode")){wrap.classList.remove("fmap-fullscreen-mode");btn?.querySelector("i")?.setAttribute("class","fas fa-expand");}
  else{wrap.classList.add("fmap-fullscreen-mode");btn?.querySelector("i")?.setAttribute("class","fas fa-compress");}
  setTimeout(()=>_filmingMap?.invalidateSize(),300);
}

async function loadLayerData(type){
  // loadLayerData non utilisé — POI chargés via _autoLoadPOIsAround au clic sur "Voir lieux"
}

async function handleMapMove(){
  // handleMapMove désactivé — trop lourd, remplacé par chargement au clic
}

// ════════════════════════════════════════════════════════════════
// FIN FILMING
// ════════════════════════════════════════════════════════════════

// ════ NOT FOUND ════
function afficherNotFound(data){
  document.getElementById("page-film-detail").style.display="block";
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("hero").style.display="none";
  document.getElementById("back-label").innerText=t("back_home");
  ["fake_alert","detail_tags","detail_rating","cast_section","trailer_section","similar_section","seasons_section"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  document.getElementById("confidence_wrap").style.display="none";
  document.getElementById("food-partner").classList.remove("visible");
  document.getElementById("affiche_film").style.display="none";
  document.getElementById("titre_film").innerText=t("not_found_title");
  document.getElementById("synopsis_film").innerText=data.message||"";
  const titreHtml=data.titre_gemini?`<p style="color:var(--muted);font-size:.85rem;margin-bottom:16px;">Titre potentiel IA : <strong style="color:var(--text)">${data.titre_gemini}</strong></p>`:"";
 document.getElementById("streaming_section").innerHTML = `
  ${titreHtml}
  <h3 style="margin-bottom:12px">
    <i class="fas fa-search"></i> ${t("searching")}
  </h3>
  <div class="streaming-buttons" style="margin-top:10px;">
    ${data.search_youtube ? `
      <a href="${data.search_youtube}" target="_blank" rel="noopener" class="btn-stream">
        <i class="fab fa-youtube"></i> YouTube
      </a>` : ""}
    
  </div>
`;
  window.scrollTo({top:0,behavior:"smooth"});
}

// ════ DÉTAILS ════
async function afficherDetails(movieId, mediaType="movie", pushHistory=true){
  if (pushHistory) _pushNav(`/film/${movieId}`, {type:"detail", id:movieId, mediaType});
  if(currentMovieId&&currentMovieId!==movieId)navStack.push({id:currentMovieId,type:currentMediaType});
 
  currentMovieId=movieId;currentMediaType=mediaType;cacherErreur();
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("filming-page").style.display="none";
  showDetailLoading();
  try{
    const data=await safeFetch(`/movie/${movieId}?lang=${getTMDBLang()}&type=${mediaType}`);
    if(data.status==="error"){afficherErreur(data.message||t("err_generic"));document.getElementById("page-film-detail").style.display="none";if(lastGrid)document.getElementById("genre-grid").style.display="block";return;}
    const region=getRegionCode();
    const providers=data["watch/providers"]?.results?.[region]?.flatrate||[];
    const similar=data.similar?.results?.slice(0,6)||[];
    const cast=data.credits?.cast?.slice(0,8)||[];
    const trailerD=data.videos?.results?.find(v=>v.type==="Trailer")||data.videos?.results?.find(v=>["Teaser","Clip"].includes(v.type));
    const trailerUrl=trailerD?.site==="YouTube"?`https://www.youtube.com/watch?v=${trailerD.key}`:"";
    const genres=data.genres?.map(g=>g.name)||[];
    const year=(data.release_date||data.first_air_date||"").split("-")[0];
    const isTv=mediaType==="tv"||!!data.first_air_date;
    afficherDetailFilm({status:"success",title:data.title||data.name||"Inconnu",synopsis:data.overview||"",image:data.poster_path?`https://image.tmdb.org/t/p/w500${data.poster_path}`:"",streaming:providers.map(p=>p.provider_name),streaming_logos:providers.map(p=>({name:p.provider_name,logo_path:p.logo_path})),similar,cast,trailer:trailerUrl,confidence:null,is_fake:false,vote_average:data.vote_average,vote_count:data.vote_count,runtime:data.runtime||data.episode_run_time?.[0],genres,year,tmdb_id:movieId,is_series:isTv,seasons:isTv?(data.seasons||[]):null});
  }catch(e){afficherErreur(t("err_generic"));document.getElementById("page-film-detail").style.display="none";if(lastGrid)document.getElementById("genre-grid").style.display="block";}
}
function showDetailLoading(){
  document.getElementById("page-film-detail").style.display="block";
  document.getElementById("titre_film").innerText="…";
  document.getElementById("affiche_film").src="";
  ["synopsis_film","detail_tags","detail_rating","streaming_section","cast_section","trailer_section","similar_section","seasons_section","fake_alert"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  ["crew_section","locations_section","finance_section","eidr_badge"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  document.getElementById("confidence_wrap").style.display="none";
  document.getElementById("food-partner").classList.remove("visible");
}
function afficherDetailFilm(data) {
  document.getElementById("page-film-detail").style.display = "block";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("hero").style.display = "none";
  document.getElementById("back-label").innerText = lastGrid ? t("back_list") : t("back_home");

  // Fake / low confidence
  document.getElementById("fake_alert").innerHTML =
    data._lowConfWarning
      ? `<div class="fake-alert"><i class="fas fa-exclamation-triangle"></i> Résultat incertain — (${Math.round(data.confidence)}% de confiance). Vérifiez manuellement si besoin.</div>`
      : data.is_fake
      ? `<div class="fake-alert"><i class="fas fa-exclamation-triangle"></i> Contenu humoristique possible.</div>`
      : "";

  document.getElementById("titre_film").innerText = data.title || "Inconnu";

  // Affiche
  const imgEl = document.getElementById("affiche_film");
  if (data.image) {
    imgEl.src = data.image;
    imgEl.style.display = "block";
  } else {
    imgEl.style.display = "none";
  }

  // Tags
  const tagsEl = document.getElementById("detail_tags");
  tagsEl.innerHTML = "";
  if (data.is_series) tagsEl.innerHTML += `<span class="tag series"><i class="fas fa-tv"></i> ${t("series_tag")}</span>`;
  if (data.year) tagsEl.innerHTML += `<span class="tag year"><i class="fas fa-calendar"></i> ${data.year}</span>`;
  if (data.runtime) tagsEl.innerHTML += `<span class="tag"><i class="fas fa-clock"></i> ${data.runtime} min</span>`;
  (data.genres || []).forEach(g => tagsEl.innerHTML += `<span class="tag genre">${g}</span>`);

  // Confiance
  const confWrap = document.getElementById("confidence_wrap");
  if (data.confidence !== null && data.confidence !== undefined) {
    const pct = Math.round(data.confidence);
    const color = pct >= 70 ? "#00ffcc" : pct >= 40 ? "#ffd700" : "#ff4444";
    const lbl = pct >= 70 ? (currentLang.startsWith("en") ? "High confidence" : "Confiance élevée")
                 : pct >= 40 ? (currentLang.startsWith("en") ? "Medium confidence" : "Confiance moyenne")
                 : (currentLang.startsWith("en") ? "Low confidence" : "Confiance faible");
    confWrap.style.display = "block";
    document.getElementById("conf-bar-inner").style.width = pct + "%";
    document.getElementById("conf-bar-inner").style.background = color;
    document.getElementById("conf-pct-label").textContent = pct + "% — " + lbl;
    document.getElementById("conf-pct-label").style.color = color;
  } else {
    confWrap.style.display = "none";
  }

  // Note
  const ratingEl = document.getElementById("detail_rating");
  ratingEl.innerHTML = data.vote_average
    ? `<i class="fas fa-star" style="color:var(--gold)"></i> ${parseFloat(data.vote_average).toFixed(1)}<small> / 10 · ${data.vote_count ? data.vote_count.toLocaleString() + " votes" : ""}</small>`
    : "";

  // Synopsis
  const synEl = document.getElementById("synopsis_film");
  if (data.scene_description) {
    synEl.innerHTML = `
      <div style="background:rgba(0,255,204,.06);border-left:3px solid var(--primary);padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:14px;font-size:.82rem;color:var(--muted)">
        <span style="color:var(--primary);font-weight:600;font-size:.73rem;text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:6px">
          <i class="fas fa-film"></i> ${t("scene_identified")}
        </span>
        ${data.scene_description}
      </div>
      <span style="font-size:.73rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:8px">Synopsis</span>
      ${data.synopsis || t("no_synopsis")}
    `;
  } else {
    synEl.textContent = data.synopsis || t("no_synopsis");
  }

  // ─── PARTNER (popcorn) ──────────────────────────────
  const foodPartner = document.getElementById("food-partner");
  if (foodPartner) {
    foodPartner.classList.add("visible");
    const foodBtn = foodPartner.querySelector("a.btn-stream, a.food-btn, a");
    if (foodBtn) {
      foodBtn.href = getFoodLink(currentLang);
      foodBtn.target = "_blank";
      foodBtn.rel = "sponsored noopener";
    }
  }

 // ─── STREAMING ──────────────────────────────────────────────
const streamEl = document.getElementById("streaming_section");
const providers = data.streaming_logos || []; // [{name, logo_path}]

if (providers.length > 0) {
  const logos = providers.map(p => {
    const name = p.name || '';
    const logoUrl = p.logo_path ? `https://image.tmdb.org/t/p/w92${p.logo_path}` : '';
    
    // Construire l'URL de recherche pour chaque plateforme
   let link = '#';
const searchTitle = encodeURIComponent(data.title || '');

// Normaliser le nom pour matcher les variantes Amazon
const isAmazon = name.toLowerCase().includes('amazon') || name.toLowerCase().includes('prime video');

if (isAmazon) {
  link = getAmazonSearch(data.title);
} else if (STREAMING_LINKS[name]) {
  link = STREAMING_LINKS[name] + searchTitle;
} else {
  link = `https://www.youtube.com/results?search_query=${searchTitle}+${encodeURIComponent(name)}`;
}
    
    return `<a href="${link}" target="_blank" rel="sponsored noopener" class="streaming-badge" title="${name}">
      ${logoUrl ? `<img src="${logoUrl}" alt="${name}" loading="lazy">` : name}
    </a>`;
  }).join('');

  streamEl.innerHTML = `
    <h3><i class="fas fa-satellite-dish"></i> ${t("streaming_title")}</h3>
    <div class="streaming-badges">${logos}</div>
  `;
} else {
  // Pas de provider dans la région → fallback Amazon
  const region = getRegionCode();
  streamEl.innerHTML = `
    <h3><i class="fas fa-satellite-dish"></i> ${t("streaming_title")}</h3>
    <p style="color:var(--muted);font-size:.85rem">
      ${t("no_streaming_country")} (région ${region})
    </p>
    <div class="streaming-buttons" style="margin-top:8px">
      <a href="${getAmazonSearch(data.title)}" target="_blank" rel="sponsored noopener" class="btn-stream affiliate" style="border-color:#00a8e040">
        <i class="fas fa-search" style="color:#00a8e0"></i> Amazon Prime
      </a>
    </div>
  `;
}

  // ─── SAISONS ──────────────────────────────────────────
  const seasonsEl = document.getElementById("seasons_section");
  if (data.is_series && data.seasons && data.seasons.length > 0) {
    const seasons = data.seasons.filter(s => s.season_number > 0 || s.episode_count > 0);
    const seasonCards = seasons.map(s => {
      const poster = s.poster_path ? `https://image.tmdb.org/t/p/w154${s.poster_path}` : "";
      const airYear = s.air_date ? s.air_date.split("-")[0] : "";
      const posterHtml = poster
        ? `<img class="season-poster" src="${poster}" alt="${s.name || ""}" loading="lazy">`
        : `<div style="width:48px;height:72px;background:var(--card2);border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:1.2rem">🎬</div>`;
      return `<div class="season-card" id="season-${s.season_number}">
        <div class="season-header" onclick="toggleSaison(${data.tmdb_id},${s.season_number})">
          ${posterHtml}
          <div class="season-info">
            <div class="season-name">${s.name || t("seasons_title") + " " + s.season_number}</div>
            <div class="season-meta">${s.episode_count || 0} ${t("episodes_title")}${airYear ? " · " + airYear : ""}</div>
          </div>
          <i class="fas fa-chevron-down season-chevron"></i>
        </div>
        <div class="episodes-list" id="episodes-${s.season_number}">
          <div class="episodes-loading"><i class="fas fa-circle-notch fa-spin"></i> ${t("loading_episodes")}</div>
        </div>
      </div>`;
    }).join("");
    seasonsEl.innerHTML = `<h3><i class="fas fa-layer-group"></i> ${t("seasons_title")}</h3>${seasonCards}`;
  } else {
    seasonsEl.innerHTML = "";
  }

  // ─── CAST ──────────────────────────────────────────────
  const castEl = document.getElementById("cast_section");
  if ((data.cast || []).length > 0) {
    const items = data.cast.map(c => {
      const photo = c.profile_path
        ? `https://image.tmdb.org/t/p/w185${c.profile_path}`
        : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Crect width='60' height='60' fill='%231a1a24' rx='30'/%3E%3Ctext x='50%25' y='50%25' fill='%23555' font-size='24' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%91%A4%3C/text%3E%3C/svg%3E";
      return `<div class="cast-card">
        <img src="${photo}" alt="${c.name}" loading="lazy">
        <p>${c.name}${c.character ? `<br><span style="color:var(--primary);font-size:.58rem">${c.character}</span>` : ""}</p>
      </div>`;
    }).join("");
    castEl.innerHTML = `<h3><i class="fas fa-users"></i> ${t("cast_title")}</h3><div class="cast-list">${items}</div>`;
  } else {
    castEl.innerHTML = "";
  }

  // ─── TRAILER ────────────────────────────────────────────
  const trailerEl = document.getElementById("trailer_section");
  if (data.trailer) {
    const embedUrl = data.trailer.replace("watch?v=", "embed/").replace("youtu.be/", "www.youtube.com/embed/");
    trailerEl.innerHTML = `
      <h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3>
      <button class="btn-trailer" onclick="afficherTrailer(this,'${embedUrl}')">
        <i class="fas fa-play"></i> ${t("see_trailer")}
      </button>
      <iframe id="trailer_iframe" allowfullscreen style="display:none;width:100%;aspect-ratio:16/9;border-radius:12px;border:none;margin-top:10px;"></iframe>
    `;
  } else {
    const q = encodeURIComponent((data.title || "") + " trailer");
    trailerEl.innerHTML = `
      <h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3>
      <a href="https://www.youtube.com/results?search_query=${q}" target="_blank" rel="noopener" class="btn-trailer">
        <i class="fas fa-search"></i> ${t("search_trailer")}
      </a>
    `;
  }

  // ─── SIMILAR ────────────────────────────────────────────
  const similarEl = document.getElementById("similar_section");
  const similarList = data.similar || [];
  if (similarList.length > 0) {
    const cards = similarList.map(s => {
      const poster = s.poster_path
        ? `https://image.tmdb.org/t/p/w200${s.poster_path}`
        : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300' fill='%231a1a24'%3E%3Crect width='200' height='300'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='28' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
      const isTv = s.media_type === "tv" || !!s.first_air_date;
      return `<div class="movie-card" onclick="afficherDetails(${s.id},'${isTv ? "tv" : "movie"}')" style="cursor:pointer">
        <img src="${poster}" alt="${s.title || s.name || "?"}" loading="lazy" style="aspect-ratio:2/3;object-fit:cover">
        <div class="card-body"><h4>${s.title || s.name || "?"}</h4></div>
      </div>`;
    }).join("");
    similarEl.innerHTML = `<h3>${t("similar_title")}</h3><div id="similar_cards">${cards}</div>`;
  } else {
    similarEl.innerHTML = "";
  }

  // ─── WIKIDATA ENRICHMENT ──────────────────────────────
  if (data.tmdb_id) chargerEnrichissementWikidata(data.tmdb_id, data.media_type || "movie");

  window.scrollTo({ top: 0, behavior: "smooth" });
}
function afficherTrailer(btn,embedUrl){const iframe=document.getElementById("trailer_iframe");if(iframe){iframe.src=embedUrl;iframe.style.display="block";btn.style.display="none";}}

// ════ SAISONS ════
const _loadedSeasons={};
async function toggleSaison(seriesId,seasonNumber){
  const card=document.getElementById(`season-${seasonNumber}`);if(!card)return;
  const episodesList=document.getElementById(`episodes-${seasonNumber}`);
  if(card.classList.contains("open")){card.classList.remove("open");return;}
  card.classList.add("open");
  if(_loadedSeasons[`${seriesId}-${seasonNumber}`])return;
  try{
    const data=await safeFetch(`/tv/${seriesId}/season/${seasonNumber}?lang=${getTMDBLang()}`);
    _loadedSeasons[`${seriesId}-${seasonNumber}`]=true;const episodes=data.episodes||[];
    if(episodes.length===0){episodesList.innerHTML=`<p style="padding:16px;color:var(--muted);font-size:.82rem;text-align:center">${t("no_synopsis")}</p>`;return;}
    episodesList.innerHTML=episodes.map(ep=>{const still=ep.still_path?`https://image.tmdb.org/t/p/w185${ep.still_path}`:"";const airDate=ep.air_date?ep.air_date.split("-").reverse().join("/"):"";const stillHtml=still?`<img class="episode-still" src="${still}" alt="" loading="lazy">`:"";return `<div class="episode-item"><div class="episode-num">${ep.episode_number}</div>${stillHtml}<div class="episode-body"><div class="episode-title">${ep.name||"Episode "+ep.episode_number}</div>${airDate?`<div class="episode-date">${airDate}</div>`:""}${ep.overview?`<div class="episode-overview">${ep.overview}</div>`:""}</div></div>`;}).join("");
  }catch(e){episodesList.innerHTML=`<p style="padding:16px;color:var(--muted);font-size:.82rem;text-align:center"><i class="fas fa-exclamation-circle"></i> Erreur chargement épisodes</p>`;}
}

// ════ PUBLICITÉ ════
let _adFinished=false,_analysisResult=null,_analysisCallback=null,_adCountdownInterval=null;
function demarrerPub(){
  const modal=document.getElementById('ad-modal'),closeBtn=document.getElementById('ad-close-btn'),countdown=document.getElementById('ad-countdown');
  if(!modal)return;
  _adFinished=false;modal.style.display='flex';closeBtn.disabled=true;closeBtn.style.background='rgba(255,255,255,0.1)';closeBtn.style.color='var(--text)';
  let seconds=5;countdown.textContent=seconds;
  _adCountdownInterval=setInterval(()=>{seconds--;countdown.textContent=seconds;if(seconds<=0){clearInterval(_adCountdownInterval);closeBtn.disabled=false;countdown.textContent='✕';closeBtn.style.background='rgba(0,255,204,0.2)';closeBtn.style.color='var(--primary)';_publicitéTerminée();}},1000);
}
function fermerPub(){const closeBtn=document.getElementById('ad-close-btn');if(closeBtn&&closeBtn.disabled)return;clearInterval(_adCountdownInterval);_publicitéTerminée();}
function _publicitéTerminée(){_adFinished=true;const modal=document.getElementById('ad-modal');if(modal)modal.style.display='none';if(_analysisResult!==null){_afficherResultatFinal(_analysisResult);_analysisResult=null;}}
function _afficherResultatFinal(data){
  if(!_adFinished){_analysisResult=data;return;}
  const overlay=document.getElementById("loading-overlay"),progressBar=document.getElementById("prog-fill"),percentLabel=document.getElementById("prog-percent");
  if(progressBar)progressBar.style.width="100%";if(percentLabel)percentLabel.textContent="100%";
  setTimeout(()=>overlay.classList.remove("active"),300);stopGame();
  if(data.status==="success"||data.status==="cached"){navStack=[];lastGrid=null;currentMovieId=data.tmdb_id;currentMediaType=data.media_type||"movie";afficherDetailFilm(data);}
  else if(data.status==="not_found")afficherNotFound(data);
  else afficherErreurRiche(data);
}

// ════ CONFIDENTIALITÉ ════
function afficherPrivacy(){document.getElementById("hero").style.display="none";document.getElementById("genre-nav").style.display="none";document.getElementById("genre-grid").style.display="none";document.getElementById("page-film-detail").style.display="none";document.getElementById("filming-page").style.display="none";document.getElementById("privacy-page").style.display="block";window.scrollTo({top:0,behavior:"smooth"});}
function cacherPrivacy(){document.getElementById("privacy-page").style.display="none";retourAccueil();}

// ════ WIKIDATA ENRICHMENT ════
async function chargerEnrichissementWikidata(tmdb_id,media_type="movie"){
  const sections={crew:document.getElementById("crew_section"),locations:document.getElementById("locations_section"),finance:document.getElementById("finance_section"),eidr:document.getElementById("eidr_badge")};
  if(sections.crew)sections.crew.innerHTML=`<div class="wd-loading"><i class="fas fa-circle-notch fa-spin"></i><span style="color:var(--muted);font-size:.82rem">Chargement équipe créative…</span></div>`;
  try{
    const[wdData,locData]=await Promise.allSettled([safeFetch(`/movie/${tmdb_id}/wikidata?type=${media_type}`),safeFetch(`/movie/${tmdb_id}/locations?type=${media_type}`)]);
    const wd=wdData.status==="fulfilled"?wdData.value:null;const loc=locData.status==="fulfilled"?locData.value:null;
    if(sections.crew)afficherCrewWikidata(sections.crew,wd);
    if(sections.locations)afficherLocationsWikidata(sections.locations,loc?.locations||[],wd?.locations||[]);
    if(sections.finance)afficherFinanceWikidata(sections.finance,wd);
    if(sections.eidr&&wd?.eidr_id){sections.eidr.innerHTML=`<span class="eidr-badge" title="Identifiant EIDR standard industrie audiovisuelle"><i class="fas fa-fingerprint"></i>EIDR <code>${wd.eidr_id}</code></span>`;sections.eidr.style.display="flex";}
  }catch(e){console.warn("Wikidata enrichment KO:",e);if(sections.crew)sections.crew.innerHTML="";}
}
function afficherCrewWikidata(container,wd){
  if(!wd||wd.status==="error"){container.innerHTML="";return;}
  const crew=wd.crew||{};const castWd=wd.cast_wd||[];const rows=[];
  const addRow=(icon,label,items)=>{if(!items||items.length===0)return;const links=items.map(name=>`<span class="crew-name">${escapeHtml(name)}</span>`).join(", ");rows.push(`<div class="crew-row"><span class="crew-label"><i class="${icon}"></i> ${label}</span><span class="crew-value">${links}</span></div>`);};
  addRow("fas fa-video",crewLabel("directors"),crew.directors);addRow("fas fa-pen-nib",crewLabel("screenwriters"),crew.screenwriters);addRow("fas fa-camera",crewLabel("cinematographers"),crew.cinematographers);addRow("fas fa-cut",crewLabel("editors"),crew.editors);addRow("fas fa-music",crewLabel("composers"),crew.composers);addRow("fas fa-briefcase",crewLabel("producers"),crew.producers);addRow("fas fa-truck",crewLabel("distributors"),crew.distributors);
  if(castWd.length>0){const castHtml=castWd.slice(0,6).map(c=>`<span class="crew-name">${escapeHtml(c.name)}${c.character?` <em style="color:var(--muted);font-size:.75em">— ${escapeHtml(c.character)}</em>`:""}</span>`).join(", ");rows.push(`<div class="crew-row"><span class="crew-label"><i class="fas fa-users"></i> ${crewLabel("cast")}</span><span class="crew-value">${castHtml}</span></div>`);}
  if(rows.length===0){container.innerHTML="";return;}
  const companies=(wd.companies||[]).map(c=>escapeHtml(c.name)).join(" · ");
  container.innerHTML=`<div class="crew-section-inner"><h3><i class="fas fa-id-card"></i> ${crewLabel("title")}</h3>${companies?`<p class="prod-co"><i class="fas fa-building"></i> ${companies}</p>`:""}<div class="crew-grid">${rows.join("")}</div><p class="wd-source"><i class="fab fa-wikipedia-w"></i> ${crewLabel("source")} ${wd.wikidata_id?`<a href="https://www.wikidata.org/wiki/${wd.wikidata_id}" target="_blank" rel="noopener">${wd.wikidata_id}</a>`:""}</p></div>`;
}
function afficherLocationsWikidata(container,locations){
  const allLocs=[...locations];if(allLocs.length===0){container.innerHTML="";return;}
  const withGPS=allLocs.filter(l=>l.lat!==null&&l.lat!==undefined);
  const locItems=allLocs.map(loc=>{const hasCoord=loc.lat!==null&&loc.lat!==undefined;const mapsUrl=hasCoord?`https://www.google.com/maps?q=${loc.lat},${loc.lng}`:`https://www.google.com/maps/search/${encodeURIComponent(loc.name)}`;const wdUrl=loc.wikidata_id?`https://www.wikidata.org/wiki/${loc.wikidata_id}`:null;return `<div class="location-chip"><a href="${mapsUrl}" target="_blank" rel="noopener" class="loc-maps-link" title="Voir sur Google Maps"><i class="fas fa-map-marker-alt" style="color:var(--primary)"></i> ${escapeHtml(loc.name)}${hasCoord?'<i class="fas fa-external-link-alt" style="font-size:.6rem;opacity:.5"></i>':""}</a>${wdUrl?`<a href="${wdUrl}" target="_blank" rel="noopener" class="loc-wd-link" title="Wikidata"><i class="fab fa-wikipedia-w"></i></a>`:""}</div>`;}).join("");
  let mapHtml="";if(withGPS.length>0)mapHtml=`<div id="filming-map" class="filming-map-container" style="height:220px;border-radius:12px;overflow:hidden;margin-bottom:16px;border:1px solid var(--border)"><div id="filming-map-inner" style="width:100%;height:100%"></div></div>`;
  container.innerHTML=`<div class="locations-section-inner"><h3><i class="fas fa-map-marked-alt"></i> ${locLabel("title")} <span class="loc-count">${allLocs.length}</span></h3>${mapHtml}<div class="location-chips">${locItems}</div>${withGPS.length>0?`<p class="loc-affiliate"><i class="fas fa-bed"></i><a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(withGPS[0].name)}&aid=Pelify" target="_blank" rel="sponsored noopener" class="loc-booking-link">Trouver un hôtel près du lieu de tournage →</a></p>`:""}<p class="wd-source"><i class="fab fa-wikipedia-w"></i> ${locLabel("source")}</p></div>`;
  if(withGPS.length>0&&typeof L!=="undefined")initFilmingMap(withGPS);
  else if(withGPS.length>0)_ensureLeafletFull(()=>initFilmingMap(withGPS));
}


function initFilmingMap(locations) {
  try {
    const mapEl = document.getElementById("filming-map-inner");
    if (!mapEl || !window.L) {
      console.warn("Leaflet ou conteneur manquant");
      return;
    }

    // Nettoyer l'ancienne carte
    if (window._filmingMapDetail) {
      window._filmingMapDetail.remove();
      window._filmingMapDetail = null;
    }

    // Créer la carte
    const center = [locations[0].lat, locations[0].lng];
    const map = L.map(mapEl, { zoomControl: true, scrollWheelZoom: false });
    window._filmingMapDetail = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(map);

    // Vérifier que le plugin markerCluster est disponible
    const clusterGroup = (window.L.markerClusterGroup)
      ? L.markerClusterGroup({
          maxClusterRadius: 60,
          showCoverageOnHover: false,
          iconCreateFunction: function(cluster) {
            const count = cluster.getChildCount();
            const size = count > 100 ? 50 : count > 30 ? 40 : 32;
            return L.divIcon({
              html: `<div class="fmap-cluster" style="width:${size}px;height:${size}px;border-radius:50%;background:rgba(0,255,204,0.2);border:2px solid #00ffcc;color:#00ffcc;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:${size>40?'14px':'12px'}">${count}</div>`,
              className: '',
              iconSize: [size, size],
              iconAnchor: [size/2, size/2]
            });
          }
        })
      : L.layerGroup(); // fallback si cluster non disponible

    const icon = L.divIcon({
      className: '',
      html: `<div style="background:var(--primary,#00ffcc);width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #000;box-shadow:0 2px 8px rgba(0,255,204,.4)"></div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 28]
    });

    const points = locations.map(loc => [loc.lat, loc.lng]);
    const firstPoint = points[0];
    const bounds = [];

    locations.forEach((loc, index) => {
      const marker = L.marker([loc.lat, loc.lng], { icon }).addTo(clusterGroup);
      
      let distanceText = '';
      if (index > 0 && window.turf) {
        const from = turf.point(firstPoint);
        const to = turf.point([loc.lng, loc.lat]);
        const distance = turf.distance(from, to, { units: 'kilometers' });
        distanceText = ` <span style="font-size:0.7rem;color:var(--muted)">(${distance.toFixed(1)} km depuis le premier lieu)</span>`;
      }

      marker.bindPopup(`
        <strong>${loc.name}</strong>
        ${distanceText}
        <br>
        <a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(loc.name)}&aid=Pelify" target="_blank" style="color:#00ffcc;font-size:.8rem">🛏 Hôtels →</a> · 
        <a href="https://www.expedia.com/search?q=${encodeURIComponent(loc.name)}" target="_blank" style="color:#00ffcc;font-size:.8rem">🏨 Expedia →</a> · 
        <a href="https://www.airbnb.com/s/${encodeURIComponent(loc.name)}" target="_blank" style="color:#00ffcc;font-size:.8rem">🏡 Airbnb →</a> · 
        <a href="https://www.google.com/maps?q=${loc.lat},${loc.lng}" target="_blank" style="color:#00ffcc;font-size:.8rem">🗺 Maps →</a>
      `);

      bounds.push([loc.lat, loc.lng]);
    });

    map.addLayer(clusterGroup);

    if (bounds.length === 1) {
      map.setView(center, 12);
    } else {
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    if (points.length > 1 && window.L.polyline) {
      const line = L.polyline(points, {
        color: '#00ffcc',
        weight: 2,
        opacity: 0.5,
        dashArray: '6,8'
      }).addTo(map);
    }

    // 🔥 FORCER L'AFFICHAGE – Invalider la taille après un court délai
    setTimeout(() => {
      map.invalidateSize();
    }, 250);

  } catch (e) {
    console.warn("Leaflet map KO:", e);
  }
}
function afficherFinanceWikidata(container,wd){
  if(!wd||(!wd.budget_usd&&!wd.box_office_usd)){container.innerHTML="";return;}
  const fmt=n=>n?"$"+(n>=1e9?(n/1e9).toFixed(2)+" Md":n>=1e6?Math.round(n/1e6)+" M":n.toLocaleString()):null;
  const budget=fmt(wd.budget_usd),bo=fmt(wd.box_office_usd),roi=(wd.budget_usd&&wd.box_office_usd)?((wd.box_office_usd/wd.budget_usd)*100).toFixed(0)+"% ROI":null;
  container.innerHTML=`<div class="finance-section-inner"><h3><i class="fas fa-chart-line"></i> ${finLabel("title")}</h3><div class="finance-grid">${budget?`<div class="finance-card"><span class="finance-label">${finLabel("budget")}</span><span class="finance-value">${budget}</span></div>`:""}${bo?`<div class="finance-card success"><span class="finance-label">${finLabel("box_office")}</span><span class="finance-value">${bo}</span></div>`:""}${roi?`<div class="finance-card"><span class="finance-label">ROI</span><span class="finance-value">${roi}</span></div>`:""}</div><p class="wd-source"><i class="fab fa-wikipedia-w"></i> ${finLabel("source")}</p></div>`;
}

// ════ I18N WIKIDATA ════
const wdI18n={
  fr:{crew:{title:"Équipe créative",directors:"Réalisation",screenwriters:"Scénario",cinematographers:"Chef opérateur",editors:"Montage",composers:"Musique",producers:"Production",distributors:"Distribution",cast:"Acteurs",source:"Source Wikidata ·"},loc:{title:"Lieux de tournage",source:"Source Wikidata WikiProject Filming Locations"},fin:{title:"Chiffres clés",budget:"Budget",box_office:"Box-office mondial",source:"Source Wikidata"}},
  "en-US":{crew:{title:"Creative Team",directors:"Director(s)",screenwriters:"Screenplay",cinematographers:"Cinematography",editors:"Film Editing",composers:"Music",producers:"Produced by",distributors:"Distribution",cast:"Cast",source:"Source Wikidata ·"},loc:{title:"Filming Locations",source:"Source Wikidata WikiProject Filming Locations"},fin:{title:"Key Numbers",budget:"Budget",box_office:"Worldwide Box Office",source:"Source Wikidata"}},
  "en-GB":{crew:{title:"Creative Team",directors:"Director(s)",screenwriters:"Screenplay",cinematographers:"Cinematography",editors:"Film Editing",composers:"Music",producers:"Produced by",distributors:"Distribution",cast:"Cast",source:"Source Wikidata ·"},loc:{title:"Filming Locations",source:"Source Wikidata WikiProject Filming Locations"},fin:{title:"Key Numbers",budget:"Budget",box_office:"Worldwide Box Office",source:"Source Wikidata"}},
  es:{crew:{title:"Equipo creativo",directors:"Dirección",screenwriters:"Guión",cinematographers:"Fotografía",editors:"Montaje",composers:"Música",producers:"Producción",distributors:"Distribución",cast:"Reparto",source:"Fuente Wikidata ·"},loc:{title:"Lugares de rodaje",source:"Fuente Wikidata"},fin:{title:"Cifras clave",budget:"Presupuesto",box_office:"Recaudación mundial",source:"Fuente Wikidata"}},
  de:{crew:{title:"Filmteam",directors:"Regie",screenwriters:"Drehbuch",cinematographers:"Kamera",editors:"Schnitt",composers:"Musik",producers:"Produktion",distributors:"Verleih",cast:"Besetzung",source:"Quelle Wikidata ·"},loc:{title:"Drehorte",source:"Quelle Wikidata"},fin:{title:"Zahlen & Fakten",budget:"Budget",box_office:"Weltweites Einspielergebnis",source:"Quelle Wikidata"}},
  zh:{crew:{title:"创作团队",directors:"导演",screenwriters:"编剧",cinematographers:"摄影",editors:"剪辑",composers:"音乐",producers:"制片",distributors:"发行",cast:"演员",source:"来源 Wikidata ·"},loc:{title:"拍摄地点",source:"来源 Wikidata"},fin:{title:"关键数据",budget:"预算",box_office:"全球票房",source:"来源 Wikidata"}}
};
function _getWdI18n(lang){return wdI18n[lang]||wdI18n["en-US"];}
function crewLabel(key){return _getWdI18n(currentLang).crew[key]||key;}
function locLabel(key){return _getWdI18n(currentLang).loc[key]||key;}
function finLabel(key){return _getWdI18n(currentLang).fin[key]||key;}

// ════ UTILITAIRE ════
function escapeHtml(str){if(!str)return"";return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");}

// ════ INIT ════
window.addEventListener("scroll",()=>{document.getElementById("back-top")?.classList.toggle("visible",window.scrollY>400);});


function routerInit(){
  const p = decodeURIComponent(location.pathname);
  let m;

  if (p === "/genre/films") { chargerFilms(); return true; }

  if ((m = p.match(/^\/genre\/([^\/]+)/)))      { chargerGenre(m[1]); return true; }
  if ((m = p.match(/^\/plateforme\/([^\/]+)/))) { chargerParPlateforme(m[1]); return true; }
  if ((m = p.match(/^\/film\/(\d+)/)))          { afficherDetails(parseInt(m[1]),"movie"); return true; }
  if (p === "/series")                          { chargerSeries(); return true; }
  if (p === "/lieux-de-tournage")               { chargerLieuxDeTournage(); return true; }

  return false;
}




window.onload=()=>{
  initLang();
 if (!routerInit()) {
  setHomeMode();
  document.getElementById("hero").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("page-film-detail").style.display = "none";
}
  document.addEventListener("keydown",e=>{if(e.code==="Space"&&document.getElementById("loading-overlay")?.classList.contains("active")){e.preventDefault();gameJump();}});

  const gc=document.getElementById("game-canvas");
  if(gc){
    gc.addEventListener("touchstart",e=>{e.preventDefault();gameJump();},{passive:false});
    if(!gc.querySelector(".game-ground")){
      gc.innerHTML=`
        <div class="game-star" style="top:20px;left:15%"></div>
        <div class="game-star" style="top:40px;left:35%"></div>
        <div class="game-star" style="top:15px;left:55%"></div>
        <div class="game-star" style="top:50px;left:70%"></div>
        <div class="game-star" style="top:28px;left:85%"></div>
        <div class="game-cloud" style="width:60px;height:16px;top:28px;left:120%;animation-duration:9s"></div>
        <div class="game-cloud" style="width:38px;height:12px;top:48px;left:140%;animation-duration:13s;animation-delay:-5s"></div>
        <div class="game-cloud" style="width:80px;height:18px;top:16px;left:160%;animation-duration:11s;animation-delay:-3s"></div>
        <div class="game-ground"></div>
        <div class="game-score-display" id="game-score">0</div>
        <div class="game-lives" id="game-lives">❤️❤️❤️</div>
        <div class="game-level-display" id="game-level">LVL 1</div>
        <div id="game-hero" style="left:60px">🥷</div>
        <div class="game-tap-hint" id="game-hint">${typeof t==="function"?t("game_hint"):"Tap to jump"}</div>`;
    }
  }

  if(!localStorage.getItem("cookies_accepted")){
    setTimeout(()=>{document.getElementById("cookie-consent").style.display="flex";},2000);
  }
};
// ════ HISTORY ROUTER ════
function _pushNav(path, state) {
  if (location.pathname === path) return;
  history.pushState(state, "", path);
}

window.addEventListener("popstate", (e) => {
  const s = e.state;
  if (!s) { retourAccueil(false); return; }
  if (s.type === "detail")   afficherDetails(s.id, s.mediaType, false);
  else if (s.type === "genre")    chargerGenre(s.name, s.page||1, s.mediaType||"movie", false);
  else if (s.type === "series")   chargerSeries(s.page||1, false);
  else if (s.type === "trending") chargerTrending(false);
  else if (s.type === "platform") chargerParPlateforme(s.key, s.page||1, false);
  else if (s.type === "filming")  chargerLieuxDeTournage(s.page||1, false);
  else retourAccueil(false);
});

function goBack(){
  if (history.length > 1) history.back();
  else retourAccueil();
}