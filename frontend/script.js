// ════════════════════════════════════════════════
// SHADOWFRAME – QUEL FILM ? – JavaScript complet
// ════════════════════════════════════════════════

// ════ DICTIONNAIRE INTERNATIONAL ════
const dict = {
  "en-US": {
    title: "WHICH MOVIE?",
    tagline: "Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder: "Paste TikTok/Insta link or type a movie name...",
    badge: "Shazam for movies",
    back_home: "Home",
    back_list: "Back to list",
    ai_conf: "AI Confidence",
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
    food_title: "Ready to watch?",
    food_desc: "Order popcorn & snacks via DoorDash!",
    food_btn: "Order",
    streaming_title: "Available on",
    searching: "Manual search",
    loading_home: "Loading trending...",
    not_found_title: "Movie not found",
    similar_title: "🍿 Similar movies",
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
    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Comedy",
      scifi: "Sci-Fi",
      trending: "🔥 Trending",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crime",
      documentary: "Documentary",
      fantasy: "Fantasy",
      series: "📺 TV Series",
      family: "Family"
    }
  },
  "en-GB": {
    title: "WHICH MOVIE?",
    tagline: "Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder: "Paste TikTok/Insta link or type a movie name...",
    badge: "Shazam for movies",
    back_home: "Home",
    back_list: "Back to list",
    ai_conf: "AI Confidence",
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
    food_title: "Ready to watch?",
    food_desc: "Order popcorn & snacks via Deliveroo!",
    food_btn: "Order",
    streaming_title: "Available on",
    searching: "Manual search",
    loading_home: "Loading trending...",
    not_found_title: "Movie not found",
    similar_title: "🍿 Similar movies",
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
    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Comedy",
      scifi: "Sci-Fi",
      trending: "🔥 Trending",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crime",
      documentary: "Documentary",
      fantasy: "Fantasy",
      series: "📺 TV Series",
      family: "Family"
    }
  },
  fr: {
    title: "QUEL FILM ?",
    tagline: "Colle un lien TikTok, Reel ou YouTube — l'IA identifie le film en secondes",
    placeholder: "Colle un lien TikTok/Reel ou tape le nom d'un film...",
    badge: "Shazam pour les films",
    back_home: "Accueil",
    back_list: "Retour à la liste",
    ai_conf: "Confiance IA",
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
    food_title: "Prêt à regarder ce film ?",
    food_desc: "Commandez vos snacks via UberEats !",
    food_btn: "Commander",
    streaming_title: "Disponible sur",
    searching: "Recherche manuelle",
    loading_home: "Chargement des tendances...",
    not_found_title: "Film non identifié",
    similar_title: "🍿 Films similaires",
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
    genres: {
      horror: "Horreur",
      action: "Action",
      comedy: "Comédie",
      scifi: "Sci-Fi",
      trending: "🔥 Tendances",
      romance: "Romance",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drame",
      crime: "Crime",
      documentary: "Documentaire",
      fantasy: "Fantastique",
      series: "📺 Séries TV",
      family: "Famille"
    }
  },
  es: {
    title: "¿QUÉ PELÍCULA?",
    tagline: "Pega un enlace de TikTok o Reel — la IA identifica la película",
    placeholder: "Pega enlace TikTok/Reel o escribe un título...",
    badge: "Shazam para películas",
    back_home: "Inicio",
    back_list: "Volver a la lista",
    ai_conf: "Confianza IA",
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
    food_title: "¿Listo para ver la película?",
    food_desc: "¡Pide snacks y palomitas!",
    food_btn: "Pedir",
    streaming_title: "Disponible en",
    searching: "Buscar manualmente",
    loading_home: "Cargando tendencias...",
    not_found_title: "Película no encontrada",
    similar_title: "🍿 Películas similares",
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
    genres: {
      horror: "Terror",
      action: "Acción",
      comedy: "Comedia",
      scifi: "Ciencia Ficción",
      trending: "🔥 Tendencias",
      romance: "Romance",
      animation: "Animación",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Crimen",
      documentary: "Documental",
      fantasy: "Fantasía",
      series: "📺 Series TV",
      family: "Familia"
    }
  },
  de: {
    title: "WELCHER FILM?",
    tagline: "TikTok- oder Reel-Link einfügen — KI erkennt den Film in Sekunden",
    placeholder: "TikTok/Insta Link oder Filmtitel eingeben...",
    badge: "Shazam für Filme",
    back_home: "Startseite",
    back_list: "Zurück zur Liste",
    ai_conf: "KI-Konfidenz",
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
    food_title: "Bereit zum Anschauen?",
    food_desc: "Bestelle Snacks und Popcorn!",
    food_btn: "Bestellen",
    streaming_title: "Verfügbar auf",
    searching: "Manuell suchen",
    loading_home: "Trends werden geladen...",
    not_found_title: "Film nicht gefunden",
    similar_title: "🍿 Ähnliche Filme",
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
    genres: {
      horror: "Horror",
      action: "Action",
      comedy: "Komödie",
      scifi: "Science-Fiction",
      trending: "🔥 Trends",
      romance: "Romantik",
      animation: "Animation",
      thriller: "Thriller",
      drama: "Drama",
      crime: "Krimi",
      documentary: "Dokumentarfilm",
      fantasy: "Fantasy",
      series: "📺 TV-Serien",
      family: "Familie"
    }
  },
  zh: {
    title: "什么电影？",
    tagline: "粘贴 TikTok 或 Reel 链接 — AI 即刻识别电影",
    placeholder: "粘贴链接或输入电影名...",
    badge: "电影识别神器",
    back_home: "首页",
    back_list: "返回列表",
    ai_conf: "AI 置信度",
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
    food_title: "准备好看电影了吗？",
    food_desc: "立即订购爆米花和零食！",
    food_btn: "下单",
    streaming_title: "可在以下平台观看",
    searching: "手动搜索",
    loading_home: "加载热门中...",
    not_found_title: "未找到影片",
    similar_title: "🍿 相似影片",
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
    genres: {
      horror: "恐怖",
      action: "动作",
      comedy: "喜剧",
      scifi: "科幻",
      trending: "🔥 热门",
      romance: "爱情",
      animation: "动画",
      thriller: "惊悚",
      drama: "剧情",
      crime: "犯罪",
      documentary: "纪录片",
      fantasy: "奇幻",
      series: "📺 电视剧",
      family: "家庭"
    }
  }
};

