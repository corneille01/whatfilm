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
  const method = (options.method || "GET").toUpperCase();
  const useCache = method === "GET";

  if (useCache) {
    const cached = getCached(url);
    if (cached) return cached;
  }

  const res = await fetch(url, options);
  const ct = res.headers.get("content-type") || "";

  if (!ct.includes("application/json")) {
    throw new Error(`Réponse inattendue du serveur (${res.status}).`);
  }

  const data = await res.json();

  if (useCache && data && data.status !== "error") {
    setCache(url, data);
  }

  return data;
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
let _analysisInFlight = false;
let lastAnalyzedLink = null;
let lastGrid = null;
let currentPage = 1;
let currentGenreName = "";
let _allResults = [];
let _currentTotalPages = 1;
let currentMovieId = null;
let currentMediaType = "movie";
let analysisAbortController = null;
let navStack = [];
let _detailTourismMap = null;
let _detailTourismMarkers = [];
let _detailTourismAmenityLayer = null;
let _detailTourismIsoLayer = null;





// ─── SON IMMERSIF (fond spatial) ──────────────────────────
let _immersiveAudioCtx = null;
let _immersiveGain = null;
let _immersiveOsc = null;
let _immersiveInterval = null;
let _cameFromAnalysis = false;

let _correctionUrl = null, _correctionTranscript = "", _correctionOcr = "";
let _correctionDebounce = null;

function ouvrirCorrection() {
  _correctionUrl = lastAnalyzedLink;
  document.getElementById("correction-modal").style.display = "flex";
  document.getElementById("correction-search").value = "";
  document.getElementById("correction-results").innerHTML = "";
}

function fermerCorrection() {
  document.getElementById("correction-modal").style.display = "none";
}

function rechercherCorrection(query) {
  clearTimeout(_correctionDebounce);
  if (query.trim().length < 2) { document.getElementById("correction-results").innerHTML = ""; return; }
  _correctionDebounce = setTimeout(async () => {
    try {
      const data = await safeFetch(`/rechercher?query=${encodeURIComponent(query)}&lang=${getTMDBLang()}`);
      const results = (data.results || []).slice(0, 6);
      document.getElementById("correction-results").innerHTML = results.map(m => {
        const isTv = m.media_type === "tv" || !!m.first_air_date;
        const poster = m.poster_path ? `https://image.tmdb.org/t/p/w92${m.poster_path}` : "";
        const year = (m.release_date || m.first_air_date || "").split("-")[0];
        return `<div onclick="envoyerCorrection(${m.id},'${isTv ? "tv" : "movie"}')"
                     style="display:flex;gap:10px;padding:8px;cursor:pointer;border-radius:8px" 
                     onmouseover="this.style.background='var(--card)'" onmouseout="this.style.background=''">
          ${poster ? `<img src="${poster}" style="width:40px;border-radius:4px">` : ""}
          <div><strong>${escapeHtml(m.title || m.name)}</strong><br><small style="color:var(--muted)">${year}</small></div>
        </div>`;
      }).join("");
    } catch (e) {}
  }, 350);
}

async function envoyerCorrection(tmdbId, mediaType) {
  fermerCorrection();
  try {
    const res = await fetch("/feedback/correction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: _correctionUrl || "",
        transcript: _correctionTranscript,
        ocr_text: _correctionOcr,
        corrected_tmdb_id: tmdbId,
        corrected_media_type: mediaType,
        lang: getTMDBLang(),
      }),
    });
    const data = await res.json();
    if (data.status === "applied") {
      toast("Merci ! Résultat corrigé.");
      afficherDetails(tmdbId, mediaType);
    } else {
      toast("Merci pour ton signalement, on vérifie.");
    }
  } catch (e) {
    toast("Erreur d'envoi, réessaie.");
  }
}