// ════ CONFIG STREAMING ════
const STREAMING_META = {
  Netflix: { color: "#e50914", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/24px-Netflix_2015_logo.svg.png" },
  "Amazon Prime Video": { color: "#00a8e0", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/Amazon_Prime_Video_logo.svg/24px-Amazon_Prime_Video_logo.svg.png" },
  "Disney+": { color: "#113ccf", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/24px-Disney%2B_logo.svg.png" },
  "Apple TV+": { color: "#a2aaad", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/24px-Apple_TV_Plus_Logo.svg.png" },
  "Paramount+": { color: "#0064ff", logo: "" },
  "Canal+": { color: "#000", logo: "" },
  OCS: { color: "#e85d04", logo: "" },
  Crunchyroll: { color: "#f47521", logo: "" },
  Mubi: { color: "#2196f3", logo: "" },
  Hulu: { color: "#1ce783", logo: "" }
};
const STREAMING_LINKS = {
  Netflix: "https://www.netflix.com/search?q=",
  "Amazon Prime Video": "https://www.amazon.fr/gp/video/search?phrase=",
  "Disney+": "https://www.disneyplus.com/search/",
  "Apple TV+": "https://tv.apple.com/search?term=",
  "Canal+": "https://www.canalplus.com/recherche/",
  OCS: "https://www.ocs.fr/recherche/",
  "Paramount+": "https://www.paramountplus.com/search/",
  Crunchyroll: "https://www.crunchyroll.com/search?q=",
  Mubi: "https://mubi.com/search/",
  Hulu: "https://www.hulu.com/search?query="
};

// ════ ÉTAT GLOBAL ════
let currentLang = "fr";
let lastGrid = null;
let currentPage = 1;
let currentGenreName = "";
let _allResults = [];
let _currentTotalPages = 1;
let currentMovieId = null;
let currentMediaType = "movie";
let analysisAbortController = null;
let navStack = [];

// ════ AUDIO (Web Audio API) ════
let audioCtx = null;
let bgMusicGain = null;
let bgMusicInterval = null;

function initAudio() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  bgMusicGain = audioCtx.createGain();
  bgMusicGain.gain.value = 0.15;
  bgMusicGain.connect(audioCtx.destination);
}

function playTone(freq, duration, type = 'square', volume = 0.1) {
  if (!audioCtx) return;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(volume, audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start();
  osc.stop(audioCtx.currentTime + duration);
}

function playCoinSound() {
  playTone(988, 0.08, 'square', 0.2);
  setTimeout(() => playTone(1319, 0.1, 'square', 0.2), 60);
}

function playGameOverSound() {
  playTone(330, 0.2, 'sawtooth', 0.2);
  setTimeout(() => playTone(262, 0.3, 'sawtooth', 0.2), 150);
  setTimeout(() => playTone(196, 0.5, 'sawtooth', 0.15), 350);
}

function startBgMusic() {
  if (!audioCtx || bgMusicInterval) return;
  const notes = [523, 587, 659, 698, 784, 880, 988, 1047];
  const durations = [0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.2, 0.4];
  let i = 0;
  bgMusicInterval = setInterval(() => {
    const freq = notes[i % notes.length];
    const dur = durations[i % durations.length];
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'square';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain);
    gain.connect(bgMusicGain);
    osc.start();
    osc.stop(audioCtx.currentTime + dur);
    i++;
  }, 250);
}

function stopBgMusic() {
  clearInterval(bgMusicInterval);
  bgMusicInterval = null;
}

// ════ UTILITAIRES DE LANGUE ════
function getLangCode() {
  const m = { "en-US": "en-US", "en-GB": "en-GB", fr: "fr-FR", es: "es-ES", de: "de-DE", zh: "zh-CN" };
  return m[currentLang] || "fr-FR";
}
function getRegionCode() {
  return (dict[currentLang] || dict.fr).providers_country || "FR";
}
function getTMDBLang() {
  const m = { "en-US": "en", "en-GB": "en", fr: "fr", es: "es", de: "de", zh: "zh" };
  return m[currentLang] || "fr";
}
function t(key) {
  return (dict[currentLang] || dict.fr)[key] || key;
}
function tg(key) {
  return ((dict[currentLang] || dict.fr).genres || {})[key] || key;
}

function initLang() {
  const pathLang = window.location.pathname.replace(/\//g, "");
  const pathMap = { en: "en-US", "en-US": "en-US", "en-GB": "en-GB", fr: "fr", es: "es", de: "de", zh: "zh" };
  if (pathMap[pathLang]) currentLang = pathMap[pathLang];
  document.getElementById("lang-selector").value = currentLang;
  applyLang();
  genererNav();
}

function applyLang() {
  const langData = dict[currentLang] || dict.fr;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (langData[key]) el.textContent = langData[key];
  });
  const inp = document.getElementById("input_global");
  if (inp) inp.placeholder = langData.placeholder || "";
  const optMap = { pop: "sort_pop", note_desc: "sort_top", note_asc: "sort_asc", recent: "sort_new", ancien: "sort_old" };
  document.querySelectorAll("#filtre-tri option").forEach(opt => {
    const key = optMap[opt.value];
    if (key && langData[key]) opt.textContent = langData[key];
  });
  document.querySelector("#filtre-note option").textContent = "⭐ " + (langData.min_score || "Note min");
  document.querySelector("#filtre-annee option").textContent = "📅 " + (langData.year || "Année");
  const btr = document.getElementById("btn-reset");
  if (btr) btr.innerHTML = `<i class="fas fa-times"></i> ${langData.reset || "Reset"}`;
}

function genererNav() {
  const nav = document.getElementById("genre-nav");
  const g = dict[currentLang]?.genres || dict.fr.genres;
  nav.innerHTML = `
    <a class="btn-genre" onclick="chargerGenre('horror')"><i class="fas fa-ghost"></i> ${g.horror}</a>
    <a class="btn-genre" onclick="chargerGenre('action')"><i class="fas fa-fire"></i> ${g.action}</a>
    <a class="btn-genre" onclick="chargerGenre('comedy')"><i class="fas fa-laugh"></i> ${g.comedy}</a>
    <a class="btn-genre" onclick="chargerGenre('science-fiction')"><i class="fas fa-robot"></i> ${g.scifi}</a>
    <a class="btn-genre" onclick="chargerGenre('romance')"><i class="fas fa-heart"></i> ${g.romance}</a>
    <a class="btn-genre" onclick="chargerGenre('animation')"><i class="fas fa-dragon"></i> ${g.animation}</a>
    <a class="btn-genre" onclick="chargerGenre('thriller')"><i class="fas fa-eye"></i> ${g.thriller}</a>
    <a class="btn-genre" onclick="chargerGenre('drama')"><i class="fas fa-theater-masks"></i> ${g.drama}</a>
    <a class="btn-genre series" onclick="chargerSeries()"><i class="fas fa-tv"></i> ${g.series}</a>
    <a class="btn-genre trending" onclick="chargerTrending()"><i class="fas fa-bolt"></i> ${g.trending}</a>`;

  const platNav = document.getElementById("platform-nav");
  platNav.innerHTML = `
    <button class="btn-platform" onclick="chargerParPlateforme('netflix')" style="border-color:#e50914"><span class="plat-dot" style="background:#e50914"></span> Netflix</button>
    <button class="btn-platform" onclick="chargerParPlateforme('amazon')" style="border-color:#00a8e0"><span class="plat-dot" style="background:#00a8e0"></span> Prime Video</button>
    <button class="btn-platform" onclick="chargerParPlateforme('disney')" style="border-color:#113ccf"><span class="plat-dot" style="background:#113ccf"></span> Disney+</button>
    <button class="btn-platform" onclick="chargerParPlateforme('apple')" style="border-color:#a2aaad"><span class="plat-dot" style="background:#a2aaad"></span> Apple TV+</button>
    <button class="btn-platform" onclick="chargerParPlateforme('paramount')" style="border-color:#0064ff"><span class="plat-dot" style="background:#0064ff"></span> Paramount+</button>
    <button class="btn-platform" onclick="chargerParPlateforme('hulu')" style="border-color:#1ce783"><span class="plat-dot" style="background:#1ce783"></span> Hulu</button>`;
}

function changerLangueManuellement() {
  const newLang = document.getElementById("lang-selector").value;
  currentLang = newLang;
  applyLang();
  genererNav();
  const langPath = { "en-US": "en", "en-GB": "en-GB", fr: "fr", es: "es", de: "de", zh: "zh" }[currentLang] || "fr";
  history.replaceState(null, "", "/" + langPath);
  const detailPage = document.getElementById("page-film-detail");
  const gridPage = document.getElementById("genre-grid");
  if (currentMovieId && detailPage.style.display !== "none") {
    afficherDetails(currentMovieId, currentMediaType);
    return;
  }
  if (gridPage.style.display !== "none") {
    if (currentGenreName === "trending") chargerTrending();
    else if (currentGenreName === "series") chargerSeries();
    else if (currentGenreName) chargerGenre(currentGenreName, currentPage);
    return;
  }
  chargerTrending().then(() => {
    document.getElementById("hero").style.display = "block";
    document.getElementById("genre-nav").style.display = "flex";
  });
}

// ════ ERREURS, TOAST ════
function afficherErreur(msg) {
  const el = document.getElementById("error-message");
  document.getElementById("error-text").textContent = msg;
  el.classList.add("visible");
  el.style.display = "flex";
  setTimeout(cacherErreur, 8000);
}

function afficherErreurTelechargement() {
  // Cacher l'overlay et le jeu
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();

  // Construire un message d'erreur clair
  const msg = `
    <div style="text-align:center; padding:30px 20px; max-width:600px; margin:0 auto;">
      <i class="fas fa-exclamation-triangle" style="font-size:3rem; color:#ffaa00;"></i>
      <h3 style="color:var(--text); margin:16px 0 8px;">Impossible de télécharger la vidéo</h3>
      <p style="color:var(--muted); font-size:0.9rem; line-height:1.6;">
        Le lien que vous avez collé ne peut pas être lu. Cela peut arriver si la vidéo est privée, 
        restreinte à certains pays, ou si elle a été supprimée.<br/>
        👉 Essayez de <strong>rechercher le film manuellement</strong> en saisissant un titre, un acteur ou une description.
      </p>
      <button class="btn-stream" onclick="document.getElementById('input_global').focus()" style="margin-top:16px;">
        <i class="fas fa-search"></i> Rechercher un film
      </button>
    </div>
  `;
  
  // On vide la grille et on affiche ce message
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-title").innerText = "⛔ Vidéo inaccessible";
  document.getElementById("movie-cards").innerHTML = msg;
  document.getElementById("filtres-bar").style.display = "none";
  
  // Cacher le hero
  document.getElementById("hero").style.display = "none";
  document.getElementById("page-film-detail").style.display = "none";
}
function cacherErreur() {
  const el = document.getElementById("error-message");
  el.classList.remove("visible");
  el.style.display = "none";
}
function toast(msg, dur = 3000) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), dur);
}

// ════ BARRE DE RECHERCHE ════
function majBtnClear() {
  const val = document.getElementById("input_global").value;
  document.getElementById("btn-clear").classList.toggle("visible", val.length > 0);
}
function effacerRecherche() {
  document.getElementById("input_global").value = "";
  document.getElementById("btn-clear").classList.remove("visible");
  document.getElementById("input_global").focus();
}

// ════ NAVIGATION ════
function retourAccueil() {
  cacherErreur();
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("privacy-page").style.display = "none";
  document.getElementById("hero").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
  document.getElementById("platform-nav").classList.remove("visible");
  lastGrid = null;
  currentMovieId = null;
  navStack = [];
}
function retourArriere() {
  if (navStack.length > 0) {
    const prev = navStack.pop();
    afficherDetails(prev.id, prev.type);
  } else {
    document.getElementById("page-film-detail").style.display = "none";
    if (lastGrid) {
      document.getElementById("genre-grid").style.display = "block";
    } else {
      retourAccueil();
    }
  }
}
function hideHero() {
  document.getElementById("hero").style.display = "none";
  document.getElementById("genre-nav").style.display = "flex";
}

// ════ RECHERCHE GLOBALE ════
async function gererRechercheGlobal() {
  const input = document.getElementById("input_global").value.trim();
  if (!input) return;
  cacherErreur();
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("page-film-detail").style.display = "none";
  const isLink = /^https?:\/\/|tiktok\.com|instagram\.com|youtube\.com|youtu\.be|vm\.tiktok\.com|vt\.tiktok\.com/i.test(input);
  if (isLink) {
    await analyserVideo(input);
  } else {
    hideHero();
    try {
      const res = await fetch(`/rechercher?query=${encodeURIComponent(input)}&lang=${getTMDBLang()}`);
      const data = await res.json();
      afficherResultatsRecherche(data, input);
    } catch (e) {
      afficherErreur("Erreur réseau : " + e.message);
    }
  }
}

// ════ ANNULER ANALYSE ════
function annulerAnalyse() {
  if (analysisAbortController) analysisAbortController.abort();
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();
  retourAccueil();
}