function afficherTourismeTournage(container, locApiLocations = [], wdLocations = [], context = {}) {
  const all = [...(locApiLocations || []), ...(wdLocations || [])];

  const locations = all
    .map(normalizeDetailLocation)
    .filter(l => l && Number.isFinite(l.lat) && Number.isFinite(l.lng));

  if (!locations.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <section class="detail-tourism-block">
      <div class="detail-tourism-head">
        <div>
          <h3>
            <i class="fas fa-map-marked-alt"></i>
            Lieux de tournage & guide touristique
          </h3>
          <p>
            Explore les vrais lieux de tournage, les restaurants, hôtels,
            transports et activités proches.
          </p>
        </div>
      </div>

      <div class="detail-tourism-grid">
        <div id="detail-tourism-map" class="detail-tourism-map"></div>

        <div class="detail-tourism-side">
          <div class="detail-tourism-locations">
            ${locations.map((loc, index) => `
              <button class="detail-location-card"
                      onclick="selectDetailFilmingLocation(${index})">
                <span class="detail-location-num">${index + 1}</span>
                <span>
                  <strong>${escapeHtml(loc.name)}</strong>
                  <small>${escapeHtml([loc.city, loc.country].filter(Boolean).join(", ") || "Lieu non précisé")}</small>
                </span>
              </button>
            `).join("")}
          </div>

          <div id="detail-nearby-panel" class="detail-nearby-panel">
            <p>Sélectionne un lieu pour voir les commodités proches.</p>
          </div>
        </div>
      </div>
    </section>
  `;

  window._detailTourismLocations = locations;
  window._detailTourismContext = context;

  ensureDetailMapLibs(() => {
    initDetailTourismMap(locations);
  });
}

function normalizeDetailLocation(l) {
  if (!l) return null;

  const lat = Number(l.lat ?? l.latitude);
  const lng = Number(l.lng ?? l.lon ?? l.longitude);

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

  return {
    id: l.id || l.location_id || null,
    name: l.name || l.label || l.title || "Lieu de tournage",
    city: l.city || "",
    country: l.country && l.country !== "Inconnu" ? l.country : "",
    address: l.address || "",
    scene: l.scene || l.scene_description || l.description || "",
    lat,
    lng
  };
}

function ensureDetailMapLibs(callback) {
  const loadLeaflet = () => {
    if (window.L) return Promise.resolve();

    if (!document.querySelector('link[href*="leaflet.css"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    return loadScriptOnce(
      "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
      "leaflet-js-detail"
    );
  };
loadLeaflet()
  .then(callback)
  .catch(err => {
    console.warn("Carte touristique impossible à charger:", err);
  });
}

function initDetailTourismMap(locations) {
  const mapEl = document.getElementById("detail-tourism-map");
  if (!mapEl || !window.L) return;

  if (_detailTourismMap) {
    try {
      _detailTourismMap.remove();
    } catch (e) {}
    _detailTourismMap = null;
  }

  _detailTourismMarkers = [];

  _detailTourismMap = L.map(mapEl, {
    scrollWheelZoom: false,
    zoomControl: true
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(_detailTourismMap);

  const bounds = L.latLngBounds();

  locations.forEach((loc, index) => {
    const marker = L.marker([loc.lat, loc.lng])
      .addTo(_detailTourismMap)
      .bindPopup(`
        <strong>${escapeHtml(loc.name)}</strong><br>
        <small>${escapeHtml([loc.city, loc.country].filter(Boolean).join(", "))}</small>
      `);

    marker.on("click", () => selectDetailFilmingLocation(index));

    _detailTourismMarkers.push(marker);
    bounds.extend([loc.lat, loc.lng]);
  });

  setTimeout(() => {
    _detailTourismMap.invalidateSize();

    if (bounds.isValid()) {
      _detailTourismMap.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 13
      });
    }
  }, 250);
}
async function selectDetailFilmingLocation(index) {
  const locations = window._detailTourismLocations || [];
  const loc = locations[index];

  if (!loc || !_detailTourismMap) return;

  const marker = _detailTourismMarkers[index];

  _detailTourismMap.flyTo([loc.lat, loc.lng], 15, {
    duration: 0.8
  });

  if (marker) marker.openPopup();

  const panel = document.getElementById("detail-nearby-panel");
  if (panel) {
    panel.innerHTML = `
      <div class="tourism-coming-soon">
        <strong>Guide touristique bientôt disponible</strong>
        <p>
          Les hôtels, restaurants, transports et activités proches seront ajoutés
          dans une prochaine version.
        </p>
        <a class="btn-stream"
           href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc.lat + "," + loc.lng)}"
           target="_blank"
           rel="noopener">
          <i class="fas fa-map-location-dot"></i>
          Ouvrir ce lieu sur Google Maps
        </a>
      </div>
    `;
  }
}








// ════ DICTIONNAIRE INTERNATIONAL ════
const dict = {
  "en-US": {
    partner_title: "Want to go further?",
report_wrong_btn: "Not the right movie?",
    filming_no_result: "No result.",
    filming_load_error: "Loading error.",
    filming_no_movie: "No movie found.",
    filming_see_one: "View filming location",
    filming_see_many: "View locations",
    filming_you_are_here: "You are here",
    filming_geo_denied: "Geolocation denied",

    title: "PELIFY",
    tagline: "Paste a TikTok, Reel or YouTube link — we identify the film in seconds",
    subtitle: "Just saw a movie clip on TikTok or in a story and don’t know what it is? Paste the link — we tell you everything: title, streaming, cast.",
    placeholder: "Paste a TikTok/Reel/YouTube link, upload a video, or type a title...",
    badge: "Shazam for movies",

    back_home: "Home",
    back_list: "Back to list",
    ai_conf: "Confidence",
    reset: "Reset",

    year: "Year",
    min_score: "Min score",
    sort_pop: "🔥 Popularity",
    sort_top: "⭐ Top rated",
    sort_asc: "Score ascending",
    sort_new: "🆕 Newest",
    sort_old: "📼 Oldest",

    no_streaming_country: "No streaming available in the US currently.",
    cancel: "Cancel",

    game_hint: "TAP / SPACE to jump",
    game_playing_msg: "<i class=\"fas fa-film\"></i> We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",

    food_title: "Ready to watch?",
    food_desc: "Order popcorn & snacks via DoorDash!",
    food_btn: "Order",

    streaming_title: "Available on",
    searching: "Manual search",
    loading_home: "Loading trending...",

    not_found_title: "Movie not found",
    similar_title: "<i class=\"fas fa-film\"></i> Similar movies",
    cast_title: "Cast",
    series_tag: "TV Series",

    trailer_title: "Trailer",
    scene_identified: "Scene identified",
    no_synopsis: "No synopsis available.",
    see_trailer: "Watch trailer",
    search_trailer: "Find trailer on YouTube",

    seasons_title: "Seasons",
    episodes_title: "Episodes",
    loading_episodes: "Loading episodes...",

    providers_country: "US",
    game_over: "GAME OVER — Score: ",

    filming_btn: "Filmed Here",
    filming_title: "FILMING LOCATIONS",
    filming_subtitle: "Explore real-world locations from cinema & TV worldwide",
    filming_search: "Search a film…",
    filming_movies_only: "Movies",
    filming_all_media: "All",

    err_server_busy: "The server is busy. Please retry in 30 seconds.",
    err_private: "This video is private or requires a login.",
    err_geo: "This video is not available in your region.",
    err_deleted: "This video has been deleted or no longer exists.",
    err_download: "Unable to download this video. Make sure it's public.",
    err_no_frames: "Could not extract images from this video.",
    err_timeout: "Analysis timed out. Try a shorter video.",
    err_session: "Session expired. Please retry.",
    err_generic: "An error occurred. Please try again.",
    auth_title: "Log in to Pelify",
    auth_desc: "Just an email, no password. We'll send you a login link.",
    auth_send_btn: "Send link",
    auth_cancel: "Cancel",
    auth_sent_title: "Link sent!",
    auth_sent_desc: "Check your inbox (and spam folder) then click the link you received.",
    auth_close: "Close",
    auth_invalid_email: "Invalid email address.",
    paywall_title: "Free trial used",
    paywall_desc: "You've used your free identification for today. Upgrade to Pelify Pro for unlimited access.",
    paywall_per_week: "excl. tax / week",
    paywall_choose: "Choose",
    paywall_per_month: "excl. tax / month",
    paywall_unlimited: "Unlimited identifications, cancel anytime",
    paywall_cta: "Upgrade to Pelify Pro",
    paywall_cancel: "Later",
    account_manage: "Manage subscription",
    account_logout: "Log out",
    account_pro_active: "Pelify Pro active",
    account_free_plan: "Free account — 1/day",
    account_logged_out: "Logged out.",
    billing_success: "Subscription activated! 🎉",
    err_low_confidence: "Movie not identified with enough confidence. Try searching manually.",
    search_manually: "Search manually",
    err_rate_limited: "Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily: "Daily limit reached. Come back tomorrow.",
    err_video_too_short: "Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large: "File too large. Try a shorter video.",
    err_video_blocked: "Video blocked for copyright reasons.",
    err_unsupported: "Unsupported platform or format.",

    step1: "Paste a TikTok, Instagram, Facebook, YouTube, X, LinkedIn link... or upload the video",
    step2: "We analyze the clip in a few seconds",
    step3: "The movie, series or anime appears, with where to watch it",
    step4: "Bonus: explore the real filming locations on a map, with nearby amenities around each filming location",

    cta: "Identify",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> Tap a card for details, streaming and similar movies.",
    results: "results",

    seo_summary: "How to find a movie from TikTok?",
    seo_h2: "How to find a movie from a TikTok, Instagram, YouTube or any other social media video?",
    seo_intro: "Many viral scenes on TikTok, Instagram or YouTube Shorts come from unknown movies, series or anime. With Pelify, just paste the link to identify the film in seconds.",
    seo_li1: "Identify a movie from TikTok",
    seo_li2: "Find a movie from a video",
    seo_li3: "Recognize a movie scene",
    seo_li4: "What movie is in this video?",

    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Comedy",
      scifi: "Sci-Fi",
      trending: "Trending",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crime",
      documentary: "Documentary",
      fantasy: "Fantasy",
      series: "TV Series",
      family: "Family"
    }
  },

  "en-GB": {
    partner_title: "Want to go further?",
report_wrong_btn: "Not the right movie?",
    filming_no_result: "No result.",
    filming_load_error: "Loading error.",
    filming_no_movie: "No movie found.",
    filming_see_one: "View filming location",
    filming_see_many: "View locations",
    filming_you_are_here: "You are here",
    filming_geo_denied: "Geolocation denied",

    title: "PELIFY",
    tagline: "Paste a TikTok, Reel or YouTube link — we identify the film in seconds",
    subtitle: "Just seen a film clip on TikTok or in a story and don’t know what it is? Paste the link — we tell you everything: title, streaming, cast.",
    placeholder: "Paste a TikTok/Reel/YouTube link, upload a video, or type a title...",
    badge: "Shazam for films",

    back_home: "Home",
    back_list: "Back to list",
    ai_conf: "Confidence",
    reset: "Reset",

    year: "Year",
    min_score: "Min score",
    sort_pop: "🔥 Popularity",
    sort_top: "⭐ Top rated",
    sort_asc: "Score ascending",
    sort_new: "🆕 Newest",
    sort_old: "📼 Oldest",

    no_streaming_country: "No streaming available in the UK currently.",
    cancel: "Cancel",

    game_hint: "TAP / SPACE to jump",
    game_playing_msg: "<i class=\"fas fa-film\"></i> We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",

    food_title: "Ready to watch?",
    food_desc: "Order popcorn & snacks via Deliveroo!",
    food_btn: "Order",

    streaming_title: "Available on",
    searching: "Manual search",
    loading_home: "Loading trending...",

    not_found_title: "Movie not found",
    similar_title: "<i class=\"fas fa-film\"></i> Similar movies",
    cast_title: "Cast",
    series_tag: "TV Series",

    trailer_title: "Trailer",
    scene_identified: "Scene identified",
    no_synopsis: "No synopsis available.",
    see_trailer: "Watch trailer",
    search_trailer: "Find trailer on YouTube",

    seasons_title: "Seasons",
    episodes_title: "Episodes",
    loading_episodes: "Loading episodes...",

    providers_country: "GB",
    game_over: "GAME OVER — Score: ",

    filming_btn: "Filmed Here",
    filming_title: "FILMING LOCATIONS",
    filming_subtitle: "Explore real-world locations from cinema & TV worldwide",
    filming_search: "Search a film…",
    filming_movies_only: "Movies",
    filming_all_media: "All",

    err_server_busy: "The server is busy. Please retry in 30 seconds.",
    err_private: "This video is private or requires a login.",
    err_geo: "This video is not available in your region.",
    err_deleted: "This video has been deleted or no longer exists.",
    err_download: "Unable to download this video. Make sure it's public.",
    err_no_frames: "Could not extract images from this video.",
    err_timeout: "Analysis timed out. Try a shorter video.",
    err_session: "Session expired. Please retry.",
    err_generic: "An error occurred. Please try again.",
    auth_title: "Log in to Pelify",
    auth_desc: "Just an email, no password. We'll send you a login link.",
    auth_send_btn: "Send link",
    auth_cancel: "Cancel",
    auth_sent_title: "Link sent!",
    auth_sent_desc: "Check your inbox (and spam folder) then click the link you received.",
    auth_close: "Close",
    auth_invalid_email: "Invalid email address.",
    paywall_title: "Free trial used",
    paywall_desc: "You've used your free identification for today. Upgrade to Pelify Pro for unlimited access.",
    paywall_per_week: "excl. tax / week",
    paywall_choose: "Choose",
    paywall_per_month: "excl. tax / month",
    paywall_unlimited: "Unlimited identifications, cancel anytime",
    paywall_cta: "Upgrade to Pelify Pro",
    paywall_cancel: "Later",
    account_manage: "Manage subscription",
    account_logout: "Log out",
    account_pro_active: "Pelify Pro active",
    account_free_plan: "Free account — 1/day",
    account_logged_out: "Logged out.",
    billing_success: "Subscription activated! 🎉",
    err_low_confidence: "Movie not identified with enough confidence. Try searching manually.",
    search_manually: "Search manually",
    err_rate_limited: "Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily: "Daily limit reached. Come back tomorrow.",
    err_video_too_short: "Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large: "File too large. Try a shorter video.",
    err_video_blocked: "Video blocked for copyright reasons.",
    err_unsupported: "Unsupported platform or format.",

    step1: "Paste a TikTok, Instagram, Facebook, YouTube, X, LinkedIn link... or upload the video",
    step2: "We analyse the clip in a few seconds",
    step3: "The film, series or anime appears, with where to watch it",
    step4: "Bonus: explore the real filming locations on a map, with nearby amenities around each filming location",

    cta: "Identify",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> Tap a card for details, streaming and similar movies.",
    results: "results",

    seo_summary: "How to find a movie from TikTok?",
    seo_h2: "How to find a movie from a TikTok, Instagram, YouTube or any other social media video?",
    seo_intro: "Many viral scenes on TikTok, Instagram or YouTube Shorts come from unknown movies, series or anime. With Pelify, just paste the link to identify the film in seconds.",
    seo_li1: "Identify a movie from TikTok",
    seo_li2: "Find a movie from a video",
    seo_li3: "Recognise a movie scene",
    seo_li4: "What movie is in this video?",

    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Comedy",
      scifi: "Sci-Fi",
      trending: "Trending",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crime",
      documentary: "Documentary",
      fantasy: "Fantasy",
      series: "TV Series",
      family: "Family"
    }
  },

  fr: {
    partner_title: "Envie d'aller plus loin ?",
report_wrong_btn: "Ce n'est pas le bon film ?",
    filming_no_result: "Aucun résultat.",
    filming_load_error: "Erreur de chargement.",
    filming_no_movie: "Aucun film trouvé.",
    filming_see_one: "Voir le lieu de tournage",
    filming_see_many: "Voir les lieux",
    filming_you_are_here: "Vous êtes ici",
    filming_geo_denied: "Géolocalisation refusée",

    title: "PELIFY",
    tagline: "Collez un lien TikTok, Reel ou YouTube — nous identifions le film en quelques secondes",
    subtitle: "Vous venez de voir un extrait de film sur TikTok ou en story sans savoir lequel ? Collez le lien, on vous dit tout — titre, streaming, casting.",
    placeholder: "Collez un lien TikTok/Reel/YouTube, importez une vidéo, ou tapez un titre...",
    badge: "Shazam pour les films",

    back_home: "Accueil",
    back_list: "Retour à la liste",
    ai_conf: "Confiance",
    reset: "Reset",

    year: "Année",
    min_score: "Note min",
    sort_pop: "🔥 Popularité",
    sort_top: "⭐ Mieux notés",
    sort_asc: "Note croissante",
    sort_new: "🆕 Plus récents",
    sort_old: "📼 Plus anciens",

    no_streaming_country: "Pas de streaming disponible en France actuellement.",
    cancel: "Annuler",

    game_hint: "TAP / ESPACE pour sauter",
    game_playing_msg: "<i class=\"fas fa-film\"></i> On cherche le film de votre lien…\nJouez pendant l'analyse — ça prend environ 30 secondes !",

    food_title: "Prêt à regarder ce film ?",
    food_desc: "Commandez vos snacks via UberEats !",
    food_btn: "Commander",

    streaming_title: "Disponible sur",
    searching: "Recherche manuelle",
    loading_home: "Chargement des tendances...",

    not_found_title: "Film non identifié",
    similar_title: "<i class=\"fas fa-film\"></i> Films similaires",
    cast_title: "Au casting",
    series_tag: "Série TV",

    trailer_title: "Bande-annonce",
    scene_identified: "Scène identifiée",
    no_synopsis: "Pas de synopsis disponible.",
    see_trailer: "Voir la bande-annonce",
    search_trailer: "Chercher la bande-annonce",

    seasons_title: "Saisons",
    episodes_title: "Épisodes",
    loading_episodes: "Chargement des épisodes...",

    providers_country: "FR",
    game_over: "GAME OVER — Score : ",

    filming_btn: "Lieux de tournage",
    filming_title: "LIEUX DE TOURNAGE",
    filming_subtitle: "Explorez les vrais décors du cinéma mondial",
    filming_search: "Rechercher un film…",
    filming_movies_only: "Films",
    filming_all_media: "Tout",

    err_server_busy: "Le serveur est actuellement surchargé. Réessayez dans 30 secondes.",
    err_private: "Cette vidéo est privée ou nécessite une connexion.",
    err_geo: "Cette vidéo n'est pas disponible dans votre région.",
    err_deleted: "Cette vidéo a été supprimée ou n'existe plus.",
    err_download: "Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique et accessible.",
    err_no_frames: "Impossible d'extraire des images de cette vidéo.",
    err_timeout: "L'analyse a pris trop de temps. Essayez avec une vidéo plus courte.",
    err_session: "Session expirée. Relancez l'analyse.",
    err_generic: "Une erreur s'est produite. Réessayez dans quelques instants.",
    auth_title: "Connexion à Pelify",
    auth_desc: "Un email, pas de mot de passe. On t'envoie un lien de connexion.",
    auth_send_btn: "Envoyer le lien",
    auth_cancel: "Annuler",
    auth_sent_title: "Lien envoyé !",
    auth_sent_desc: "Vérifie ta boîte mail (et les spams) puis clique sur le lien reçu.",
    auth_close: "Fermer",
    auth_invalid_email: "Email invalide.",
    paywall_title: "Essai gratuit utilisé",
    paywall_desc: "Tu as utilisé ton identification gratuite du jour. Passe à Pelify Pro pour un accès illimité.",
    paywall_per_week: "HT / semaine",
    paywall_choose: "Choisir",
    paywall_per_month: "HT / mois",
    paywall_unlimited: "Identifications illimitées, sans engagement",
    paywall_cta: "Passer à Pelify Pro",
    paywall_cancel: "Plus tard",
    account_manage: "Gérer l'abonnement",
    account_logout: "Déconnexion",
    account_pro_active: "Pelify Pro actif",
    account_free_plan: "Compte gratuit — 1 essai/jour",
    account_logged_out: "Déconnecté.",
    billing_success: "Abonnement activé ! 🎉",
    err_low_confidence: "Film non identifié avec certitude. Essayez de le rechercher manuellement.",
    search_manually: "Rechercher manuellement",
    err_rate_limited: "Trop de requêtes. Attendez une minute avant de réessayer.",
    err_rate_limited_daily: "Limite journalière atteinte. Revenez demain.",
    err_video_too_short: "Vidéo trop courte. Essayez un extrait d'au moins 3 secondes.",
    err_file_too_large: "Fichier trop volumineux. Essayez une vidéo plus courte.",
    err_video_blocked: "Vidéo bloquée pour droits d'auteur.",
    err_unsupported: "Plateforme ou format non supporté.",

    step1: "Collez un lien TikTok, Instagram, Facebook, YouTube, X, LinkedIn... ou importez la vidéo",
    step2: "Nous analysons l'extrait en quelques secondes",
    step3: "Le film, la série ou l'animé s'affiche, avec où le regarder",
    step4: "Bonus : explorez les vrais lieux de tournage sur une carte avec les commodités autour de chaque lieu de tournage",

    cta: "Identifier",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> Cliquer sur une carte pour voir les détails, le streaming et les films similaires.",
    results: "résultats",

    seo_summary: "Comment trouver un film depuis un extrait TikTok, Instagram, YouTube... ?",
    seo_h2: "Comment trouver un film à partir d'une vidéo TikTok, Instagram, YouTube ou tout autre réseau social ?",
    seo_intro: "Beaucoup de scènes virales sur TikTok, Instagram ou YouTube Shorts proviennent de films, séries ou animes inconnus. Avec Pelify, il suffit de coller le lien pour identifier le film en quelques secondes.",
    seo_li1: "Identifier un film depuis TikTok",
    seo_li2: "Trouver un film à partir d'une vidéo",
    seo_li3: "Reconnaître une scène de film",
    seo_li4: "Quel film est dans cette vidéo ?",

    genres: {
      horror: "Horreur",
      action: "Action",
      comedy: "Comédie",
      scifi: "Sci-Fi",
      trending: "Tendances",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drame",
      crime: "Crime",
      documentary: "Documentaire",
      fantasy: "Fantastique",
      series: "Séries TV",
      family: "Famille"
    }
  },

  es: {
    partner_title: "¿Quieres ir más lejos?",
report_wrong_btn: "¿No es la película correcta?",
    filming_no_result: "Sin resultados.",
    filming_load_error: "Error de carga.",
    filming_no_movie: "No se encontró ninguna película.",
    filming_see_one: "Ver localización de rodaje",
    filming_see_many: "Ver localizaciones",
    filming_you_are_here: "Estás aquí",
    filming_geo_denied: "Geolocalización rechazada",

    title: "PELIFY",
    tagline: "Pega un enlace de TikTok, Reel o YouTube — identificamos la película en segundos",
    subtitle: "¿Acabas de ver un fragmento de película en TikTok o en una story y no sabes cuál es? Pega el enlace — te contamos todo: título, streaming y reparto.",
    placeholder: "Pega un enlace de TikTok/Reel/YouTube, sube un vídeo o escribe un título...",
    badge: "Shazam para películas",

    back_home: "Inicio",
    back_list: "Volver a la lista",
    ai_conf: "Confianza",
    reset: "Restablecer",

    year: "Año",
    min_score: "Nota mínima",
    sort_pop: "🔥 Popularidad",
    sort_top: "⭐ Mejor valoradas",
    sort_asc: "Nota ascendente",
    sort_new: "🆕 Más recientes",
    sort_old: "📼 Más antiguas",

    no_streaming_country: "Sin streaming disponible actualmente.",
    cancel: "Cancelar",

    game_hint: "TAP / ESPACIO para saltar",
    game_playing_msg: "<i class=\"fas fa-film\"></i> Estamos identificando la película…\n¡Juega mientras esperas, tarda unos 30 segundos!",

    food_title: "¿Listo para ver la película?",
    food_desc: "¡Pide snacks y palomitas!",
    food_btn: "Pedir",

    streaming_title: "Disponible en",
    searching: "Buscar manualmente",
    loading_home: "Cargando tendencias...",

    not_found_title: "Película no encontrada",
    similar_title: "<i class=\"fas fa-film\"></i> Películas similares",
    cast_title: "Reparto",
    series_tag: "Serie TV",

    trailer_title: "Tráiler",
    scene_identified: "Escena identificada",
    no_synopsis: "Sin sinopsis disponible.",
    see_trailer: "Ver tráiler",
    search_trailer: "Buscar tráiler en YouTube",

    seasons_title: "Temporadas",
    episodes_title: "Episodios",
    loading_episodes: "Cargando episodios...",

    providers_country: "ES",
    game_over: "GAME OVER — Puntuación: ",

    filming_btn: "Rodado aquí",
    filming_title: "LOCALIZACIONES DE RODAJE",
    filming_subtitle: "Explora los escenarios reales del cine mundial",
    filming_search: "Buscar una película…",
    filming_movies_only: "Películas",
    filming_all_media: "Todo",

    err_server_busy: "El servidor está ocupado. Reintenta en 30 segundos.",
    err_private: "Este vídeo es privado o requiere inicio de sesión.",
    err_geo: "Este vídeo no está disponible en tu región.",
    err_deleted: "Este vídeo fue eliminado o ya no existe.",
    err_download: "No se puede descargar este vídeo. Verifica que sea público.",
    err_no_frames: "No se pudieron extraer imágenes del vídeo.",
    err_timeout: "El análisis tardó demasiado. Prueba con un vídeo más corto.",
    err_session: "Sesión expirada. Reinicia el análisis.",
    err_generic: "Ocurrió un error. Inténtalo de nuevo.",
    auth_title: "Iniciar sesión en Pelify",
    auth_desc: "Solo un email, sin contraseña. Te enviamos un enlace de acceso.",
    auth_send_btn: "Enviar enlace",
    auth_cancel: "Cancelar",
    auth_sent_title: "¡Enlace enviado!",
    auth_sent_desc: "Revisa tu correo (y spam) y haz clic en el enlace recibido.",
    auth_close: "Cerrar",
    auth_invalid_email: "Email no válido.",
    paywall_title: "Prueba gratuita utilizada",
    paywall_desc: "Ya usaste tu identificación gratuita de hoy. Pásate a Pelify Pro para acceso ilimitado.",
    paywall_per_week: "sin IVA / semana",
    paywall_choose: "Elegir",
    paywall_per_month: "sin IVA / mes",
    paywall_unlimited: "Identificaciones ilimitadas, cancela cuando quieras",
    paywall_cta: "Pasar a Pelify Pro",
    paywall_cancel: "Más tarde",
    account_manage: "Gestionar suscripción",
    account_logout: "Cerrar sesión",
    account_pro_active: "Pelify Pro activo",
    account_free_plan: "Cuenta gratuita — 1/día",
    account_logged_out: "Sesión cerrada.",
    billing_success: "¡Suscripción activada! 🎉",
    err_low_confidence: "Película no identificada con certeza. Busca manualmente.",
    search_manually: "Buscar manualmente",
    err_rate_limited: "Demasiadas solicitudes. Espera un minuto antes de reintentar.",
    err_rate_limited_daily: "Límite diario alcanzado. Vuelve mañana.",
    err_video_too_short: "Video demasiado corto. Prueba con un clip de al menos 3 segundos.",
    err_file_too_large: "Archivo demasiado grande. Prueba con un video más corto.",
    err_video_blocked: "Video bloqueado por derechos de autor.",
    err_unsupported: "Plataforma o formato no compatible.",

    step1: "Pega un enlace de TikTok, Instagram, Facebook, YouTube, X, LinkedIn... o sube el vídeo",
    step2: "Analizamos el fragmento en pocos segundos",
    step3: "Aparece la película, serie o anime, con dónde verla",
    step4: "Bonus: explora los lugares reales de rodaje en un mapa, con servicios cercanos alrededor de cada lugar",

    cta: "Identificar",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> Tocar una tarjeta para ver detalles, streaming y películas similares.",
    results: "resultados",

    seo_summary: "¿Cómo encontrar una película desde TikTok?",
    seo_h2: "¿Cómo encontrar una película a partir de un vídeo de TikTok, Instagram, YouTube o cualquier otra red social?",
    seo_intro: "Muchas escenas virales en TikTok, Instagram o YouTube Shorts provienen de películas, series o animes desconocidos. Con Pelify, solo tienes que pegar el enlace para identificar la película en segundos.",
    seo_li1: "Identificar una película desde TikTok",
    seo_li2: "Encontrar una película a partir de un vídeo",
    seo_li3: "Reconocer una escena de película",
    seo_li4: "¿Qué película aparece en este vídeo?",

    genres: {
      horror: "Terror",
      action: "Acción",
      comedy: "Comedia",
      scifi: "Ciencia Ficción",
      trending: "Tendencias",
      romance: "Romance",
      animation: "Animación",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crimen",
      documentary: "Documental",
      fantasy: "Fantasía",
      series: "Series TV",
      family: "Familia"
    }
  },

  de: {
    partner_title: "Möchten Sie mehr erfahren?",
report_wrong_btn: "Nicht der richtige Film?",
    filming_no_result: "Kein Ergebnis.",
    filming_load_error: "Fehler beim Laden.",
    filming_no_movie: "Kein Film gefunden.",
    filming_see_one: "Drehort ansehen",
    filming_see_many: "Drehorte ansehen",
    filming_you_are_here: "Sie sind hier",
    filming_geo_denied: "Geolokalisierung abgelehnt",

    title: "PELIFY",
    tagline: "TikTok-, Reel- oder YouTube-Link einfügen — wir erkennen den Film in Sekunden",
    subtitle: "Du hast gerade einen Filmausschnitt auf TikTok oder in einer Story gesehen und weißt nicht, welcher Film es ist? Füge den Link ein — wir zeigen dir Titel, Streaming und Besetzung.",
    placeholder: "TikTok/Reel/YouTube-Link einfügen, Video hochladen oder Titel eingeben...",
    badge: "Shazam für Filme",

    back_home: "Startseite",
    back_list: "Zurück zur Liste",
    ai_conf: "Konfidenz",
    reset: "Zurücksetzen",

    year: "Jahr",
    min_score: "Mindestbewertung",
    sort_pop: "🔥 Beliebtheit",
    sort_top: "⭐ Bestbewertet",
    sort_asc: "Bewertung aufsteigend",
    sort_new: "🆕 Neueste",
    sort_old: "📼 Älteste",

    no_streaming_country: "Kein Streaming in Deutschland verfügbar.",
    cancel: "Abbrechen",

    game_hint: "TAP / LEERTASTE zum Springen",
    game_playing_msg: "<i class=\"fas fa-film\"></i> Wir identifizieren den Film…\nSpiel während du wartest — dauert ca. 30 Sekunden!",

    food_title: "Bereit zum Anschauen?",
    food_desc: "Bestelle Snacks und Popcorn!",
    food_btn: "Bestellen",

    streaming_title: "Verfügbar auf",
    searching: "Manuell suchen",
    loading_home: "Trends werden geladen...",

    not_found_title: "Film nicht gefunden",
    similar_title: "<i class=\"fas fa-film\"></i> Ähnliche Filme",
    cast_title: "Besetzung",
    series_tag: "TV-Serie",

    trailer_title: "Trailer",
    scene_identified: "Szene identifiziert",
    no_synopsis: "Keine Beschreibung verfügbar.",
    see_trailer: "Trailer ansehen",
    search_trailer: "Trailer auf YouTube suchen",

    seasons_title: "Staffeln",
    episodes_title: "Folgen",
    loading_episodes: "Folgen werden geladen...",

    providers_country: "DE",
    game_over: "GAME OVER — Punkte: ",

    filming_btn: "Drehorte",
    filming_title: "DREHORTE",
    filming_subtitle: "Entdecke echte Filmschauplätze weltweit",
    filming_search: "Film suchen…",
    filming_movies_only: "Filme",
    filming_all_media: "Alle",

    err_server_busy: "Der Server ist ausgelastet. Versuche es in 30 Sekunden.",
    err_private: "Dieses Video ist privat oder erfordert einen Login.",
    err_geo: "Dieses Video ist in deiner Region nicht verfügbar.",
    err_deleted: "Dieses Video wurde gelöscht oder existiert nicht mehr.",
    err_download: "Video kann nicht heruntergeladen werden. Stelle sicher, dass es öffentlich ist.",
    err_no_frames: "Bilder konnten nicht aus dem Video extrahiert werden.",
    err_timeout: "Analyse hat zu lange gedauert. Versuche ein kürzeres Video.",
    err_session: "Sitzung abgelaufen. Starte die Analyse neu.",
    err_generic: "Ein Fehler ist aufgetreten. Versuche es erneut.",
    auth_title: "Bei Pelify anmelden",
    auth_desc: "Nur eine E-Mail, kein Passwort. Wir senden dir einen Anmeldelink.",
    auth_send_btn: "Link senden",
    auth_cancel: "Abbrechen",
    auth_sent_title: "Link gesendet!",
    auth_sent_desc: "Schau in dein Postfach (auch Spam) und klicke auf den Link.",
    auth_close: "Schließen",
    auth_invalid_email: "Ungültige E-Mail-Adresse.",
    paywall_title: "Kostenloser Versuch verbraucht",
    paywall_desc: "Du hast deine kostenlose Identifikation für heute genutzt. Hol dir Pelify Pro für unbegrenzten Zugriff.",
    paywall_per_week: "netto / Woche",
    paywall_choose: "Wählen",
    paywall_per_month: "netto / Monat",
    paywall_unlimited: "Unbegrenzte Identifikationen, jederzeit kündbar",
    paywall_cta: "Zu Pelify Pro wechseln",
    paywall_cancel: "Später",
    account_manage: "Abo verwalten",
    account_logout: "Abmelden",
    account_pro_active: "Pelify Pro aktiv",
    account_free_plan: "Kostenloses Konto — 1×/Tag",
    account_logged_out: "Abgemeldet.",
    billing_success: "Abo aktiviert! 🎉",
    err_low_confidence: "Film nicht sicher identifiziert. Suche manuell.",
    search_manually: "Manuell suchen",
    err_rate_limited: "Zu viele Anfragen. Warte eine Minute, bevor du es erneut versuchst.",
    err_rate_limited_daily: "Tägliches Limit erreicht. Komm morgen wieder.",
    err_video_too_short: "Video zu kurz. Versuche einen Clip von mindestens 3 Sekunden.",
    err_file_too_large: "Datei zu groß. Versuche ein kürzeres Video.",
    err_video_blocked: "Video aus urheberrechtlichen Gründen gesperrt.",
    err_unsupported: "Nicht unterstützte Plattform oder Format.",

    step1: "Füge einen Link von TikTok, Instagram, Facebook, YouTube, X, LinkedIn ein... oder lade das Video hoch",
    step2: "Wir analysieren den Ausschnitt in wenigen Sekunden",
    step3: "Der Film, die Serie oder der Anime erscheint, inklusive Streaming-Optionen",
    step4: "Bonus: Entdecke die echten Drehorte auf einer Karte, mit Einrichtungen rund um jeden Drehort",

    cta: "Identifizieren",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> Auf eine Karte tippen für Details, Streaming und ähnliche Filme.",
    results: "Ergebnisse",

    seo_summary: "Wie findet man einen Film über TikTok?",
    seo_h2: "Wie findet man einen Film anhand eines TikTok-, Instagram-, YouTube- oder anderen Social-Media-Videos?",
    seo_intro: "Viele virale Szenen auf TikTok, Instagram oder YouTube Shorts stammen aus unbekannten Filmen, Serien oder Animes. Mit Pelify fügst du einfach den Link ein, um den Film in Sekunden zu erkennen.",
    seo_li1: "Einen Film über TikTok identifizieren",
    seo_li2: "Einen Film anhand eines Videos finden",
    seo_li3: "Eine Filmszene erkennen",
    seo_li4: "Welcher Film ist in diesem Video?",

    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Komödie",
      scifi: "Science-Fiction",
      trending: "Trends",
      romance: "Romantik",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Krimi",
      documentary: "Dokumentarfilm",
      fantasy: "Fantasy",
      series: "TV-Serien",
      family: "Familie"
    }
  },

  zh: {
    partner_title: "想要更进一步？",
report_wrong_btn: "不是这部电影？",
    filming_no_result: "没有结果。",
    filming_load_error: "加载错误。",
    filming_no_movie: "未找到电影。",
    filming_see_one: "查看拍摄地点",
    filming_see_many: "查看拍摄地点",
    filming_you_are_here: "您在这里",
    filming_geo_denied: "地理位置访问被拒绝",

    title: "PELIFY",
    tagline: "粘贴 TikTok、Reel 或 YouTube 链接 — 我们会在几秒内识别影片",
    subtitle: "刚刚在 TikTok 或动态里看到一个电影片段，却不知道是哪部电影？粘贴链接，我们会告诉你片名、播放平台和演员信息。",
    placeholder: "粘贴 TikTok/Reel/YouTube 链接，上传视频，或输入片名...",
    badge: "电影版 Shazam",

    back_home: "首页",
    back_list: "返回列表",
    ai_conf: "置信度",
    reset: "重置",

    year: "年份",
    min_score: "最低评分",
    sort_pop: "🔥 热度",
    sort_top: "⭐ 最高评分",
    sort_asc: "评分升序",
    sort_new: "🆕 最新",
    sort_old: "📼 最早",

    no_streaming_country: "暂无可用的流媒体。",
    cancel: "取消",

    game_hint: "点击 / 空格键跳跃",
    game_playing_msg: "<i class=\"fas fa-film\"></i> 正在识别您视频中的电影…\n请玩游戏等待，大约需要30秒！",

    food_title: "准备好看电影了吗？",
    food_desc: "立即订购爆米花和零食！",
    food_btn: "下单",

    streaming_title: "可在以下平台观看",
    searching: "手动搜索",
    loading_home: "加载热门中...",

    not_found_title: "未找到影片",
    similar_title: "<i class=\"fas fa-film\"></i> 相似影片",
    cast_title: "演员表",
    series_tag: "电视剧",

    trailer_title: "预告片",
    scene_identified: "识别场景",
    no_synopsis: "暂无简介。",
    see_trailer: "观看预告片",
    search_trailer: "在 YouTube 上搜索预告片",

    seasons_title: "季",
    episodes_title: "集",
    loading_episodes: "加载剧集中...",

    providers_country: "CN",
    game_over: "游戏结束 — 得分：",

    filming_btn: "拍摄地",
    filming_title: "拍摄地点",
    filming_subtitle: "探索全球电影真实拍摄地",
    filming_search: "搜索电影…",
    filming_movies_only: "电影",
    filming_all_media: "全部",

    err_server_busy: "服务器繁忙，请30秒后重试。",
    err_private: "该视频为私密视频或需要登录。",
    err_geo: "该视频在您所在地区不可用。",
    err_deleted: "该视频已被删除或不再存在。",
    err_download: "无法下载此视频，请确认视频为公开状态。",
    err_no_frames: "无法从视频中提取图像。",
    err_timeout: "分析超时，请尝试较短的视频。",
    err_session: "会话已过期，请重新分析。",
    err_generic: "发生错误，请重试。",
    auth_title: "登录 Pelify",
    auth_desc: "只需邮箱，无需密码。我们会给你发送登录链接。",
    auth_send_btn: "发送登录链接",
    auth_cancel: "取消",
    auth_sent_title: "链接已发送！",
    auth_sent_desc: "请查收邮箱（包括垃圾邮件），点击收到的链接。",
    auth_close: "关闭",
    auth_invalid_email: "邮箱地址无效。",
    paywall_title: "今日免费次数已用完",
    paywall_desc: "你已使用今日的免费识别。升级到 Pelify Pro 即可无限使用。",
    paywall_per_week: "税前 / 每周",
    paywall_choose: "选择",
    paywall_per_month: "税前 / 每月",
    paywall_unlimited: "无限识别，随时可取消",
    paywall_cta: "升级 Pelify Pro",
    paywall_cancel: "以后再说",
    account_manage: "管理订阅",
    account_logout: "退出登录",
    account_pro_active: "Pelify Pro 已激活",
    account_free_plan: "免费账户 — 每天1次",
    account_logged_out: "已退出登录。",
    billing_success: "订阅已激活！🎉",
    err_low_confidence: "无法确定识别电影，请手动搜索。",
    search_manually: "手动搜索",
    err_rate_limited: "请求过多。请等待一分钟后再试。",
    err_rate_limited_daily: "已达每日限额。请明天再来。",
    err_video_too_short: "视频太短。请尝试至少3秒的片段。",
    err_file_too_large: "文件太大。请尝试较短的视频。",
    err_video_blocked: "视频因版权原因被屏蔽。",
    err_unsupported: "不支持的平台或格式。",

    step1: "粘贴 TikTok、Instagram、Facebook、YouTube、X、LinkedIn 链接... 或上传视频",
    step2: "我们会在几秒钟内分析片段",
    step3: "电影、剧集或动漫会显示出来，并告诉你在哪里观看",
    step4: "奖励：在地图上探索真实拍摄地点，以及每个拍摄地点周边的便利设施",

    cta: "识别",
    hero_hint: "<i class=\"fas fa-hand-pointer\"></i> 点击卡片查看详情、播放平台和相似电影。",
    results: "个结果",

    seo_summary: "如何通过 TikTok 找电影？",
    seo_h2: "如何通过 TikTok、Instagram、YouTube 或其他社交媒体视频找到电影？",
    seo_intro: "TikTok、Instagram 或 YouTube Shorts 上的许多热门片段来自不知名的电影、剧集或动漫。使用 Pelify，只需粘贴链接即可在几秒内识别影片。",
    seo_li1: "通过 TikTok 识别电影",
    seo_li2: "通过视频找到电影",
    seo_li3: "识别电影场景",
    seo_li4: "这个视频里是什么电影？",

    genres: {
      horror: "恐怖",
      action: "动作",
      comedy: "喜剧",
      scifi: "科幻",
      trending: "热门",
      romance: "爱情",
      animation: "动画",
      thriller: "惊悚",
      drama: "剧情",
      crime: "犯罪",
      documentary: "纪录片",
      fantasy: "奇幻",
      series: "电视剧",
      family: "家庭"
    }
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


async function partagerFilm() {
  const slug = (document.getElementById("titre_film")?.innerText || "")
    .toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  const url = `https://pelify.app/film/${currentMovieId}${slug ? "/" + slug : ""}`;
  const title = document.getElementById("titre_film")?.innerText || "Ce film";
  const text = `J'ai trouvé ce film grâce à Pelify : ${title} 🎬`;

  if (navigator.share) {
    try {
      await navigator.share({ title, text, url });
    } catch (e) {
      if (e.name !== "AbortError") console.warn("Partage échoué", e);
    }
  } else {
    try {
      await navigator.clipboard.writeText(url);
      toast("Lien copié dans le presse-papier !");
    } catch (e) {
      toast("Impossible de copier le lien.");
    }
  }
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

    <a class="btn-genre home-action filming" href="https://tournage.pelify.app/"
      >
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
  _hideAllPages();
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("genre-nav").style.display="flex";
  document.getElementById("filtres-bar").style.display="none";
  document.getElementById("genre-title").innerText="";
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
  _hideAllPages();
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("genre-nav").style.display="flex";
  document.getElementById("filtres-bar").style.display="none";
  document.getElementById("genre-title").innerText="";
  const icon={video_private:"🔒",video_geo:"🌍",video_deleted:"🗑️",download_failed:"📵",server_busy:"⏳",no_frames:"🖼️",timeout:"⏱️",session_expired:"🔄",low_confidence:"🔍"}[code]||"⚠️";
  const retryBtn=(code==="server_busy"||code==="timeout"||code==="unexpected")?`<button class="btn-stream" style="margin-top:8px" onclick="relancerDerniereAnalyse()"><i class="fas fa-redo"></i> Réessayer</button>`:"";
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
function majHeroBtnClear(){const b=document.getElementById("hero-btn-clear");const i=document.getElementById("hero-search-input");if(b&&i)b.classList.toggle("visible",i.value.length>0);}
function effacerRechercheHero(){const i=document.getElementById("hero-search-input");const b=document.getElementById("hero-btn-clear");if(i)i.value="";if(b)b.classList.remove("visible");if(i)i.focus();}