// ════ MINI-JEU ════
let gameState = {
  running: false,
  score: 0,
  lives: 3,
  level: 1,
  heroY: 0,
  heroVY: 0,
  jumping: false,
  obstacles: [],
  coins: [],
  frame: 0,
  speed: 3,
  gTimer: null,
  dead: false,
  started: false
};
function gameJump() {
  if (!gameState.running || gameState.dead) {
    startGame();
    return;
  }
  if (!gameState.jumping) {
    gameState.heroVY = -9;
    gameState.jumping = true;
  }
}
function startGame() {
  if (gameState.gTimer) clearInterval(gameState.gTimer);
  Object.assign(gameState, {
    running: true, score: 0, lives: 3, level: 1, heroY: 0, heroVY: 0, jumping: false,
    obstacles: [], coins: [], frame: 0, speed: 3, dead: false, started: true
  });
  const isMobile = /Android|iPhone|iPad|iPod|webOS/i.test(navigator.userAgent);
  const hint = document.getElementById("game-hint");
  hint.textContent = isMobile ? "TAPE sur l'écran pour sauter !" : "Clique sur le personnage ou appuie sur ESPACE pour sauter";
  hint.style.display = "block";
  initAudio();
  startBgMusic();
  gameState.gTimer = setInterval(gameLoop, 16);
}
function stopGame() {
  clearInterval(gameState.gTimer);
  gameState.running = false;
  stopBgMusic();
}
function gameLoop() {
  if (!gameState.running) return;
  gameState.frame++;
  const canvas = document.getElementById("game-canvas");
  if (!canvas) return;
  const W = canvas.offsetWidth || 380;
  const hero = document.getElementById("game-hero");
  if (!hero) return;
  if (gameState.jumping) {
    gameState.heroVY += 0.6;
    gameState.heroY -= gameState.heroVY;
    if (gameState.heroY <= 0) {
      gameState.heroY = 0;
      gameState.heroVY = 0;
      gameState.jumping = false;
    }
  }
  hero.style.bottom = 28 + gameState.heroY + "px";
  hero.style.left = "60px";
  gameState.speed = 3 + Math.floor(gameState.score / 50) * 0.5;
  gameState.level = Math.floor(gameState.score / 50) + 1;
  document.getElementById("game-level").textContent = "LVL " + gameState.level;
  if (gameState.frame % Math.max(60, 120 - gameState.level * 5) === 0) {
    const obs = document.createElement("div");
    obs.className = "game-obstacle";
    obs.textContent = ["🌵", "🧱", "🔮", "💀", "⚡"][Math.floor(Math.random() * 5)];
    obs.style.left = W + "px";
    obs.style.bottom = "28px";
    canvas.appendChild(obs);
    gameState.obstacles.push({ el: obs, x: W });
  }
  if (gameState.frame % 80 === 40) {
    const coin = document.createElement("div");
    coin.className = "game-coin";
    coin.textContent = "🪙";
    const cy = 50 + Math.random() * 60;
    coin.style.left = W + "px";
    coin.style.bottom = 28 + cy + "px";
    coin.style.animation = "coin-bounce .8s ease infinite";
    canvas.appendChild(coin);
    gameState.coins.push({ el: coin, x: W, y: cy });
  }
  gameState.obstacles = gameState.obstacles.filter(ob => {
    ob.x -= gameState.speed;
    ob.el.style.left = ob.x + "px";
    if (ob.x > 40 && ob.x < 90 && gameState.heroY < 35) {
      gameState.lives--;
      document.getElementById("game-lives").textContent = "❤️".repeat(Math.max(0, gameState.lives));
      ob.el.remove();
      if (gameState.lives <= 0) {
        gameOver();
        return false;
      }
      return false;
    }
    if (ob.x < -40) {
      ob.el.remove();
      return false;
    }
    return true;
  });
  gameState.coins = gameState.coins.filter(c => {
    c.x -= gameState.speed;
    c.el.style.left = c.x + "px";
    if (c.x > 40 && c.x < 90 && gameState.heroY > c.y - 15 && gameState.heroY < c.y + 15 + 20) {
      gameState.score += 5;
      c.el.remove();
      playCoinSound();
      return false;
    }
    if (c.x < -40) {
      c.el.remove();
      return false;
    }
    return true;
  });
  if (gameState.frame % 10 === 0) gameState.score++;
  document.getElementById("game-score").textContent = gameState.score;
}
function gameOver() {
  gameState.running = false;
  gameState.dead = true;
  clearInterval(gameState.gTimer);
  playGameOverSound();
  stopBgMusic();
  document.getElementById("game-hint").textContent = t("game_over") + gameState.score + " — TAP";
  document.getElementById("game-hint").style.display = "block";
}

// ════ ANALYSE VIDÉO (avec fallback local) ════
async function analyserVideo(lien) {
  hideHero();
  const overlay = document.getElementById("loading-overlay");
  overlay.classList.add("active");
  startGame();
  let progress = 0;
  const progressBar = document.getElementById("prog-fill");
  const percentLabel = document.getElementById("prog-percent");
  const interval = setInterval(() => {
    if (progress < 90) {
      progress += Math.random() * 15 + 5;
      if (progress > 90) progress = 90;
      progressBar.style.width = progress + "%";
      percentLabel.textContent = Math.round(progress) + "%";
    }
  }, 800);
  analysisAbortController = new AbortController();
  try {
    const res = await fetch("/analyser", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: lien, lang: getTMDBLang() }),
      signal: analysisAbortController.signal
    });
    const data = await res.json();
    if (data.status === "transcription_needed") {
      // Fallback local OCR + transcription
      const ocrText = await runLocalOCR(data.frames_base64);
      const transcript = await runLocalWhisper(data.audio_base64);
      const continueRes = await fetch("/analyser_continue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: data.session_id,
          ocr_text: ocrText,
          transcript: transcript
        })
      });
      const finalData = await continueRes.json();
      clearInterval(interval);
      progressBar.style.width = "100%";
      percentLabel.textContent = "100%";
      setTimeout(() => overlay.classList.remove("active"), 600);
      stopGame();
      if (finalData.status === "success" || finalData.status === "cached") {
        navStack = [];
        lastGrid = null;
        currentMovieId = finalData.tmdb_id;
        currentMediaType = finalData.media_type || "movie";
        afficherDetailFilm(finalData);
      } else {
        afficherErreur("❌ " + (finalData.message || "Film introuvable."));
        retourAccueil();
      }
        } else {
      clearInterval(interval);
      progressBar.style.width = "100%";
      percentLabel.textContent = "100%";
      setTimeout(() => overlay.classList.remove("active"), 600);
      stopGame();
      if (data.status === "success" || data.status === "cached") {
        navStack = [];
        lastGrid = null;
        currentMovieId = data.tmdb_id;
        currentMediaType = data.media_type || "movie";
        afficherDetailFilm(data);
      } else if (data.status === "not_found") {
        afficherNotFound(data);
      } else if (data.status === "error" && data.message && data.message.includes("télécharger")) {
        // Échec du téléchargement → message dédié sans retour à l'accueil
        afficherErreurTelechargement();
      } else {
        // Autre erreur générique
        afficherErreur("❌ " + (data.message || "Film introuvable."));
        retourAccueil();
      }
    }
  } catch (e) {
    clearInterval(interval);
    overlay.classList.remove("active");
    stopGame();
    if (e.name !== "AbortError") {
      afficherErreur("Erreur réseau : " + e.message);
      retourAccueil();
    }
  }
}

async function runLocalOCR(framesBase64) {
  const worker = await Tesseract.createWorker('fra');
  let fullText = "";
  for (const b64 of framesBase64) {
    const { data: { text } } = await worker.recognize(`data:image/jpeg;base64,${b64}`);
    fullText += text + " ";
  }
  await worker.terminate();
  return fullText.trim();
}