// ════ NAVIGATION ════
function _hideAllPages(){
  ["page-film-detail","genre-grid","privacy-page","filming-page","hero","genre-nav"].forEach(id=>{
    const el=document.getElementById(id);if(el)el.style.display="none";
  });
  document.getElementById("platform-nav")?.classList.remove("visible")
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
 if (_analysisInFlight) return;   
  const input=document.getElementById("input_global").value.trim();
  if(!input)return;
  await new Promise(requestAnimationFrame);
  cacherErreur();
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  const isLink=/^https?:\/\//i.test(input)&&(/tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com/.test(input)||/instagram\.com/.test(input)||/youtube\.com|youtu\.be/.test(input)||/twitter\.com|x\.com/.test(input)||/facebook\.com|fb\.watch/.test(input)||/dailymotion\.com|dai\.ly/.test(input)||/bilibili\.com/.test(input)||/snapchat\.com/.test(input)||/vimeo\.com/.test(input)||/twitch\.tv/.test(input)||/linkedin\.com/.test(input)||/reddit\.com|redd\.it/.test(input)||/pinterest\.|pin\.it/.test(input)||/bit\.ly|t\.co|tinyurl\.com|ow\.ly|buff\.ly|short\.io|lnk\.to/.test(input))||/^https?:\/\//i.test(input);
if (isLink) { analyserVideo(input); }
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
   _analysisInFlight = false;
  if(analysisAbortController)analysisAbortController.abort();
  _adFinished=true;_analysisResult=null;
  document.getElementById('ad-modal').style.display='none';
  clearInterval(_adCountdownInterval);
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();retourAccueil();
}
function relancerDerniereAnalyse(){
  if(lastAnalyzedLink){
    analyserVideo(lastAnalyzedLink);
  } else {
    retourAccueil();
  }
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



// ════ RETRY AUTOMATIQUE SUR ERREUR SERVEUR TRANSITOIRE ════
// Gère le cas où Gunicorn redémarre son unique worker (Free tier Render)
// pile pendant une requête d'analyse. La requête initiale échoue avec
// une erreur réseau ou un 502/503, mais retenter quelques secondes plus
// tard (le temps que le nouveau worker boote) réussit généralement.
// ════ AUTH & BILLING (monétisation) ════
let _currentUser = null; // {logged_in, email?, subscribed?}

async function refreshAuthState() {
  try {
    const res = await fetch("/auth/me", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
      }
    });

    if (!res.ok) {
      _currentUser = { logged_in: false };
      majAccountBtn();
      return _currentUser;
    }

    const data = await res.json();

    _currentUser = {
      logged_in: !!data.logged_in,
      email: data.email || null,
      user_id: data.user_id || null,
      subscribed: !!data.subscribed,
      subscription: data.subscription || null
    };

    majAccountBtn();

    return _currentUser;

  } catch (e) {
    console.error("refreshAuthState:", e);
    _currentUser = { logged_in: false };
    majAccountBtn();
    return _currentUser;
  }
}

function majAccountBtn(){
  const icon = document.getElementById("account-btn-icon");
  if(!icon) return;
  if(_currentUser?.logged_in){
    icon.className = _currentUser.subscribed ? "fas fa-crown" : "fas fa-user-check";
  }else{
    icon.className = "fas fa-user";
  }
}

function ouvrirAuthModal(){
  document.getElementById("account-modal").style.display = "none";
  document.getElementById("auth-modal-form").style.display = "block";
  document.getElementById("auth-modal-sent").style.display = "none";
  document.getElementById("auth-error").style.display = "none";
  document.getElementById("auth-email-input").value = "";
  document.getElementById("auth-modal").style.display = "flex";
  setTimeout(() => document.getElementById("auth-email-input")?.focus(), 100);
}
function fermerAuthModal(){
  document.getElementById("auth-modal").style.display = "none";
}

async function envoyerMagicLink(){
  const input = document.getElementById("auth-email-input");
  const email = input.value.trim();
  const errEl = document.getElementById("auth-error");
  errEl.style.display = "none";
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)){
    errEl.textContent = t("auth_invalid_email");
    errEl.style.display = "block";
    return;
  }
  const btn = document.getElementById("auth-send-btn");
  btn.disabled = true;
  try{
    const res = await fetch("/auth/request-link", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({email}),
    });
    const data = await res.json();
    if(data.status !== "ok"){
      errEl.textContent = data.message || t("err_generic");
      errEl.style.display = "block";
      return;
    }
    document.getElementById("auth-modal-form").style.display = "none";
    document.getElementById("auth-modal-sent").style.display = "block";
  }catch(e){
    errEl.textContent = t("err_generic");
    errEl.style.display = "block";
  }finally{
    btn.disabled = false;
  }
}