async function runLocalWhisper(audioBase64) {
  const audioBlob = base64ToBlob(audioBase64, 'audio/mp3');
  const arrayBuffer = await audioBlob.arrayBuffer();
  const audioCtxLocal = new AudioContext();
  const audioBuffer = await audioCtxLocal.decodeAudioData(arrayBuffer);
  const pcm = audioBuffer.getChannelData(0);
  const pipeline = await window.getWhisperPipeline();
  const result = await pipeline(pcm, { language: 'french' });
  return result.text;
}

function base64ToBlob(base64, mimeType) {
  const byteChars = atob(base64);
  const byteArrays = [];
  for (let offset = 0; offset < byteChars.length; offset += 512) {
    const slice = byteChars.slice(offset, offset + 512);
    const byteNumbers = new Array(slice.length);
    for (let i = 0; i < slice.length; i++) byteNumbers[i] = slice.charCodeAt(i);
    byteArrays.push(new Uint8Array(byteNumbers));
  }
  return new Blob(byteArrays, { type: mimeType });
}

// ════ NOT FOUND ════
function afficherNotFound(data) {
  document.getElementById("page-film-detail").style.display = "block";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("hero").style.display = "none";
  document.getElementById("back-label").innerText = t("back_home");
  ["fake_alert", "detail_tags", "detail_rating", "cast_section", "trailer_section", "similar_section", "seasons_section"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = "";
  });
  document.getElementById("confidence_wrap").style.display = "none";
  document.getElementById("food-partner").classList.remove("visible");
  document.getElementById("affiche_film").style.display = "none";
  document.getElementById("titre_film").innerText = t("not_found_title");
  document.getElementById("synopsis_film").innerText = data.description || "";
  const titreHtml = data.titre_gemini
    ? `<p style="color:var(--muted);font-size:.85rem;margin-bottom:16px;">Titre potentiel IA : <strong style="color:var(--text)">${data.titre_gemini}</strong><br><small style="font-size:.73rem;">Non trouvé dans TMDB.</small></p>`
    : "";
  document.getElementById("streaming_section").innerHTML =
    `${titreHtml}<h3><i class="fas fa-search"></i> ${t("searching")}</h3><div class="streaming-buttons" style="margin-top:10px;"><a href="${data.search_youtube}" target="_blank" rel="noopener" class="btn-stream"><i class="fab fa-youtube"></i> YouTube</a><a href="${data.search_google}" target="_blank" rel="noopener" class="btn-stream"><i class="fab fa-google"></i> Google</a><a href="${data.search_tmdb}" target="_blank" rel="noopener" class="btn-stream"><i class="fas fa-film"></i> TMDB</a></div>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ════ GENRES / TRENDING / SERIES ════
async function chargerGenre(genreName, page = 1, mediaType = "movie") {
  hideHero();
  cacherErreur();
  currentGenreName = genreName;
  currentPage = page;
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText = genreName.toUpperCase();
  document.getElementById("movie-cards").innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid = genreName;
  navStack = [];
  try {
    const url = `/discover/${encodeURIComponent(genreName)}?lang=${getTMDBLang()}&page=${page}${mediaType === "tv" ? "&type=tv" : ""}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.status === "success") {
      renderCards(data.results, genreName, page, data.total_pages, mediaType);
    } else {
      document.getElementById("movie-cards").innerHTML = `<p style="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px">Genre introuvable.</p>`;
    }
  } catch (e) {
    afficherErreur("Erreur: " + e.message);
  }
}

async function chargerSeries(page = 1) {
  hideHero();
  cacherErreur();
  currentGenreName = "series";
  currentPage = page;
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(".btn-genre.series")?.classList.add("active");
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText = tg("series").toUpperCase();
  document.getElementById("movie-cards").innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid = "series";
  navStack = [];
  try {
    const res = await fetch(`/trending?lang=${getTMDBLang()}&type=tv`);
    const data = await res.json();
    if (data.status === "success") {
      renderCards(data.results.map(r => ({ ...r, media_type: "tv" })), "series", 1, 1, "tv");
    } else {
      document.getElementById("movie-cards").innerHTML = `<p style="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px">Impossible de charger les séries.</p>`;
    }
  } catch (e) {
    afficherErreur("Erreur séries: " + e.message);
  }
}

async function chargerTrending() {
  hideHero();
  cacherErreur();
  currentGenreName = "trending";
  document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
  document.querySelector(".btn-genre.trending")?.classList.add("active");
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText = tg("trending").toUpperCase();
  document.getElementById("movie-cards").innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid = "trending";
  navStack = [];
  try {
    const res = await fetch(`/trending?lang=${getTMDBLang()}`);
    const data = await res.json();
    if (data.status === "success") {
      renderCards(data.results, "trending", 1, 1);
    } else {
      document.getElementById("movie-cards").innerHTML = `<p style="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px">Impossible de charger les tendances.</p>`;
    }
  } catch (e) {
    afficherErreur("Erreur tendances: " + e.message);
  }
}

async function chargerParPlateforme(platformKey) {
  hideHero();
  cacherErreur();
  const nameMap = { netflix: "NETFLIX", amazon: "PRIME VIDEO", disney: "DISNEY+", apple: "APPLE TV+", paramount: "PARAMOUNT+", hulu: "HULU" };
  currentGenreName = platformKey;
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-title").innerText = "📺 " + nameMap[platformKey];
  document.getElementById("movie-cards").innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  document.querySelectorAll(".btn-platform").forEach(b => b.classList.remove("active"));
  event?.currentTarget?.classList.add("active");
  lastGrid = platformKey;
  navStack = [];
  try {
    const trending = await fetch(`/trending?lang=${getTMDBLang()}`);
    const data = await trending.json();
    if (data.status === "success") {
      renderCards(data.results, platformKey, 1, 1);
      toast("🎬 Films populaires sur " + nameMap[platformKey]);
    }
  } catch (e) {
    afficherErreur("Erreur plateforme: " + e.message);
  }
}