function ouvrirPaywallModal(){
  document.getElementById("paywall-error").style.display = "none";
  document.getElementById("paywall-modal").style.display = "flex";
}
function fermerPaywallModal(){
  document.getElementById("paywall-modal").style.display = "none";
}

async function passerPro(plan = "weekly"){
  const errEl = document.getElementById("paywall-error");
  if(!_currentUser?.logged_in){
    fermerPaywallModal();
    fermerCompteModal();
    ouvrirAuthModal();
    return;
  }
  try{
    const res = await fetch("/billing/checkout", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({plan}),
    });
    const data = await res.json();
    if(data.status === "ok" && data.checkout_url){
      window.location.href = data.checkout_url;
    }else{
      const msg = data.message || t("err_generic");
      if(errEl){ errEl.textContent = msg; errEl.style.display = "block"; }
      else toast(msg);
    }
  }catch(e){
    const msg = t("err_generic");
    if(errEl){ errEl.textContent = msg; errEl.style.display = "block"; }
    else toast(msg);
  }
}

async function ouvrirCompteModal(){
  await refreshAuthState();
  if(!_currentUser?.logged_in){
    ouvrirAuthModal();
    return;
  }
  document.getElementById("account-email").textContent = _currentUser.email;
  const statusEl = document.getElementById("account-status");
  const manageBtn = document.getElementById("account-manage-btn");
  const subBtn = document.getElementById("account-subscribe-btn");
  if(_currentUser.subscribed){
    statusEl.innerHTML = `<span style="color:var(--primary)"><i class="fas fa-crown"></i> ${t("account_pro_active")}</span>`;
    manageBtn.style.display = "flex";
    subBtn.style.display = "none";
  }else{
    statusEl.innerHTML = `<span style="color:var(--muted)">${t("account_free_plan")}</span>`;
    manageBtn.style.display = "none";
    subBtn.style.display = "flex";
  }
  document.getElementById("account-modal").style.display = "flex";
}
function fermerCompteModal(){
  document.getElementById("account-modal").style.display = "none";
}

async function gererAbonnement(){
  try{
    const res = await fetch("/billing/portal");
    const data = await res.json();
    if(data.status === "ok" && data.portal_url){
      window.location.href = data.portal_url;
    }else{
      toast(data.message || t("err_generic"));
    }
  }catch(e){
    toast(t("err_generic"));
  }
}

async function deconnexion() {
  try {
    const res = await fetch("/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
      }
    });

    if (!res.ok) {
      throw new Error("Échec de la déconnexion");
    }

    // Vérification réelle auprès du serveur
    const auth = await refreshAuthState();

    if (auth.logged_in) {
      throw new Error("La session serveur est toujours active.");
    }

    _currentUser = {
      logged_in: false,
      email: null,
      user_id: null,
      subscribed: false,
      subscription: null
    };

    majAccountBtn();
    fermerCompteModal();

    toast(t("account_logged_out"));

  } catch (e) {
    console.error("Déconnexion:", e);
    toast("Impossible de confirmer la déconnexion.");
  }
}

async function fetchWithRetry(url, options, signal, maxRetries = 2, delayMs = 3000) {
  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(url, { ...options, signal });

      // 502/503 = erreur serveur transitoire typique d'un restart de worker.
      // On retente plutôt que de remonter l'erreur immédiatement.
      if ((res.status === 502 || res.status === 503) && attempt < maxRetries) {
        console.warn(`Tentative ${attempt + 1}/${maxRetries + 1} échouée (HTTP ${res.status}), nouvelle tentative dans ${delayMs}ms...`);
        await new Promise(r => setTimeout(r, delayMs));
        continue;
      }

      return res;
    } catch (e) {
      // AbortError = l'utilisateur a annulé, ne jamais retenter dans ce cas.
      if (e.name === "AbortError") throw e;

      lastError = e;
      if (attempt < maxRetries) {
        console.warn(`Tentative ${attempt + 1}/${maxRetries + 1} échouée (${e.message}), nouvelle tentative dans ${delayMs}ms...`);
        await new Promise(r => setTimeout(r, delayMs));
        continue;
      }
    }
  }

  throw lastError || new Error("network");
}
// Appelle /analyser_continue avec un filet de sécurité : si la requête
// échoue au niveau réseau (coupure, worker redémarré par Render en plein
// traitement) ou si la session a expiré côté serveur alors que l'analyse
// avait pourtant abouti, on retente via /analyser sur l'URL d'origine —
// qui vérifie systématiquement le cache en premier — plutôt que
// d'afficher une erreur générique à l'utilisateur.
async function _postAnalyserContinue(sessionId, ocrText, transcript, browserLang, signal, originalUrl) {
  const tryCacheFallback = async () => {
    if (!originalUrl) return null;
    try {
      const retry = await fetch("/analyser", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: originalUrl, lang: getTMDBLang(), browser_lang: browserLang }),
        signal
      });
      const retryData = await retry.json().catch(() => null);
      if (retryData && retryData.status === "cached") return retryData;
    } catch (_) {
      // Pas de résultat en cache non plus : on laisse l'erreur d'origine remonter.
    }
    return null;
  };

  try {
    const cr = await fetch("/analyser_continue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        ocr_text: ocrText,
        transcript: transcript,
        browser_lang: browserLang
      }),
      signal
    });

    let finalData;
    try {
      finalData = await cr.json();
    } catch (e) {
      throw new Error("json_parse");
    }

    if (finalData?.status === "error" && finalData?.code === "session_expired") {
      const cached = await tryCacheFallback();
      if (cached) return cached;
    }

    return finalData;

  } catch (e) {
    if (e.name === "AbortError") throw e;

    const cached = await tryCacheFallback();
    if (cached) return cached;

    throw e;
  }
}
// ════ ANALYSE VIDÉO ════
async function analyserVideo(lien){
   if (_analysisInFlight) return;   // ← garde anti-doublon
  _analysisInFlight = true;
   lastAnalyzedLink = lien;
  hideHero();_adFinished=false;_analysisResult=null;
  const lastAd=parseInt(localStorage.getItem('last_ad')||'0');
  const showAd=Date.now()-lastAd>30*60*1000;
  if(showAd){localStorage.setItem('last_ad',Date.now().toString());demarrerPub();}else{_adFinished=true;}
  const overlay=document.getElementById("loading-overlay");overlay.classList.add("active");startGame();
  let progress=0;const progressBar=document.getElementById("prog-fill");const percentLabel=document.getElementById("prog-percent");
  let progInterval=setInterval(()=>{if(progress<88){progress+=Math.random()*8+3;if(progress>88)progress=88;if(progressBar)progressBar.style.width=progress+"%";if(percentLabel)percentLabel.textContent=Math.round(progress)+"%";}},900);
  analysisAbortController=new AbortController();const signal=analysisAbortController.signal;
  try{
   const res=await fetchWithRetry("/analyser",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:lien,lang:getTMDBLang(),browser_lang:getBrowserLangShort()})},signal);
    if(res.status===401||res.status===402){
      clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
      _analysisInFlight=false;
      if(res.status===401)ouvrirAuthModal();else ouvrirPaywallModal();
      return;
    }
    if(!res.ok)throw new Error(`http_${res.status}`);
    let data;try{data=await res.json();}catch(e){throw new Error("json_parse");}
    if(data.status==="error"){clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();afficherErreurRiche(data);return;}
    if(data.status==="transcription_needed"){
      clearInterval(progInterval);
      const skipWhisper=data.skip_whisper===true;
      const[ocrText,transcript]=await Promise.allSettled([data.frames_base64?.length?runLocalOCR(data.frames_base64):Promise.resolve(""),(!skipWhisper&&data.audio_base64)?runLocalWhisper(data.audio_base64):Promise.resolve("")]);
      const finalData=await _postAnalyserContinue(data.session_id,ocrText.status==="fulfilled"?ocrText.value:"",transcript.status==="fulfilled"?transcript.value:"",getBrowserLangShort(),signal,lien);
       _analysisInFlight = false; 
      _afficherResultatFinal(finalData);return;
    }
    if(data.status==="processing"&&data.session_id){
    const r=await pollAnalysisStatus(data.session_id,signal);
    await _consumeAnalysis(r,signal,lien);
    return;
}
    clearInterval(progInterval);
     _analysisInFlight = false;  
    _afficherResultatFinal(data);
  }catch(e){
     _analysisInFlight = false; 
    clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
    if(e.name==="AbortError"){
  return;
}
    if(e.message==="json_parse")afficherErreurRiche({code:"unexpected",message:t("err_generic")});
    else if(e.message?.startsWith("http_")){const status=parseInt(e.message.split("_")[1]);afficherErreurRiche({code:status===502||status===503?"server_busy":"unexpected"});}
    else afficherErreurRiche({code:"unexpected",message:t("err_generic")});
  }
}

async function analyserVideoUpload(file){
  if (_analysisInFlight) return;
_analysisInFlight = true;
if(!file){ _analysisInFlight = false; return; }
  if(file.size > 50*1024*1024){ afficherErreur(t("err_file_too_large")||"Fichier trop volumineux (max 50 Mo)."); _analysisInFlight = false; return; }
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
    if(data.status==="error"&&(data.code==="auth_required"||data.code==="quota_exceeded")){_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();_analysisInFlight=false;if(data.code==="auth_required")ouvrirAuthModal();else ouvrirPaywallModal();return;}
    if(data.status==="error"){_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();afficherErreurRiche(data); _analysisInFlight = false; return;}
    if(data.status==="processing"&&data.session_id){const r=await pollAnalysisStatus(data.session_id,signal);await _consumeAnalysis(r,signal);return;}
    await _consumeAnalysis(data,signal,lien);
  }catch(e){
    _adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
    _analysisInFlight = false;
    if(e.name==="AbortError"||signal.aborted)return;
    afficherErreurRiche({code:"unexpected",message:t("err_generic")});
  }
}

async function _consumeAnalysis(data, signal, originalUrl) {

  // ═══════════════════════════════════════════════════════════════
  // AUTHENTIFICATION / QUOTA
  // ═══════════════════════════════════════════════════════════════
  if (
    data &&
    data.status === "error" &&
    (
      data.code === "auth_required" ||
      data.code === "quota_exceeded"
    )
  ) {
    _adFinished = true;

    const adModal = document.getElementById("ad-modal");
    if (adModal) {
      adModal.style.display = "none";
    }

    if (
      typeof _adCountdownInterval !== "undefined" &&
      _adCountdownInterval
    ) {
      clearInterval(_adCountdownInterval);
    }

    if (typeof overlay !== "undefined" && overlay) {
      overlay.classList.remove("active");
    }

    if (typeof stopGame === "function") {
      stopGame();
    }

    _analysisInFlight = false;

    // ───────────────────────────────────────────────────────────
    // AUTH REQUIRED
    // ───────────────────────────────────────────────────────────
    if (data.code === "auth_required") {

      await refreshAuthState();

      if (!_currentUser?.logged_in) {
        ouvrirAuthModal();
        return;
      }

      // Le frontend sait que l'utilisateur est connecté,
      // mais le backend affirme le contraire.
      console.warn(
        "auth_required alors que l'utilisateur est connecté",
        _currentUser
      );

      afficherErreurRiche({
        code: "unexpected",
        message:
          "Votre session est connectée mais le serveur demande encore une authentification."
      });

      return;
    }

    // ───────────────────────────────────────────────────────────
    // QUOTA EXCEEDED
    // ───────────────────────────────────────────────────────────
    await refreshAuthState();

    // IMPORTANT :
    // Un utilisateur Pelify Pro ne doit jamais être envoyé
    // vers le paywall simplement parce qu'une réponse quota_exceeded
    // a été reçue.
    if (_currentUser?.subscribed === true) {

      console.warn(
        "quota_exceeded reçu alors que Pelify Pro est actif.",
        _currentUser
      );

      afficherErreurRiche({
        code: "unexpected",
        message:
          "Votre abonnement Pelify Pro est actif, mais le serveur a renvoyé une erreur de quota. Réessayez."
      });

      return;
    }

    // Utilisateur gratuit → paywall
    ouvrirPaywallModal();
    return;
  }


  // ═══════════════════════════════════════════════════════════════
  // AUTRES ERREURS
  // ═══════════════════════════════════════════════════════════════
  if (data && data.status === "error") {

    _adFinished = true;

    const adModal = document.getElementById("ad-modal");
    if (adModal) {
      adModal.style.display = "none";
    }

    if (
      typeof _adCountdownInterval !== "undefined" &&
      _adCountdownInterval
    ) {
      clearInterval(_adCountdownInterval);
    }

    if (typeof overlay !== "undefined" && overlay) {
      overlay.classList.remove("active");
    }

    if (typeof stopGame === "function") {
      stopGame();
    }

    _analysisInFlight = false;

    afficherErreurRiche(data);

    return;
  }


  // ═══════════════════════════════════════════════════════════════
  // TRANSCRIPTION / OCR
  // ═══════════════════════════════════════════════════════════════
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

    const finalData = await _postAnalyserContinue(
      data.session_id,

      ocrText.status === "fulfilled"
        ? ocrText.value
        : "",

      transcript.status === "fulfilled"
        ? transcript.value
        : "",

      getBrowserLangShort(),

      signal,

      originalUrl
    );

    _afficherResultatFinal(finalData);

    _analysisInFlight = false;

    return;
  }


  // ═══════════════════════════════════════════════════════════════
  // RÉSULTAT FINAL
  // ═══════════════════════════════════════════════════════════════
  _analysisInFlight = false;

  _afficherResultatFinal(data);
}

function sleepWithAbort(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);

    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }

    signal?.addEventListener("abort", onAbort, { once: true });
  });
}


async function pollAnalysisStatus(
  sessionId,
  signal,
  maxDurationMs = 9 * 60 * 1000
) {
  const progressBar = document.getElementById("prog-fill");
  const percentLabel = document.getElementById("prog-percent");

  const startedAt = Date.now();

  let lastProgress = 88;
  let delayMs = 4000;
  let consecutiveErrors = 0;

  while (Date.now() - startedAt < maxDurationMs) {
    if (signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }

    // Quand l’utilisateur quitte temporairement l’onglet,
    // on espace davantage les requêtes.
    if (document.hidden) {
      await sleepWithAbort(15000, signal);
      continue;
    }

    try {
      /*
       * Ne pas utiliser fetchWithRetry ici.
       * La boucle de polling effectue déjà les nouvelles tentatives.
       */
      const res = await fetch(
        `/analyser_status/${encodeURIComponent(sessionId)}`,
        {
          method: "GET",
          headers: {
            "Accept": "application/json",
            "Cache-Control": "no-cache"
          },
          cache: "no-store",
          signal
        }
      );

      const data = await res.json().catch(() => null);

      if (!res.ok || !data) {
        throw new Error(`polling_http_${res.status}`);
      }

      consecutiveErrors = 0;

      let stepProgress = 88;

      if (data.step === "downloading") {
        stepProgress = 91;
      } else if (data.step === "processing") {
        stepProgress = 96;
      }

      if (progressBar && percentLabel) {
        const targetProgress = Math.min(stepProgress, 98);

        lastProgress = Math.max(lastProgress, targetProgress);

        progressBar.style.width = `${lastProgress}%`;
        percentLabel.textContent = `${Math.round(lastProgress)}%`;
      }

      // Dès qu’on n’est plus en traitement, on arrête immédiatement la boucle.
      if (data.status !== "processing") {
        if (data.status !== "error") {
          if (progressBar) {
            progressBar.style.width = "100%";
          }

          if (percentLabel) {
            percentLabel.textContent = "100%";
          }
        }

        return data;
      }

      /*
       * Le backend décide du délai :
       * queued      → 4 secondes
       * downloading → 5 secondes
       * processing  → 8 secondes
       */
      const serverDelay = Number(data.retry_after_ms);

      if (Number.isFinite(serverDelay)) {
        delayMs = Math.max(
          4000,
          Math.min(serverDelay, 15000)
        );
      } else {
        delayMs = Math.min(
          Math.round(delayMs * 1.5),
          12000
        );
      }

      await sleepWithAbort(delayMs, signal);

    } catch (e) {
      if (e.name === "AbortError") {
        throw e;
      }

      consecutiveErrors += 1;

      console.warn(
        `Erreur polling ${consecutiveErrors}/5 :`,
        e
      );

      if (consecutiveErrors >= 5) {
        return {
          status: "error",
          code: "server_busy",
          message: tErr("server_busy")
        };
      }

      await sleepWithAbort(
        Math.min(3000 * consecutiveErrors, 15000),
        signal
      );
    }
  }

  return {
    status: "error",
    code: "timeout",
    message: tErr("timeout")
  };
}
async function runLocalOCR(framesBase64) {
  try {
    if (!framesBase64 || !framesBase64.length) return "";

    await ensureTesseractReady();

    if (!window.Tesseract) {
      _analysisInFlight = false;
      return "";
    }

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
  ; cacherErreur();
  currentGenreName = genreName; currentPage = page;
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(`.btn-genre[href="/genre/${genreName}"]`)?.classList.add("active");

  const cacheKey = `genre_${genreName}_${page}_${getTMDBLang()}`;
  const cached = getCached(cacheKey);
  _hideAllPages();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
  // ⚠️ afficherNavCategoriesFilms() doit être appelé APRÈS _hideAllPages(),
  // sinon _hideAllPages() masque platform-nav juste après l'avoir rempli
  // (bug : la barre de catégories disparaissait au clic sur un genre).
  afficherNavCategoriesFilms(genreName);

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

 _hideAllPages();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
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
  _hideAllPages();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
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

 _hideAllPages();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";

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
  _hideAllPages();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
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
  _hideAllPages();
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("genre-nav").style.display="flex";
  document.getElementById("genre-title").innerText=`🔍 "${query}"`;
  lastGrid="search";navStack=[];
  renderCards(data.results||[],"search",1,1);
}




// ════ NOT FOUND ════
function afficherNotFound(data){
  _hideAllPages();
  document.getElementById("page-film-detail").style.display="block";
  document.getElementById("back-label").innerText=t("back_home");
  ["fake_alert","detail_tags","detail_rating","cast_section","trailer_section","similar_section","seasons_section"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  document.getElementById("confidence_wrap").style.display="none";
  document.getElementById("partner-offer")?.classList.remove("visible");
  document.getElementById("report-wrong-wrap").style.display = _cameFromAnalysis ? "block" : "none";
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
   _cameFromAnalysis = false; 
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
  ["synopsis_film","detail_tags","detail_rating","streaming_section","cast_section","trailer_section","similar_section","seasons_section","fake_alert","alternatives_section"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  ["crew_section","locations_section","finance_section","eidr_badge"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  document.getElementById("confidence_wrap").style.display="none";
  document.getElementById("partner-offer")?.classList.remove("visible");
}

async function telechargerVideo(url, btn) {
  if (!url || !url.trim()) {
    afficherErreur(t("err_generic") || "Collez un lien valide.");
    return;
  }
  const originalHtml = btn ? btn.innerHTML : null;
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }

  try {
    const res = await fetch("/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim(), format_id: "best", audio_only: false }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      afficherErreur(err.message || "Échec du téléchargement.");
      return;
    }

    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : "video.mp4";

    // Déclenche le téléchargement natif du navigateur
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    // "Supprime du frontend" : on libère immédiatement la mémoire (blob)
    // et l'élément temporaire — rien ne reste en mémoire ni dans le DOM
    // une fois le téléchargement lancé côté navigateur.
    URL.revokeObjectURL(a.href);
    a.remove();
  } catch (e) {
    afficherErreur("Erreur réseau pendant le téléchargement.");
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }
  }
}

function telechargerDepuisHero() {
  telechargerVideo(
    document.getElementById("hero-search-input").value,
    event.currentTarget
  );
}

function telechargerDepuisBarre() {
  telechargerVideo(
    document.getElementById("fixed-search-input").value,
    event.currentTarget
  );
}




function afficherDetailFilm(data) {
  _hideAllPages();
  document.getElementById("page-film-detail").style.display = "block";
  document.getElementById("report-wrong-wrap").style.display = _cameFromAnalysis ? "block" : "none"; // ← toujours nécessaire, cf. bug précédent
  document.getElementById("back-label").innerText = lastGrid ? t("back_list") : t("back_home");
   document.getElementById("report-wrong-wrap").style.display = _cameFromAnalysis ? "block" : "none";

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
  // ─── ALTERNATIVES (multi-candidats) ──────────────────────────
const altEl = document.getElementById("alternatives_section");

if (altEl) {
  if (
    data.needs_confirmation &&
    Array.isArray(data.alternatives) &&
    data.alternatives.length > 0
  ) {
    altEl.style.display = "block";
    afficherAlternatives(altEl, data.alternatives);
  } else {
    altEl.innerHTML = "";
    altEl.style.display = "none";
  }
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

 
  // ─── OFFRE PARTENAIRE (Amazon + programmes Awin géociblés) ──────
  const partnerEl = document.getElementById("partner-offer");
  if (partnerEl) {
    const offer = getRandomPartnerOffer();
    partnerEl.classList.add("visible");
    const iconEl = document.getElementById("partner-offer-icon");
    const descEl = document.getElementById("partner-offer-desc");
    const btnEl  = document.getElementById("partner-offer-btn");
    const btnLbl = document.getElementById("partner-offer-btn-label");
    if (iconEl) {
      if (offer.image) {
        iconEl.innerHTML = `<img src="${offer.image}" alt="${escapeHtml(offer.title)}" style="max-height:2rem;max-width:80px;border-radius:4px" onerror="this.parentElement.textContent='${offer.icon}'">`;
      } else {
        iconEl.textContent = offer.icon;
      }
    }
    if (descEl) descEl.textContent = offer.desc;
    if (btnLbl) btnLbl.textContent = offer.cta;
    if (btnEl) btnEl.onclick = () => window.open(offer.url, "_blank", "noopener");
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



function afficherAlternatives(container, alternatives) {
  const lbl =
    currentLang === "es" ? "¿No es la película correcta? También podría ser:" :
    currentLang === "de" ? "Nicht der richtige Film? Es könnte auch sein:" :
    currentLang === "zh" ? "不是这部电影？也可能是：" :
    currentLang.startsWith("en") ? "Not the right movie? It could also be:" :
    "Ce n'est pas le bon film ? Ça pourrait aussi être :";

  const placeholder =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='154' height='231' fill='%231a1a24'%3E%3Crect width='154' height='231'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='24' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";

  const cards = alternatives.map(alt => {
    const poster = alt.poster_path
      ? `https://image.tmdb.org/t/p/w154${alt.poster_path}`
      : placeholder;
    const year = alt.year || "";
    const pct = Math.round(alt.confidence || 0);
    return `
      <div class="alt-card" onclick="choisirAlternative(${alt.id},'${alt.media_type || "movie"}')" role="button" tabindex="0">
        <img src="${poster}" alt="${escapeHtml(alt.title || "")}" loading="lazy">
        <div class="alt-card-body">
          <strong>${escapeHtml(alt.title || "?")}</strong>
          <span class="alt-card-meta">${year ? year + " · " : ""}${pct}%</span>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="alternatives-block">
      <p class="alternatives-label"><i class="fas fa-question-circle"></i> ${lbl}</p>
      <div class="alternatives-list">${cards}</div>
    </div>
  `;
}

function choisirAlternative(id, mediaType) {
  afficherDetails(id, mediaType);
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
// ════ CONFIG PUBS ALTERNÉES ════
// ════ OFFRES PARTENAIRES GÉOCIBLÉES (Amazon + programmes Awin) ════

function getAmazonPrimeOffer() {
  const domain = AMAZON_DOMAINS[_detectCountry()] || "www.amazon.com";
  const isEN = currentLang.startsWith("en");
  return {
    icon: "🎬",
    title: "Amazon Prime Video",
    desc: isEN ? "30-day free trial — Thousands of movies & shows" : "30 jours gratuits — Des milliers de films et séries",
    cta: isEN ? "Try free →" : "Essayer gratuitement →",
    url: `https://${domain}/amazonprime?tag=${_amazonTag(domain)}`,
  };
}
// ════ DÉTECTION PAYS — indépendante d'AMAZON_DOMAINS ════
function _detectCountry(){
  for (const l of (navigator.languages || [navigator.language || ""])) {
    const m = l.toUpperCase().match(/-([A-Z]{2})$/);
    if (m) return m[1];
  }
  const uiToCC = { fr:"FR", es:"ES", de:"DE", "en-GB":"GB", "en-US":"US", zh:"CN" };
  return uiToCC[currentLang] || "US";
}
// Chaque programme Awin approuvé va ici, rangé par code pays ISO.
// Un pays peut avoir plusieurs offres — elles seront mises en rotation
// aléatoire entre elles (et avec Amazon) automatiquement.
// Pour ajouter un nouveau programme : ajoute un objet dans le tableau
// du bon pays, ou crée une nouvelle clé pays si besoin.
// ════ OFFRES PARTENAIRES GÉOCIBLÉES — AVEC EARFUN + HTVRONT ════
// Remplace intégralement ta constante AWIN_OFFERS_BY_COUNTRY par ce bloc.
// Offres approuvées pour TOUS les pays (fusionnées avec l'offre du pays
// détecté dans getPartnerOffers()). Utile pour les programmes multi-pays
// ou, comme ici, quand on choisit sciemment de diffuser au-delà de la
// zone de vente officielle du programme.
const AWIN_OFFERS_GLOBAL = [
  {
    icon: "🎓",
    title: "Alison",
    desc: "Cours en ligne gratuits et certifiants — plus de 6000 formations",
    cta: "Découvrir →",
    url: "https://www.awin1.com/cread.php?s=4549507&v=120101&q=584470&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=4549507&v=120101&q=584470&r=2932851"
  },
];
const AWIN_OFFERS_BY_COUNTRY = {
  DE: [
    { icon: "💪", title: "PROGRAMM 21", desc: "21 Tage. 21 Minuten. 21 Lebensmittel.", cta: "Entdecken →", url: "https://www.awin1.com/awclick.php?gid=606436&mid=127263&awinaffid=2932851&linkid=4793651&clickref=pelify" },
    { icon: "🏺", title: "Casa Moro", desc: "5% Rabatt — Marokkanisches Wohndesign & Beleuchtung", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=3190082&v=31431&q=442216&r=2932851", image: "https://www.awin1.com/cshow.php?s=3190082&v=31431&q=442216&r=2932851" },
    { icon: "🎯", title: "Snipster", desc: "Cool bleiben. Clever bieten.", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=2526726&v=17469&q=377673&r=2932851", image: "https://www.awin1.com/cshow.php?s=2526726&v=17469&q=377673&r=2932851" },
    { icon: "🔒", title: "FastestVPN", desc: "Sicheres, privates Surfen — 256-Bit-Verschlüsselung", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Preisgekrönte kabellose Kopfhörer & Lautsprecher", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV-Vinyl, Klebefolien, Maschinen und Werkzeuge für kreative DIY-Projekte", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Smartring für Schlaf, Erholung, HRV, Hauttemperatur und Stress — ohne Abo",
  cta: "Entdecken →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
}
  
  ],

 FR: [
  
    { icon: "💡", title: "Éclairage Déco", desc: "Lustres, suspensions et luminaires design haut de gamme", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4826404&v=128237&q=608878&r=2932851", image: "https://www.awin1.com/cshow.php?s=4826404&v=128237&q=608878&r=2932851" },
    { icon: "💡", title: "Éclairage Déco", desc: "Lustres, suspensions et luminaires design haut de gamme", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4826404&v=128237&q=608878&r=2932851", image: "https://www.awin1.com/cshow.php?s=4826404&v=128237&q=608878&r=2932851" },
    { icon: "💡", title: "Éclairage Déco", desc: "Lustres, suspensions et luminaires design haut de gamme", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4826404&v=128237&q=608878&r=2932851", image: "https://www.awin1.com/cshow.php?s=4826404&v=128237&q=608878&r=2932851" },
    { icon: "🛒", title: "AliExpress FR", desc: "Des millions de produits à prix direct usine", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=3775159&v=26009&q=501388&r=2932851", image: "https://www.awin1.com/cshow.php?s=3775159&v=26009&q=501388&r=2932851" },
    { icon: "🛋️", title: "Moskera", desc: "Mobilier et décoration d'intérieur", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4814317&v=128253&q=608010&r=2932851", image: "https://www.awin1.com/cshow.php?s=4814317&v=128253&q=608010&r=2932851" },
    { icon: "🔒", title: "FastestVPN", desc: "Navigation privée et sécurisée — chiffrement 256 bits", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Écouteurs et enceintes sans fil primés", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "Machines, vinyles HTV, vinyles adhésifs et outils créatifs pour personnaliser vos projets", cta: "Découvrir →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
    {
      icon: "💍",
      title: "Ultrahuman",
      desc: "Bague connectée pour suivre sommeil, récupération, VFC, température et stress, sans abonnement",
      cta: "Découvrir →",
      url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
      image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
    }
  ],

  AU: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  AT: [
    { icon: "🔒", title: "FastestVPN", desc: "Sicheres, privates Surfen — 256-Bit-Verschlüsselung", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Preisgekrönte kabellose Kopfhörer & Lautsprecher", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV-Vinyl, Klebefolien, Maschinen und Werkzeuge für kreative DIY-Projekte", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  BE: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  BR: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegação segura e privada — criptografia de 256 bits", cta: "Descobrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Fones de ouvido e caixas de som sem fio premiados", cta: "Descobrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anel inteligente para sono, recuperação, VFC, temperatura da pele e stress, sem assinatura",
  cta: "Descobrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  
  ],

  CA: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  IN: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  IE: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  IT: [
    { icon: "🔒", title: "FastestVPN", desc: "Navigazione sicura e privata — crittografia a 256 bit", cta: "Scopri →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auricolari e speaker wireless pluripremiati", cta: "Scopri →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "Vinile HTV, vinile adesivo, macchine e strumenti per progetti creativi", cta: "Scopri →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anello smart per sonno, recupero, HRV, temperatura cutanea e stress, senza abbonamento",
  cta: "Scopri →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
}
  ],

  JP: [
    { icon: "🔒", title: "FastestVPN", desc: "安全でプライベートなブラウジング — 256ビット暗号化", cta: "詳しく見る →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "受賞歴のあるワイヤレスイヤホン＆スピーカー", cta: "詳しく見る →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  MX: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación segura y privada — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  NL: [
    { icon: "🔒", title: "FastestVPN", desc: "Veilig en privé browsen — 256-bit encryptie", cta: "Ontdekken →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Bekroonde draadloze oordopjes & speakers", cta: "Ontdekken →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV-vinyl, zelfklevend vinyl, machines en tools voor creatieve projecten", cta: "Ontdekken →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  PL: [
    { icon: "🔒", title: "FastestVPN", desc: "Bezpieczne, prywatne przeglądanie — szyfrowanie 256-bit", cta: "Odkryj →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Nagradzane słuchawki bezprzewodowe i głośniki", cta: "Odkryj →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "Folie HTV, winyle samoprzylepne, maszyny i narzędzia do projektów kreatywnych", cta: "Odkryj →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  SG: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  ES: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación privada y segura — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "Vinilo HTV, vinilo adhesivo, máquinas y herramientas para proyectos creativos", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
 {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  SE: [
    { icon: "🔒", title: "FastestVPN", desc: "Säker, privat surfning — 256-bitars kryptering", cta: "Upptäck →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Prisbelönta trådlösa hörlurar & högtalare", cta: "Upptäck →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  TR: [
    { icon: "🔒", title: "FastestVPN", desc: "Güvenli, gizli tarama — 256-bit şifreleme", cta: "Keşfet →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Ödüllü kablosuz kulaklık ve hoparlörler", cta: "Keşfet →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  AE: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  GB: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
   { icon: "🅿️", title: "Park BCP", desc: "UK airport parking — book ahead and save", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=2261238&v=3495&q=348156&r=2932851", image: "https://www.awin1.com/cshow.php?s=2261238&v=3495&q=348156&r=2932851" },
    {
  icon: "🧱",
  title: "brickzonehub",
  desc: "Custom LEGO® display frames, acrylic cases and stands for fan-favourite themes.",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4589784&v=121692&q=586383&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4589784&v=121692&q=586383&r=2932851"
},
{
  icon: "🧱",
  title: "brickzonehub",
  desc: "Custom LEGO® display frames, acrylic cases and stands for fan-favourite themes.",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4731406&v=121692&q=586383&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4731406&v=121692&q=586383&r=2932851"
},
{
  icon: "🧱",
  title: "brickzonehub",
  desc: "Custom LEGO® display frames, acrylic cases and stands for fan-favourite themes.",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4731454&v=121692&q=586383&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4731454&v=121692&q=586383&r=2932851"
},
{
  icon: "🧱",
  title: "brickzonehub",
  desc: "Custom LEGO® display frames, acrylic cases and stands for fan-favourite themes.",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4731442&v=121692&q=586383&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4731442&v=121692&q=586383&r=2932851"
},
{
  icon: "🧱",
  title: "brickzonehub",
  desc: "Custom LEGO® display frames, acrylic cases and stands for fan-favourite themes.",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4731456&v=121692&q=586383&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4731456&v=121692&q=586383&r=2932851"
}
  ],

  US: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
 {
  icon: "🌷",
  title: "AirTulip",
  desc: "Système haut de gamme intégré à la tête de lit, créant une zone d’air purifié ciblée autour de l’oreiller grâce à un flux d’air laminaire. Idéal pour améliorer la qualité de l’air pendant le sommeil, notamment pour les personnes sensibles aux particules et aux allergènes. Disponible aux États-Unis.",
  cta: "Découvrir →",
  url: "https://www.awin1.com/cread.php?s=4825485&v=128289&q=608799&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4825485&v=128289&q=608799&r=2932851"
},
    { icon: "🎧", title: "ISOtunes", desc: "Protection auditive connectée pour le travail", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4705778&v=124690&q=598598&r=2932851", image: "https://www.awin1.com/cshow.php?s=4705778&v=124690&q=598598&r=2932851" },
    {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Smart ring for sleep, recovery, HRV, skin temperature and stress tracking, with no subscription",
  cta: "Discover →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
 
  ],

  AR: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación segura y privada — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  CL: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación segura y privada — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  CN: [
    { icon: "🔒", title: "FastestVPN", desc: "安全私密浏览 — 256位加密", cta: "了解更多 →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "屡获殊荣的无线耳机与音箱", cta: "了解更多 →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "智能戒指，用于睡眠、恢复、HRV、皮肤温度和压力追踪，无需订阅",
  cta: "了解更多 →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  
  ],

  CO: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación segura y privada — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  DK: [
    { icon: "🔒", title: "FastestVPN", desc: "Sikker, privat browsing — 256-bit kryptering", cta: "Opdag →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Prisvindende trådløse hovedtelefoner & højttalere", cta: "Opdag →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  FI: [
    { icon: "🔒", title: "FastestVPN", desc: "Turvallinen, yksityinen selailu — 256-bitin salaus", cta: "Tutustu →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Palkitut langattomat kuulokkeet ja kaiuttimet", cta: "Tutustu →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  NO: [
    { icon: "🔒", title: "FastestVPN", desc: "Sikker, privat nettlesing — 256-bit kryptering", cta: "Oppdag →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Prisvinnende trådløse hodetelefoner & høyttalere", cta: "Oppdag →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  PT: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegação segura e privada — encriptação de 256 bits", cta: "Descobrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auscultadores e colunas sem fios premiados", cta: "Descobrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "Vinil HTV, vinil adesivo, máquinas e ferramentas para projetos criativos", cta: "Descobrir →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anel inteligente para sono, recuperação, VFC, temperatura da pele e stress, sem assinatura",
  cta: "Descobrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  ],

  RU: [
    { icon: "🔒", title: "FastestVPN", desc: "Безопасный, приватный просмотр — 256-битное шифрование", cta: "Узнать →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Отмеченные наградами беспроводные наушники и колонки", cta: "Узнать →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  CH: [
    { icon: "🔒", title: "FastestVPN", desc: "Sicheres, privates Surfen — 256-Bit-Verschlüsselung", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Preisgekrönte kabellose Kopfhörer & Lautsprecher", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV-Vinyl, Klebefolien, Maschinen und Werkzeuge für kreative DIY-Projekte", cta: "Entdecken →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  UA: [
    { icon: "🔒", title: "FastestVPN", desc: "Безпечний, приватний перегляд — 256-бітне шифрування", cta: "Дізнатись →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Відзначені нагородами бездротові навушники та колонки", cta: "Дізнатись →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  HR: [
    { icon: "🔒", title: "FastestVPN", desc: "Sigurno, privatno pregledavanje — 256-bitna enkripcija", cta: "Otkrij →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Nagrađivane bežične slušalice i zvučnici", cta: "Otkrij →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  CZ: [
    { icon: "🔒", title: "FastestVPN", desc: "Bezpečné, soukromé prohlížení — 256bitové šifrování", cta: "Objevit →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Oceňovaná bezdrátová sluchátka a reproduktory", cta: "Objevit →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  GR: [
    { icon: "🔒", title: "FastestVPN", desc: "Ασφαλής, ιδιωτική περιήγηση — κρυπτογράφηση 256-bit", cta: "Ανακάλυψε →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Βραβευμένα ασύρματα ακουστικά και ηχεία", cta: "Ανακάλυψε →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  HU: [
    { icon: "🔒", title: "FastestVPN", desc: "Biztonságos, privát böngészés — 256 bites titkosítás", cta: "Fedezd fel →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Díjnyertes vezeték nélküli fülhallgatók és hangszórók", cta: "Fedezd fel →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  LV: [
    { icon: "🔒", title: "FastestVPN", desc: "Droša, privāta pārlūkošana — 256 bitu šifrēšana", cta: "Atklāt →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Balvu ieguvušas bezvadu austiņas un skaļruņi", cta: "Atklāt →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  LT: [
    { icon: "🔒", title: "FastestVPN", desc: "Saugus, privatus naršymas — 256 bitų šifravimas", cta: "Sužinoti →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Apdovanotos belaidės ausinės ir garsiakalbiai", cta: "Sužinoti →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  NZ: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  PE: [
    { icon: "🔒", title: "FastestVPN", desc: "Navegación segura y privada — cifrado de 256 bits", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Auriculares y altavoces inalámbricos galardonados", cta: "Descubrir →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  {
  icon: "💍",
  title: "Ultrahuman",
  desc: "Anillo inteligente para sueño, recuperación, VFC, temperatura cutánea y estrés, sin suscripción",
  cta: "Descubrir →",
  url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
  image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
},
  
  ]
  ,

  RO: [
    { icon: "🔒", title: "FastestVPN", desc: "Navigare sigură și privată — criptare pe 256 de biți", cta: "Descoperă →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Căști și boxe wireless premiate", cta: "Descoperă →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  SK: [
    { icon: "🔒", title: "FastestVPN", desc: "Bezpečné, súkromné prehliadanie — 256-bitové šifrovanie", cta: "Objaviť →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Ocenené bezdrôtové slúchadlá a reproduktory", cta: "Objaviť →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  SI: [
    { icon: "🔒", title: "FastestVPN", desc: "Varno, zasebno brskanje — 256-bitno šifriranje", cta: "Odkrij →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Nagrajene brezžične slušalke in zvočniki", cta: "Odkrij →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],

  ZA: [
    { icon: "🔒", title: "FastestVPN", desc: "Secure, private browsing — 256-bit encryption", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Award-winning wireless earbuds & speakers", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
  ],

  BG: [
    { icon: "🔒", title: "FastestVPN", desc: "Сигурно, лично сърфиране — 256-битово криптиране", cta: "Открий →", url: "https://www.awin1.com/cread.php?s=4590561&v=90211&q=566685&r=2932851", image: "https://www.awin1.com/cshow.php?s=4590561&v=90211&q=566685&r=2932851" },
    { icon: "🎧", title: "EarFun", desc: "Наградени безжични слушалки и колони", cta: "Открий →", url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851", image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851" },
    { icon: "🎨", title: "HTVRont", desc: "HTV vinyl, adhesive vinyl, machines and crafting tools for creative DIY projects", cta: "Discover →", url: "https://www.awin1.com/cread.php?s=4819183&v=68106&q=523805&r=2932851", image: "https://www.awin1.com/cshow.php?s=4819183&v=68106&q=523805&r=2932851" },
  ],
};


// ════ EARFUN — 3 VISUELS AWIN POUR ROTATION A/B ════
const EARFUN_CREATIVES = [
  {
    ab: "earfun-a",
    url: "https://www.awin1.com/cread.php?s=3996847&v=61233&q=525399&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=3996847&v=61233&q=525399&r=2932851"
  },
  {
    ab: "earfun-b",
    url: "https://www.awin1.com/cread.php?s=3996845&v=61233&q=525399&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=3996845&v=61233&q=525399&r=2932851"
  },
  {
    ab: "earfun-c",
    url: "https://www.awin1.com/cread.php?s=3996846&v=61233&q=525399&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=3996846&v=61233&q=525399&r=2932851"
  }
];

// ════ ULTRAHUMAN — 3 VISUELS AWIN POUR ROTATION A/B ════
const ULTRAHUMAN_CREATIVES = [
  {
    ab: "ultrahuman-a",
    url: "https://www.awin1.com/cread.php?s=4052116&v=69428&q=531112&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=4052116&v=69428&q=531112&r=2932851"
  },
  {
    ab: "ultrahuman-b",
    url: "https://www.awin1.com/cread.php?s=4052112&v=69428&q=531112&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=4052112&v=69428&q=531112&r=2932851"
  },
  {
    ab: "ultrahuman-c",
    url: "https://www.awin1.com/cread.php?s=4052111&v=69428&q=531112&r=2932851",
    image: "https://www.awin1.com/cshow.php?s=4052111&v=69428&q=531112&r=2932851"
  }
];

function expandUltrahumanCreatives(offers) {
  return offers.flatMap(offer => {
    if (!offer || offer.title !== "Ultrahuman") return [offer];

    return ULTRAHUMAN_CREATIVES.map(creative => ({
      ...offer,
      url: creative.url,
      image: creative.image,
      ab: creative.ab
    }));
  });
}

function expandEarFunCreatives(offers) {
  return offers.flatMap(offer => {
    if (!offer || offer.title !== "EarFun") return [offer];

    return EARFUN_CREATIVES.map(creative => ({
      ...offer,
      url: creative.url,
      image: creative.image,
      ab: creative.ab
    }));
  });
}
function getPartnerOffers() {
  const cc = _detectCountry();
  const awinOffers = [
    ...(AWIN_OFFERS_BY_COUNTRY[cc] || []),
    ...AWIN_OFFERS_GLOBAL,   // ← offres diffusées quel que soit le pays détecté
  ];

  // EarFun : transforme 1 offre en 3 variantes visuelles
  const withEarFunVariants = expandEarFunCreatives(awinOffers);

  // Ultrahuman : transforme 1 offre en 3 variantes visuelles
  const withUltrahumanVariants = expandUltrahumanCreatives(withEarFunVariants);

  return [getAmazonPrimeOffer(), ...withUltrahumanVariants];
}

function getRandomPartnerOffer() {
  const offers = getPartnerOffers();
  return offers[Math.floor(Math.random() * offers.length)];
}

function _renderAdContent() {
  const variant = getRandomPartnerOffer();
  const el = document.getElementById("ad-content-dynamic");
  if (!el) return;
  const iconHtml = variant.image
    ? `<img src="${variant.image}" alt="${variant.title}" style="max-width:100%;border-radius:8px" onerror="this.outerHTML='<div style=\\'font-size:2.5rem\\'>${variant.icon}</div>'">`
    : `<div style="font-size: 2.5rem">${variant.icon}</div>`;
  el.innerHTML = `
    <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 12px; padding: 24px; margin-bottom: 16px;">
      <div style="margin-bottom: 12px">${iconHtml}</div>
      <h3 style="color: var(--primary); margin: 0 0 8px; font-size: 1.1rem">${variant.title}</h3>
      <p style="color: var(--muted); font-size: 0.85rem; margin: 0 0 16px">${variant.desc}</p>
      <a href="${variant.url}" target="_blank" rel="sponsored noopener" onclick="fermerPub()"
         style="display: inline-block; background: var(--primary); color: #000; padding: 10px 24px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 0.9rem;">
        ${variant.cta}
      </a>
    </div>
  `;
}

// ════ BANNIÈRE BAS DE PAGE — rotation automatique des offres ════
let _bannerBottomInterval = null;
let _bannerBottomIndex = 0;

function initBannerBottom() {
  const link = document.getElementById("banner-bottom-link");
  const text = document.getElementById("banner-bottom-text");
  if (!link || !text) return;

  const offers = getPartnerOffers();
  if (!offers.length) return;

  _bannerBottomIndex = 0;
  _renderBannerBottomOffer(offers[_bannerBottomIndex], link, text);

  if (_bannerBottomInterval) clearInterval(_bannerBottomInterval);

  if (offers.length <= 1) return;

  _bannerBottomInterval = setInterval(() => {
    const banner = document.getElementById("banner-bottom");
    if (!banner || banner.style.display === "none") {
      clearInterval(_bannerBottomInterval);
      _bannerBottomInterval = null;
      return;
    }
    _bannerBottomIndex = (_bannerBottomIndex + 1) % offers.length;
    _renderBannerBottomOffer(offers[_bannerBottomIndex], link, text);
  }, 8000);
}

function _renderBannerBottomOffer(offer, link, text) {
  text.style.transition = "opacity 0.3s";
  text.style.opacity = "0";
  setTimeout(() => {
    link.href = offer.url;
    text.innerHTML = `${offer.icon} <strong>${escapeHtml(offer.title)}</strong> — ${escapeHtml(offer.desc)}`;
    text.style.opacity = "1";
  }, 300);
}
function demarrerPub(){
  const modal=document.getElementById('ad-modal'),closeBtn=document.getElementById('ad-close-btn'),countdown=document.getElementById('ad-countdown');
  if(!modal)return;
  _renderAdContent();
  _adFinished=false;modal.style.display='flex';closeBtn.disabled=true;closeBtn.style.background='rgba(255,255,255,0.1)';closeBtn.style.color='var(--text)';
  let seconds=15;countdown.textContent=seconds;
  const switchAt = Math.floor(seconds / 2);   // ← bascule à mi-parcours
  _adCountdownInterval=setInterval(()=>{
    seconds--;
    countdown.textContent=seconds;
    if (seconds === switchAt) _renderAdContent();   // ← affiche une nouvelle offre
    if(seconds<=0){
      clearInterval(_adCountdownInterval);
      closeBtn.disabled=false;countdown.textContent='✕';
      closeBtn.style.background='rgba(0,255,204,0.2)';closeBtn.style.color='var(--primary)';
      _publicitéTerminée();
    }
  },1000);
}
function fermerPub(){const closeBtn=document.getElementById('ad-close-btn');if(closeBtn&&closeBtn.disabled)return;clearInterval(_adCountdownInterval);_publicitéTerminée();}
function _publicitéTerminée(){_adFinished=true;const modal=document.getElementById('ad-modal');if(modal)modal.style.display='none';if(_analysisResult!==null){_afficherResultatFinal(_analysisResult);_analysisResult=null;}}
function _afficherResultatFinal(data){
  if(!_adFinished){
    _analysisResult=data;
    // Filet de sécurité : si pour une raison quelconque le mécanisme
    // normal de fin de pub (_publicitéTerminée, appelé au clic ou
    // automatiquement à 15s) ne se déclenche jamais — élément DOM
    // manquant, changement de page entre-temps, etc. — on force
    // quand même l'affichage après un délai raisonnable, plutôt que
    // de laisser l'utilisateur bloqué indéfiniment sans autre
    // solution que d'annuler et relancer la même analyse.
    setTimeout(() => {
      if (_analysisResult !== null && !_adFinished) {
        _adFinished = true;
        const modal = document.getElementById('ad-modal');
        if (modal) modal.style.display = 'none';
        clearInterval(_adCountdownInterval);
        const donnees = _analysisResult;
        _analysisResult = null;
        _afficherResultatFinal(donnees);
      }
    }, 16000);
    return;
  }
   _cameFromAnalysis = true;
  _correctionTranscript = data._transcript || "";
  _correctionOcr = data._ocr_text || "";
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
async function chargerEnrichissementWikidata(tmdb_id, media_type = "movie") {
  const sections = {
    crew: document.getElementById("crew_section"),
    locations: document.getElementById("locations_section"),
    finance: document.getElementById("finance_section"),
    eidr: document.getElementById("eidr_badge")
  };

  if (sections.crew) {
    sections.crew.innerHTML = `
      <div class="wd-loading">
        <i class="fas fa-circle-notch fa-spin"></i>
        <span style="color:var(--muted);font-size:.82rem">
          Chargement équipe créative…
        </span>
      </div>
    `;
  }

  if (sections.locations) {
    sections.locations.innerHTML = `
      <div class="wd-loading">
        <i class="fas fa-circle-notch fa-spin"></i>
        <span style="color:var(--muted);font-size:.82rem">
          Chargement des lieux de tournage…
        </span>
      </div>
    `;
  }

  try {
    const [wdData, locData] = await Promise.allSettled([
      safeFetch(`/movie/${tmdb_id}/wikidata?type=${media_type}`),
      safeFetch(`/movie/${tmdb_id}/locations?type=${media_type}`)
    ]);

    const wd = wdData.status === "fulfilled" ? wdData.value : null;
    const loc = locData.status === "fulfilled" ? locData.value : null;

    if (sections.crew) {
      afficherCrewWikidata(sections.crew, wd);
    }

    if (sections.finance) {
      afficherFinanceWikidata(sections.finance, wd);
    }

    if (sections.locations) {
      afficherTourismeTournage(
        sections.locations,
        loc?.locations || [],
        wd?.locations || [],
        { tmdb_id, media_type }
      );
    }

    if (sections.eidr && wd?.eidr_id) {
      sections.eidr.innerHTML = `
        <span class="eidr-badge" title="Identifiant EIDR standard industrie audiovisuelle">
          <i class="fas fa-fingerprint"></i>
          EIDR <code>${wd.eidr_id}</code>
        </span>
      `;
      sections.eidr.style.display = "flex";
    }
  } catch (e) {
    console.warn("Wikidata enrichment KO:", e);

    if (sections.crew) sections.crew.innerHTML = "";
    if (sections.finance) sections.finance.innerHTML = "";
    if (sections.locations) sections.locations.innerHTML = "";
  }
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
  if (p === "/lieux-de-tournage")               { window.location.href = "https://tournage.pelify.app/"; return true; }

  return false;
}




window.onload=()=>{
  initLang();
  initBannerBottom();
  refreshAuthState();
  (()=>{
    const params=new URLSearchParams(location.search);
    const billing=params.get("billing");
    if(billing==="success"){toast(t("billing_success"));history.replaceState({},"",location.pathname);}
    else if(billing==="cancel"){history.replaceState({},"",location.pathname);}
  })();
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