// ════ RENDER CARDS ════
function renderCards(results, genreName, page, totalPages, mediaType = "movie") {
  _allResults = results || [];
  _currentTotalPages = totalPages || 1;
  peuplerFiltreAnnee(_allResults);
  document.getElementById("filtres-bar").style.display = _allResults.length > 0 ? "flex" : "none";
  document.getElementById("filtre-count").textContent = _allResults.length + " film" + (_allResults.length > 1 ? "s" : "");
  appliquerFiltres();
  if (genreName !== "trending" && genreName !== "search") {
    setTimeout(() => {
      const container = document.getElementById("movie-cards");
      const existing = container.querySelector(".pagination");
      if (existing) existing.remove();
      const pag = document.createElement("div");
      pag.className = "pagination";
      const isSeries = genreName === "series";
      pag.innerHTML = `<button class="btn-page" onclick="${isSeries ? `chargerSeries(${page - 1})` : `chargerGenre('${genreName}',${page - 1})`}" ${page <= 1 ? "disabled" : ""}><i class="fas fa-chevron-left"></i></button><span class="page-info">${page}${totalPages ? " / " + totalPages : ""}</span><button class="btn-page" onclick="${isSeries ? `chargerSeries(${page + 1})` : `chargerGenre('${genreName}',${page + 1})`}" ${totalPages && page >= totalPages ? "disabled" : ""}><i class="fas fa-chevron-right"></i></button>`;
      container.appendChild(pag);
    }, 0);
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function peuplerFiltreAnnee(results) {
  const sel = document.getElementById("filtre-annee");
  const annees = [...new Set(results.map(m => (m.release_date || m.first_air_date || "").split("-")[0]).filter(Boolean))].sort((a, b) => b - a);
  sel.innerHTML = `<option value="">📅 ${t("year")}</option>` + annees.map(a => `<option value="${a}">${a}</option>`).join("");
}

function appliquerFiltres() {
  const annee = document.getElementById("filtre-annee").value;
  const note = parseFloat(document.getElementById("filtre-note").value) || 0;
  const tri = document.getElementById("filtre-tri").value;
  let res = _allResults.filter(m => {
    const y = (m.release_date || m.first_air_date || "").split("-")[0];
    return (!annee || y === annee) && (m.vote_average || 0) >= note;
  });
  if (tri === "note_desc") res.sort((a, b) => (b.vote_average || 0) - (a.vote_average || 0));
  else if (tri === "note_asc") res.sort((a, b) => (a.vote_average || 0) - (b.vote_average || 0));
  else if (tri === "recent") res.sort((a, b) => (b.release_date || b.first_air_date || "").localeCompare(a.release_date || a.first_air_date || ""));
  else if (tri === "ancien") res.sort((a, b) => (a.release_date || a.first_air_date || "").localeCompare(b.release_date || b.first_air_date || ""));
  document.getElementById("filtre-count").textContent = res.length + " film" + (res.length > 1 ? "s" : "");
  renderCardsFiltered(res);
}

function reinitFiltres() {
  document.getElementById("filtre-annee").value = "";
  document.getElementById("filtre-note").value = "";
  document.getElementById("filtre-tri").value = "pop";
  appliquerFiltres();
}

function renderCardsFiltered(results) {
  const container = document.getElementById("movie-cards");
  const oldPag = container.querySelector(".pagination");
  [...container.children].forEach(c => { if (!c.classList.contains("pagination")) c.remove(); });
  if (!results || results.length === 0) {
    const p = document.createElement("p");
    p.style.cssText = "color:var(--muted);grid-column:1/-1;text-align:center;padding:40px";
    p.textContent = "Aucun résultat avec ces filtres.";
    if (oldPag) container.insertBefore(p, oldPag);
    else container.appendChild(p);
    return;
  }
  results.forEach(m => {
    const year = (m.release_date || m.first_air_date || "N/A").split("-")[0];
    const rating = m.vote_average ? m.vote_average.toFixed(1) : "0";
    const title = m.title || m.name || "Titre inconnu";
    const isTv = m.media_type === "tv" || m.first_air_date;
    const poster = m.poster_path ? `https://image.tmdb.org/t/p/w300${m.poster_path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
    const div = document.createElement("div");
    div.className = "movie-card";
    div.setAttribute("role", "button");
    div.setAttribute("tabindex", "0");
    div.setAttribute("aria-label", title);
    div.onclick = () => afficherDetails(m.id, isTv ? "tv" : "movie");
    div.onkeydown = e => { if (e.key === "Enter") afficherDetails(m.id, isTv ? "tv" : "movie"); };
    div.innerHTML = `${isTv ? `<span class="card-type-badge">TV</span>` : ""}<img src="${poster}" alt="${title}" loading="lazy"><div class="card-body"><h4>${title}</h4><div class="card-meta"><span><i class="fas fa-calendar" style="font-size:.65rem;opacity:.5"></i> ${year}</span><span class="rating"><i class="fas fa-star" style="font-size:.65rem"></i> ${rating}</span></div></div>`;
    if (oldPag) container.insertBefore(div, oldPag);
    else container.appendChild(div);
  });
}

// ════ RÉSULTATS DE RECHERCHE ════
function afficherResultatsRecherche(data, query) {
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("genre-title").innerText = `🔍 "${query}"`;
  lastGrid = "search";
  navStack = [];
  renderCards(data.results || [], "search", 1, 1);
}

// ════ DÉTAILS DU FILM ════
async function afficherDetails(movieId, mediaType = "movie") {
  if (!navStack.length) navStack = [];
  else { if (currentMovieId) navStack.push({ id: currentMovieId, type: currentMediaType }); }
  currentMovieId = movieId;
  currentMediaType = mediaType;
  cacherErreur();
  document.getElementById("genre-grid").style.display = "none";
  showDetailLoading();
  try {
    const res = await fetch(`/movie/${movieId}?lang=${getTMDBLang()}&type=${mediaType}`);
    const data = await res.json();
    const region = getRegionCode();
    const providers = data["watch/providers"]?.results?.[region]?.flatrate || [];
    const similar = data.similar?.results?.slice(0, 6) || [];
    const cast = data.credits?.cast?.slice(0, 8) || [];
    const trailerD = data.videos?.results?.find(v => v.type === "Trailer") || data.videos?.results?.find(v => ["Teaser", "Clip"].includes(v.type));
    const trailerUrl = trailerD?.site === "YouTube" ? `https://www.youtube.com/watch?v=${trailerD.key}` : "";
    const genres = data.genres?.map(g => g.name) || [];
    const year = (data.release_date || data.first_air_date || "").split("-")[0];
    const isTv = mediaType === "tv" || !!data.first_air_date;
    afficherDetailFilm({
      status: "success",
      title: data.title || data.name || "Inconnu",
      synopsis: data.overview || "",
      image: data.poster_path ? `https://image.tmdb.org/t/p/w500${data.poster_path}` : "",
      streaming: providers.map(p => p.provider_name),
      streaming_logos: providers.map(p => ({ name: p.provider_name, logo_path: p.logo_path })),
      similar, cast,
      trailer: trailerUrl,
      confidence: null,
      is_fake: false,
      vote_average: data.vote_average,
      vote_count: data.vote_count,
      runtime: data.runtime || data.episode_run_time?.[0],
      genres, year,
      tmdb_id: movieId,
      is_series: isTv,
      seasons: isTv ? (data.seasons || []) : null
    });
  } catch (e) {
    afficherErreur("Erreur chargement: " + e.message);
    retourArriere();
  }
}

function showDetailLoading() {
  document.getElementById("page-film-detail").style.display = "block";
  document.getElementById("titre_film").innerText = "…";
  document.getElementById("affiche_film").src = "";
  ["synopsis_film", "detail_tags", "detail_rating", "streaming_section", "cast_section", "trailer_section", "similar_section", "seasons_section", "fake_alert"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = "";
  });
  document.getElementById("confidence_wrap").style.display = "none";
  document.getElementById("food-partner").classList.remove("visible");
}

function afficherDetailFilm(data) {
  document.getElementById("page-film-detail").style.display = "block";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("hero").style.display = "none";
  document.getElementById("back-label").innerText = lastGrid ? t("back_list") : t("back_home");

  document.getElementById("fake_alert").innerHTML = data.is_fake ? `<div class="fake-alert"><i class="fas fa-exclamation-triangle"></i> Contenu humoristique possible — résultat peut être imprécis.</div>` : "";

  document.getElementById("titre_film").innerText = data.title || "Inconnu";

  const imgEl = document.getElementById("affiche_film");
  if (data.image) {
    imgEl.src = data.image;
    imgEl.style.display = "block";
  } else imgEl.style.display = "none";

  const tagsEl = document.getElementById("detail_tags");
  tagsEl.innerHTML = "";
  if (data.is_series) tagsEl.innerHTML += `<span class="tag series"><i class="fas fa-tv"></i> ${t("series_tag")}</span>`;
  if (data.year) tagsEl.innerHTML += `<span class="tag year"><i class="fas fa-calendar"></i> ${data.year}</span>`;
  if (data.runtime) tagsEl.innerHTML += `<span class="tag"><i class="fas fa-clock"></i> ${data.runtime} min</span>`;
  (data.genres || []).forEach(g => tagsEl.innerHTML += `<span class="tag genre">${g}</span>`);

  const confWrap = document.getElementById("confidence_wrap");
  if (data.confidence !== null && data.confidence !== undefined) {
    const pct = Math.round(data.confidence);
    const color = pct >= 70 ? "#00ffcc" : pct >= 40 ? "#ffd700" : "#ff4444";
    const lbl = pct >= 70 ? (currentLang.startsWith("en") ? "High confidence" : "Confiance élevée") : pct >= 40 ? (currentLang.startsWith("en") ? "Medium confidence" : "Confiance moyenne") : (currentLang.startsWith("en") ? "Low confidence" : "Confiance faible");
    confWrap.style.display = "block";
    document.getElementById("conf-bar-inner").style.width = pct + "%";
    document.getElementById("conf-bar-inner").style.background = color;
    document.getElementById("conf-pct-label").textContent = pct + "% — " + lbl;
    document.getElementById("conf-pct-label").style.color = color;
  } else confWrap.style.display = "none";

  const ratingEl = document.getElementById("detail_rating");
  ratingEl.innerHTML = data.vote_average ? `<i class="fas fa-star" style="color:var(--gold)"></i> ${parseFloat(data.vote_average).toFixed(1)}<small> / 10 · ${data.vote_count ? data.vote_count.toLocaleString() + " votes" : ""}</small>` : "";

  const synEl = document.getElementById("synopsis_film");
  if (data.scene_description) {
    synEl.innerHTML = `<div style="background:rgba(0,255,204,.06);border-left:3px solid var(--primary);padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:14px;font-size:.82rem;color:var(--muted)"><span style="color:var(--primary);font-weight:600;font-size:.73rem;text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:6px"><i class="fas fa-film"></i> ${t("scene_identified")}</span>${data.scene_description}</div><span style="font-size:.73rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:8px">Synopsis</span>${data.synopsis || t("no_synopsis")}`;
  } else {
    synEl.textContent = data.synopsis || t("no_synopsis");
  }

  setTimeout(() => document.getElementById("food-partner").classList.add("visible"), 400);

  const streamEl = document.getElementById("streaming_section");
  const streamList = data.streaming || [];
  const streamLogos = data.streaming_logos || [];
  const noStreamMsg = t("no_streaming_country");
  if (streamList.length > 0) {
    const btns = streamList.map((name, i) => {
      const base = STREAMING_LINKS[name] || "https://www.google.com/search?q=";
      const url = base + encodeURIComponent(data.title || "");
      const meta = STREAMING_META[name] || { color: "#fff", logo: "" };
      const logoPath = streamLogos[i]?.logo_path;
      const logoSrc = logoPath ? `https://image.tmdb.org/t/p/w45${logoPath}` : meta.logo || "";
      const aff = name.includes("Amazon") || name.includes("Apple");
      const logoHtml = logoSrc ? `<img src="${logoSrc}" class="plat-logo" alt="${name}" onerror="this.style.display='none'">` : `<i class="fas fa-play-circle" style="color:${meta.color}"></i>`;
      return `<a href="${url}" target="_blank" rel="noopener" class="btn-stream ${aff ? "affiliate" : ""}" style="border-color:${meta.color}40">${logoHtml} ${name}</a>`;
    }).join("");
    streamEl.innerHTML = `<h3><i class="fas fa-satellite-dish"></i> ${t("streaming_title")}</h3><div class="streaming-buttons">${btns}</div>`;
  } else {
    streamEl.innerHTML = `<h3><i class="fas fa-satellite-dish"></i> Streaming</h3><p style="color:var(--muted);font-size:.85rem">${noStreamMsg}</p><div class="streaming-buttons" style="margin-top:8px"><a href="https://www.amazon.fr/gp/video/search?phrase=${encodeURIComponent(data.title || "")}" target="_blank" class="btn-stream affiliate" style="border-color:#00a8e040"><i class="fas fa-search" style="color:#00a8e0"></i> Amazon Prime</a><a href="https://www.google.com/search?q=${encodeURIComponent((data.title || "") + " streaming")}" target="_blank" class="btn-stream"><i class="fab fa-google"></i> Google</a></div>`;
  }

  const seasonsEl = document.getElementById("seasons_section");
  if (data.is_series && data.seasons && data.seasons.length > 0) {
    const seasons = data.seasons.filter(s => s.season_number > 0 || s.episode_count > 0);
    const seasonCards = seasons.map(s => {
      const poster = s.poster_path ? `https://image.tmdb.org/t/p/w154${s.poster_path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='72' fill='%231a1a24'%3E%3Crect width='48' height='72'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='16' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
      const airYear = s.air_date ? s.air_date.split("-")[0] : "";
      return `<div class="season-card" id="season-${s.season_number}"><div class="season-header" onclick="toggleSaison(${data.tmdb_id},${s.season_number})"><img class="season-poster" src="${poster}" alt="${s.name || ""}" loading="lazy" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2748%27 height=%2772%27 fill=%27%231a1a24%27%3E%3Crect width=%2748%27 height=%2772%27/%3E%3C/svg%3E'"><div class="season-info"><div class="season-name">${s.name || t("seasons_title") + " " + s.season_number}</div><div class="season-meta">${s.episode_count || 0} ${t("episodes_title")}${airYear ? " · " + airYear : ""}</div></div><i class="fas fa-chevron-down season-chevron"></i></div><div class="episodes-list" id="episodes-${s.season_number}"><div class="episodes-loading"><i class="fas fa-circle-notch fa-spin"></i> ${t("loading_episodes")}</div></div></div>`;
    }).join("");
    seasonsEl.innerHTML = `<h3><i class="fas fa-layer-group"></i> ${t("seasons_title")}</h3>${seasonCards}`;
  } else seasonsEl.innerHTML = "";

  const castEl = document.getElementById("cast_section");
  if ((data.cast || []).length > 0) {
    const items = data.cast.map(c => {
      const photo = c.profile_path ? `https://image.tmdb.org/t/p/w185${c.profile_path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Crect width='60' height='60' fill='%231a1a24' rx='30'/%3E%3Ctext x='50%25' y='50%25' fill='%23555' font-size='24' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%91%A4%3C/text%3E%3C/svg%3E";
      return `<div class="cast-card"><img src="${photo}" alt="${c.name}" loading="lazy"><p>${c.name}${c.character ? `<br><span style="color:var(--primary);font-size:.58rem">${c.character}</span>` : ""}</p></div>`;
    }).join("");
    castEl.innerHTML = `<h3><i class="fas fa-users"></i> ${t("cast_title")}</h3><div class="cast-list">${items}</div>`;
  } else castEl.innerHTML = "";

  const trailerEl = document.getElementById("trailer_section");
  if (data.trailer) {
    const embedUrl = data.trailer.replace("watch?v=", "embed/").replace("youtu.be/", "www.youtube.com/embed/");
    trailerEl.innerHTML = `<h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3><button class="btn-trailer" onclick="afficherTrailer(this,'${embedUrl}')"><i class="fas fa-play"></i> ${t("see_trailer")}</button><iframe id="trailer_iframe" allowfullscreen style="display:none;width:100%;aspect-ratio:16/9;border-radius:12px;border:none;margin-top:10px;"></iframe>`;
  } else {
    const q = encodeURIComponent((data.title || "") + " trailer");
    trailerEl.innerHTML = `<h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3><a href="https://www.youtube.com/results?search_query=${q}" target="_blank" rel="noopener" class="btn-trailer"><i class="fas fa-search"></i> ${t("search_trailer")}</a>`;
  }

  const similarEl = document.getElementById("similar_section");
  const similarList = data.similar || [];
  if (similarList.length > 0) {
    const cards = similarList.map(s => {
      const poster = s.poster_path ? `https://image.tmdb.org/t/p/w200${s.poster_path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300' fill='%231a1a24'%3E%3Crect width='200' height='300'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='28' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
      const isTv = s.media_type === "tv" || s.first_air_date;
      const mediaType = isTv ? "tv" : "movie";
      return `<div class="movie-card" onclick="afficherDetails(${s.id},'${mediaType}')" style="cursor:pointer"><img src="${poster}" alt="${s.title || s.name || "?"}" loading="lazy" style="aspect-ratio:2/3;object-fit:cover"><div class="card-body"><h4>${s.title || s.name || "?"}</h4></div></div>`;
    }).join("");
    similarEl.innerHTML = `<h3>${t("similar_title")}</h3><div id="similar_cards">${cards}</div>`;
  } else similarEl.innerHTML = "";

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function afficherTrailer(btn, embedUrl) {
  const iframe = document.getElementById("trailer_iframe");
  if (iframe) {
    iframe.src = embedUrl;
    iframe.style.display = "block";
    btn.style.display = "none";
  }
}

// ════ SAISONS ════
const _loadedSeasons = {};
async function toggleSaison(seriesId, seasonNumber) {
  const card = document.getElementById(`season-${seasonNumber}`);
  if (!card) return;
  const episodesList = document.getElementById(`episodes-${seasonNumber}`);
  const isOpen = card.classList.contains("open");
  if (isOpen) {
    card.classList.remove("open");
    return;
  }
  card.classList.add("open");
  if (_loadedSeasons[`${seriesId}-${seasonNumber}`]) return;
  try {
    const res = await fetch(`/tv/${seriesId}/season/${seasonNumber}?lang=${getTMDBLang()}`);
    const data = await res.json();
    _loadedSeasons[`${seriesId}-${seasonNumber}`] = true;
    const episodes = data.episodes || [];
    if (episodes.length === 0) {
      episodesList.innerHTML = `<p style="padding:16px;color:var(--muted);font-size:.82rem;text-align:center">${t("no_synopsis")}</p>`;
      return;
    }
    episodesList.innerHTML = episodes.map(ep => {
      const still = ep.still_path ? `https://image.tmdb.org/t/p/w185${ep.still_path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='45' fill='%231a1a24'%3E%3Crect width='80' height='45'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='16' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
      const airDate = ep.air_date ? ep.air_date.split("-").reverse().join("/") : "";
      const overview = ep.overview || "";
      return `<div class="episode-item"><div class="episode-num">${ep.episode_number}</div><img class="episode-still" src="${still}" alt="" loading="lazy" onerror="this.style.display='none'"><div class="episode-body"><div class="episode-title">${ep.name || "Episode " + ep.episode_number}</div>${airDate ? `<div class="episode-date"><i class="fas fa-calendar" style="font-size:.6rem;opacity:.5"></i> ${airDate}</div>` : ""}${overview ? `<div class="episode-overview">${overview}</div>` : ""}</div></div>`;
    }).join("");
  } catch (e) {
    episodesList.innerHTML = `<p style="padding:16px;color:var(--error-text);font-size:.82rem;text-align:center"><i class="fas fa-exclamation-circle"></i> Erreur chargement épisodes</p>`;
  }
}

// ════ POLITIQUE DE CONFIDENTIALITÉ ════
function afficherPrivacy() {
  document.getElementById("hero").style.display = "none";
  document.getElementById("genre-nav").style.display = "none";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("privacy-page").style.display = "block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function cacherPrivacy() {
  document.getElementById("privacy-page").style.display = "none";
  retourAccueil();
}

// ════ INITIALISATION ════
window.addEventListener("scroll", () => {
  document.getElementById("back-top").classList.toggle("visible", window.scrollY > 400);
});
window.onload = () => {
  initLang();
  chargerTrending().then(() => {
    document.getElementById("hero").style.display = "block";
    document.getElementById("genre-nav").style.display = "flex";
  });
  document.addEventListener("keydown", e => {
    if (e.code === "Space" && document.getElementById("loading-overlay").classList.contains("active")) {
      e.preventDefault();
      gameJump();
    }
  });
  document.getElementById("game-canvas").addEventListener("touchstart", e => {
    e.preventDefault();
    gameJump();
  });
  if (!localStorage.getItem('cookies_accepted')) {
    document.getElementById('cookie-consent').style.display = 'flex';
  }
  // Construction du canvas de jeu s'il n'est pas déjà rempli
  const gameCanvas = document.getElementById("game-canvas");
  if (gameCanvas && !gameCanvas.querySelector(".game-ground")) {
    gameCanvas.innerHTML = `
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
      <div class="game-tap-hint" id="game-hint">TAP / ESPACE pour sauter</div>
    `;
  }
};