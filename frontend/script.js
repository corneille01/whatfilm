// ════ CACHE ════
const apiCache = {};
const CACHE_TTL = 300000;

function getCached(key) {
    const entry = apiCache[key];
    if (entry && (Date.now() - entry.time) < CACHE_TTL) return entry.data;
    return null;
}
function setCache(key, data) {
    apiCache[key] = { data, time: Date.now() };
}

// ════ SAFE FETCH ════
async function safeFetch(url, options = {}) {
    const res = await fetch(url, options);
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
        throw new Error(`Réponse inattendue du serveur (${res.status}). Réessayez dans quelques secondes.`);
    }
    const data = await res.json();
    return data;
}

// ════ DICTIONNAIRE INTERNATIONAL ════
const dict = {
  "en-US": {
    title: "WHICH MOVIE?",
    tagline: "Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder: "Paste TikTok/Insta link or type a movie name...",
    badge: "Shazam for movies",
    back_home: "Home", back_list: "Back to list", ai_conf: "AI Confidence", reset: "Reset",
    year: "Year", min_score: "Min score", sort_pop: "🔥 Popularity", sort_top: "⭐ Top rated",
    sort_asc: "Score ascending", sort_new: "🆕 Newest", sort_old: "📼 Oldest",
    no_streaming_country: "No streaming available in the US currently.", cancel: "Cancel",
    game_hint: "TAP / SPACE to jump",
    game_playing_msg: "🎬 We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",
    food_title: "Ready to watch?", food_desc: "Order popcorn & snacks via DoorDash!", food_btn: "Order",
    streaming_title: "Available on", searching: "Manual search",
    loading_home: "Loading trending...", not_found_title: "Movie not found",
    similar_title: "🍿 Similar movies", cast_title: "Cast", series_tag: "TV Series",
    trailer_title: "Trailer", scene_identified: "Scene identified", no_synopsis: "No synopsis available.",
    see_trailer: "Watch trailer", search_trailer: "Find trailer on YouTube",
    seasons_title: "Seasons", episodes_title: "Episodes", loading_episodes: "Loading episodes...",
    providers_country: "US", game_over: "GAME OVER — Score: ",
    filming_btn: "📍 Filmed Here",
    filming_title: "FILMING LOCATIONS",
    filming_subtitle: "Explore real-world locations from cinema & TV worldwide",
    filming_filter_country: "All countries",
    filming_filter_type: "All types",
    filming_filter_sort: "Most locations",
    filming_sort_count: "Most locations",
    filming_sort_rating: "Top rated",
    filming_sort_year: "Newest",
    filming_sort_title: "A–Z",
    filming_search: "Search a film…",
    filming_hotel_near: "Find hotels near this location →",
    filming_map_title: "Shooting map",
    filming_loading: "Loading catalogue…",
    filming_stats: "films · locations · countries",
    filming_filter_year: "Year",
    filming_near_me: "📍 Near me",
    filming_all_media: "All",
    filming_movies_only: "Movies",
    filming_tv_only: "TV Series",
    filming_layer_film: "Filming locations",
    filming_layer_hotel: "Hotels & stays",
    filming_layer_tourism: "Tourism offices",
    filming_cluster_toggle: "Cluster markers",
    filming_heatmap_toggle: "Heatmap",
    filming_fullscreen: "Fullscreen",
    err_server_busy: "The server is busy. Please retry in 30 seconds.",
    err_private: "This video is private or requires a login.",
    err_geo: "This video is not available in your region.",
    err_deleted: "This video has been deleted or no longer exists.",
    err_download: "Unable to download this video. Make sure it's public.",
    err_no_frames: "Could not extract images from this video.",
    err_timeout: "Analysis timed out. Try a shorter video.",
    err_session: "Session expired. Please retry.",
    err_generic: "An error occurred. Please try again.",
    err_low_confidence: "Movie not identified with enough confidence. Try searching manually.",
    search_manually: "Search manually",
    err_rate_limited: "Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily: "Daily limit reached. Come back tomorrow.",
    err_video_too_short: "Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large: "File too large. Try a shorter video.",
    err_video_blocked: "Video blocked for copyright reasons.",
    err_unsupported: "Unsupported platform or format.",
    genres: {
      horror: "Horror", action: "Action", comedy: "Comedy", scifi: "Sci-Fi",
      trending: "🔥 Trending", romance: "Romance", animation: "Animation",
      thriller: "Thriller", drama: "Drama", crime: "Crime",
      documentary: "Documentary", fantasy: "Fantasy", series: "📺 TV Series", family: "Family"
    }
  },
  "en-GB": {
    title: "WHICH MOVIE?", tagline: "Paste a TikTok, Reel or YouTube link — AI identifies the film in seconds",
    placeholder: "Paste TikTok/Insta link or type a movie name...", badge: "Shazam for movies",
    back_home: "Home", back_list: "Back to list", ai_conf: "AI Confidence", reset: "Reset",
    year: "Year", min_score: "Min score", sort_pop: "🔥 Popularity", sort_top: "⭐ Top rated",
    sort_asc: "Score ascending", sort_new: "🆕 Newest", sort_old: "📼 Oldest",
    no_streaming_country: "No streaming available in the UK currently.", cancel: "Cancel",
    game_hint: "TAP / SPACE to jump",
    game_playing_msg: "🎬 We're identifying the movie from your link…\nPlay while you wait — it takes about 30 seconds!",
    food_title: "Ready to watch?", food_desc: "Order popcorn & snacks via Deliveroo!", food_btn: "Order",
    streaming_title: "Available on", searching: "Manual search",
    loading_home: "Loading trending...", not_found_title: "Movie not found",
    similar_title: "🍿 Similar movies", cast_title: "Cast", series_tag: "TV Series",
    trailer_title: "Trailer", scene_identified: "Scene identified", no_synopsis: "No synopsis available.",
    see_trailer: "Watch trailer", search_trailer: "Find trailer on YouTube",
    seasons_title: "Seasons", episodes_title: "Episodes", loading_episodes: "Loading episodes...",
    providers_country: "GB", game_over: "GAME OVER — Score: ",
    filming_btn: "📍 Filmed Here",
    filming_title: "FILMING LOCATIONS",
    filming_subtitle: "Explore real-world locations from cinema & TV worldwide",
    filming_filter_country: "All countries",
    filming_filter_type: "All types",
    filming_filter_sort: "Most locations",
    filming_sort_count: "Most locations",
    filming_sort_rating: "Top rated",
    filming_sort_year: "Newest",
    filming_sort_title: "A–Z",
    filming_search: "Search a film…",
    filming_hotel_near: "Find hotels near this location →",
    filming_map_title: "Shooting map",
    filming_loading: "Loading catalogue…",
    filming_stats: "films · locations · countries",
    filming_filter_year: "Year",
    filming_near_me: "📍 Near me",
    filming_all_media: "All",
    filming_movies_only: "Movies",
    filming_tv_only: "TV Series",
    filming_layer_film: "Filming locations",
    filming_layer_hotel: "Hotels & stays",
    filming_layer_tourism: "Tourism offices",
    filming_cluster_toggle: "Cluster markers",
    filming_heatmap_toggle: "Heatmap",
    filming_fullscreen: "Fullscreen",
    err_server_busy: "The server is busy. Please retry in 30 seconds.",
    err_private: "This video is private or requires a login.",
    err_geo: "This video is not available in your region.",
    err_deleted: "This video has been deleted or no longer exists.",
    err_download: "Unable to download this video. Make sure it's public.",
    err_no_frames: "Could not extract images from this video.",
    err_timeout: "Analysis timed out. Try a shorter video.",
    err_session: "Session expired. Please retry.",
    err_generic: "An error occurred. Please try again.",
    err_low_confidence: "Movie not identified with enough confidence. Try searching manually.",
    search_manually: "Search manually",
    err_rate_limited: "Too many requests. Wait a minute before retrying.",
    err_rate_limited_daily: "Daily limit reached. Come back tomorrow.",
    err_video_too_short: "Video too short. Try a clip of at least 3 seconds.",
    err_file_too_large: "File too large. Try a shorter video.",
    err_video_blocked: "Video blocked for copyright reasons.",
    err_unsupported: "Unsupported platform or format.",
    genres: {
      horror: "Horror", action: "Action", comedy: "Comedy", scifi: "Sci-Fi",
      trending: "🔥 Trending", romance: "Romance", animation: "Animation",
      thriller: "Thriller", drama: "Drama", crime: "Crime",
      documentary: "Documentary", fantasy: "Fantasy", series: "📺 TV Series", family: "Family"
    }
  },
  fr: {
    title: "QUEL FILM ?", tagline: "Colle un lien TikTok, Reel ou YouTube — l'IA identifie le film en secondes",
    placeholder: "Colle un lien TikTok/Reel ou tape le nom d'un film...", badge: "Shazam pour les films",
    back_home: "Accueil", back_list: "Retour à la liste", ai_conf: "Confiance IA", reset: "Reset",
    year: "Année", min_score: "Note min", sort_pop: "🔥 Popularité", sort_top: "⭐ Mieux notés",
    sort_asc: "Note croissante", sort_new: "🆕 Plus récents", sort_old: "📼 Plus anciens",
    no_streaming_country: "Pas de streaming disponible en France actuellement.", cancel: "Annuler",
    game_hint: "TAP / ESPACE pour sauter",
    game_playing_msg: "🎬 On cherche le film de votre lien…\nJouez pendant l'analyse — ça prend environ 30 secondes !",
    food_title: "Prêt à regarder ce film ?", food_desc: "Commandez vos snacks via UberEats !", food_btn: "Commander",
    streaming_title: "Disponible sur", searching: "Recherche manuelle",
    loading_home: "Chargement des tendances...", not_found_title: "Film non identifié",
    similar_title: "🍿 Films similaires", cast_title: "Au casting", series_tag: "Série TV",
    trailer_title: "Bande-annonce", scene_identified: "Scène identifiée",
    no_synopsis: "Pas de synopsis disponible.", see_trailer: "Voir la bande-annonce",
    search_trailer: "Chercher la bande-annonce", seasons_title: "Saisons",
    episodes_title: "Épisodes", loading_episodes: "Chargement des épisodes...",
    providers_country: "FR", game_over: "GAME OVER — Score : ",
    filming_btn: "📍 Lieux de tournage",
    filming_title: "LIEUX DE TOURNAGE",
    filming_subtitle: "Explorez les vrais décors du cinéma mondial",
    filming_filter_country: "Tous les pays",
    filming_filter_type: "Tous les types",
    filming_filter_sort: "Plus de lieux",
    filming_sort_count: "Plus de lieux",
    filming_sort_rating: "Mieux notés",
    filming_sort_year: "Plus récents",
    filming_sort_title: "A–Z",
    filming_search: "Rechercher un film…",
    filming_hotel_near: "Trouver un hôtel près du lieu →",
    filming_map_title: "Carte des tournages",
    filming_loading: "Chargement du catalogue…",
    filming_stats: "films · lieux · pays",
    filming_filter_year: "Année",
    filming_near_me: "📍 Près de moi",
    filming_all_media: "Tout",
    filming_movies_only: "Films",
    filming_tv_only: "Séries",
    filming_layer_film: "Lieux de tournage",
    filming_layer_hotel: "Hôtels & hébergements",
    filming_layer_tourism: "Offices de tourisme",
    filming_cluster_toggle: "Regrouper les marqueurs",
    filming_heatmap_toggle: "Carte de chaleur",
    filming_fullscreen: "Plein écran",
    err_server_busy: "Le serveur est actuellement surchargé. Réessayez dans 30 secondes.",
    err_private: "Cette vidéo est privée ou nécessite une connexion.",
    err_geo: "Cette vidéo n'est pas disponible dans votre région.",
    err_deleted: "Cette vidéo a été supprimée ou n'existe plus.",
    err_download: "Impossible de télécharger cette vidéo. Vérifiez qu'elle est publique et accessible.",
    err_no_frames: "Impossible d'extraire des images de cette vidéo.",
    err_timeout: "L'analyse a pris trop de temps. Essayez avec une vidéo plus courte.",
    err_session: "Session expirée. Relancez l'analyse.",
    err_generic: "Une erreur s'est produite. Réessayez dans quelques instants.",
    err_low_confidence: "Film non identifié avec certitude. Essayez de le rechercher manuellement.",
    search_manually: "Rechercher manuellement",
    err_rate_limited: "Trop de requêtes. Attendez une minute avant de réessayer.",
    err_rate_limited_daily: "Limite journalière atteinte. Revenez demain.",
    err_video_too_short: "Vidéo trop courte. Essayez un extrait d'au moins 3 secondes.",
    err_file_too_large: "Fichier trop volumineux. Essayez une vidéo plus courte.",
    err_video_blocked: "Vidéo bloquée pour droits d'auteur.",
    err_unsupported: "Plateforme ou format non supporté.",
    genres: {
      horror: "Horreur", action: "Action", comedy: "Comédie", scifi: "Sci-Fi",
      trending: "🔥 Tendances", romance: "Romance", animation: "Animation",
      thriller: "Thriller", drama: "Drame", crime: "Crime",
      documentary: "Documentaire", fantasy: "Fantastique", series: "📺 Séries TV", family: "Famille"
    }
  },
  es: {
    title: "¿QUÉ PELÍCULA?", tagline: "Pega un enlace de TikTok o Reel — la IA identifica la película",
    placeholder: "Pega enlace TikTok/Reel o escribe un título...", badge: "Shazam para películas",
    back_home: "Inicio", back_list: "Volver a la lista", ai_conf: "Confianza IA", reset: "Restablecer",
    year: "Año", min_score: "Nota mínima", sort_pop: "🔥 Popularidad", sort_top: "⭐ Mejor valoradas",
    sort_asc: "Nota ascendente", sort_new: "🆕 Más recientes", sort_old: "📼 Más antiguas",
    no_streaming_country: "Sin streaming disponible actualmente.", cancel: "Cancelar",
    game_hint: "TAP / ESPACIO para saltar",
    game_playing_msg: "🎬 Estamos identificando la película…\n¡Juega mientras esperas, tarda unos 30 segundos!",
    food_title: "¿Listo para ver la película?", food_desc: "¡Pide snacks y palomitas!", food_btn: "Pedir",
    streaming_title: "Disponible en", searching: "Buscar manualmente",
    loading_home: "Cargando tendencias...", not_found_title: "Película no encontrada",
    similar_title: "🍿 Películas similares", cast_title: "Reparto", series_tag: "Serie TV",
    trailer_title: "Tráiler", scene_identified: "Escena identificada", no_synopsis: "Sin sinopsis disponible.",
    see_trailer: "Ver tráiler", search_trailer: "Buscar tráiler en YouTube",
    seasons_title: "Temporadas", episodes_title: "Episodios", loading_episodes: "Cargando episodios...",
    providers_country: "ES", game_over: "GAME OVER — Puntuación: ",
    filming_btn: "📍 Rodado aquí",
    filming_title: "LOCALIZACIONES DE RODAJE",
    filming_subtitle: "Explora los escenarios reales del cine mundial",
    filming_filter_country: "Todos los países",
    filming_filter_type: "Todos los tipos",
    filming_filter_sort: "Más localizaciones",
    filming_sort_count: "Más localizaciones",
    filming_sort_rating: "Mejor valoradas",
    filming_sort_year: "Más recientes",
    filming_sort_title: "A–Z",
    filming_search: "Buscar una película…",
    filming_hotel_near: "Buscar hoteles cerca →",
    filming_map_title: "Mapa de rodajes",
    filming_loading: "Cargando catálogo…",
    filming_stats: "películas · localizaciones · países",
    filming_filter_year: "Año",
    filming_near_me: "📍 Cerca de mí",
    filming_all_media: "Todo",
    filming_movies_only: "Películas",
    filming_tv_only: "Series",
    filming_layer_film: "Localizaciones",
    filming_layer_hotel: "Hoteles",
    filming_layer_tourism: "Oficinas de turismo",
    filming_cluster_toggle: "Agrupar marcadores",
    filming_heatmap_toggle: "Mapa de calor",
    filming_fullscreen: "Pantalla completa",
    err_server_busy: "El servidor está ocupado. Reintenta en 30 segundos.",
    err_private: "Este vídeo es privado o requiere inicio de sesión.",
    err_geo: "Este vídeo no está disponible en tu región.",
    err_deleted: "Este vídeo fue eliminado o ya no existe.",
    err_download: "No se puede descargar este vídeo. Verifica que sea público.",
    err_no_frames: "No se pudieron extraer imágenes del vídeo.",
    err_timeout: "El análisis tardó demasiado. Prueba con un vídeo más corto.",
    err_session: "Sesión expirada. Reinicia el análisis.",
    err_generic: "Ocurrió un error. Inténtalo de nuevo.",
    err_low_confidence: "Película no identificada con certeza. Busca manualmente.",
    search_manually: "Buscar manualmente",
    err_rate_limited: "Demasiadas solicitudes. Espera un minuto antes de reintentar.",
    err_rate_limited_daily: "Límite diario alcanzado. Vuelve mañana.",
    err_video_too_short: "Video demasiado corto. Prueba con un clip de al menos 3 segundos.",
    err_file_too_large: "Archivo demasiado grande. Prueba con un video más corto.",
    err_video_blocked: "Video bloqueado por derechos de autor.",
    err_unsupported: "Plataforma o formato no compatible.",
    genres: {
      horror: "Terror", action: "Acción", comedy: "Comedia", scifi: "Ciencia Ficción",
      trending: "🔥 Tendencias", romance: "Romance", animation: "Animación",
      thriller: "Thriller", drama: "Drama", crime: "Crimen",
      documentary: "Documental", fantasy: "Fantasía", series: "📺 Series TV", family: "Familia"
    }
  },
  de: {
    title: "WELCHER FILM?", tagline: "TikTok- oder Reel-Link einfügen — KI erkennt den Film in Sekunden",
    placeholder: "TikTok/Insta Link oder Filmtitel eingeben...", badge: "Shazam für Filme",
    back_home: "Startseite", back_list: "Zurück zur Liste", ai_conf: "KI-Konfidenz", reset: "Zurücksetzen",
    year: "Jahr", min_score: "Mindestbewertung", sort_pop: "🔥 Beliebtheit", sort_top: "⭐ Bestbewertet",
    sort_asc: "Bewertung aufsteigend", sort_new: "🆕 Neueste", sort_old: "📼 Älteste",
    no_streaming_country: "Kein Streaming in Deutschland verfügbar.", cancel: "Abbrechen",
    game_hint: "TAP / LEERTASTE zum Springen",
    game_playing_msg: "🎬 Wir identifizieren den Film…\nSpiel während du wartest — dauert ca. 30 Sekunden!",
    food_title: "Bereit zum Anschauen?", food_desc: "Bestelle Snacks und Popcorn!", food_btn: "Bestellen",
    streaming_title: "Verfügbar auf", searching: "Manuell suchen",
    loading_home: "Trends werden geladen...", not_found_title: "Film nicht gefunden",
    similar_title: "🍿 Ähnliche Filme", cast_title: "Besetzung", series_tag: "TV-Serie",
    trailer_title: "Trailer", scene_identified: "Szene identifiziert", no_synopsis: "Keine Beschreibung verfügbar.",
    see_trailer: "Trailer ansehen", search_trailer: "Trailer auf YouTube suchen",
    seasons_title: "Staffeln", episodes_title: "Folgen", loading_episodes: "Folgen werden geladen...",
    providers_country: "DE", game_over: "GAME OVER — Punkte: ",
    filming_btn: "📍 Drehorte",
    filming_title: "DREHORTE",
    filming_subtitle: "Entdecke echte Filmschauplätze weltweit",
    filming_filter_country: "Alle Länder",
    filming_filter_type: "Alle Typen",
    filming_filter_sort: "Meiste Drehorte",
    filming_sort_count: "Meiste Drehorte",
    filming_sort_rating: "Bestbewertet",
    filming_sort_year: "Neueste",
    filming_sort_title: "A–Z",
    filming_search: "Film suchen…",
    filming_hotel_near: "Hotel in der Nähe finden →",
    filming_map_title: "Drehort-Karte",
    filming_loading: "Katalog wird geladen…",
    filming_stats: "Filme · Drehorte · Länder",
    filming_filter_year: "Jahr",
    filming_near_me: "📍 In meiner Nähe",
    filming_all_media: "Alle",
    filming_movies_only: "Filme",
    filming_tv_only: "Serien",
    filming_layer_film: "Drehorte",
    filming_layer_hotel: "Hotels",
    filming_layer_tourism: "Touristikbüros",
    filming_cluster_toggle: "Marker gruppieren",
    filming_heatmap_toggle: "Heatmap",
    filming_fullscreen: "Vollbild",
    err_server_busy: "Der Server ist ausgelastet. Versuche es in 30 Sekunden.",
    err_private: "Dieses Video ist privat oder erfordert einen Login.",
    err_geo: "Dieses Video ist in deiner Region nicht verfügbar.",
    err_deleted: "Dieses Video wurde gelöscht oder existiert nicht mehr.",
    err_download: "Video kann nicht heruntergeladen werden. Stelle sicher, dass es öffentlich ist.",
    err_no_frames: "Bilder konnten nicht aus dem Video extrahiert werden.",
    err_timeout: "Analyse hat zu lange gedauert. Versuche ein kürzeres Video.",
    err_session: "Sitzung abgelaufen. Starte die Analyse neu.",
    err_generic: "Ein Fehler ist aufgetreten. Versuche es erneut.",
    err_low_confidence: "Film nicht sicher identifiziert. Suche manuell.",
    search_manually: "Manuell suchen",
    err_rate_limited: "Zu viele Anfragen. Warte eine Minute, bevor du es erneut versuchst.",
    err_rate_limited_daily: "Tägliches Limit erreicht. Komm morgen wieder.",
    err_video_too_short: "Video zu kurz. Versuche einen Clip von mindestens 3 Sekunden.",
    err_file_too_large: "Datei zu groß. Versuche ein kürzeres Video.",
    err_video_blocked: "Video aus urheberrechtlichen Gründen gesperrt.",
    err_unsupported: "Nicht unterstützte Plattform oder Format.",
    genres: {
      horror: "Horror", action: "Action", comedy: "Komödie", scifi: "Science-Fiction",
      trending: "🔥 Trends", romance: "Romantik", animation: "Animation",
      thriller: "Thriller", drama: "Drama", crime: "Krimi",
      documentary: "Dokumentarfilm", fantasy: "Fantasy", series: "📺 TV-Serien", family: "Familie"
    }
  },
  zh: {
    title: "什么电影？", tagline: "粘贴 TikTok 或 Reel 链接 — AI 即刻识别电影",
    placeholder: "粘贴链接或输入电影名...", badge: "电影识别神器",
    back_home: "首页", back_list: "返回列表", ai_conf: "AI 置信度", reset: "重置",
    year: "年份", min_score: "最低评分", sort_pop: "🔥 热度", sort_top: "⭐ 最高评分",
    sort_asc: "评分升序", sort_new: "🆕 最新", sort_old: "📼 最早",
    no_streaming_country: "暂无可用的流媒体。", cancel: "取消",
    game_hint: "点击 / 空格键跳跃",
    game_playing_msg: "🎬 正在识别您的视频中的电影…\n请玩游戏等待，大约需要30秒！",
    food_title: "准备好看电影了吗？", food_desc: "立即订购爆米花和零食！", food_btn: "下单",
    streaming_title: "可在以下平台观看", searching: "手动搜索", loading_home: "加载热门中...",
    not_found_title: "未找到影片", similar_title: "🍿 相似影片", cast_title: "演员表",
    series_tag: "电视剧", trailer_title: "预告片", scene_identified: "识别场景",
    no_synopsis: "暂无简介。", see_trailer: "观看预告片", search_trailer: "在 YouTube 上搜索预告片",
    seasons_title: "季", episodes_title: "集", loading_episodes: "加载剧集中...",
    providers_country: "CN", game_over: "游戏结束 — 得分：",
    filming_btn: "📍 拍摄地",
    filming_title: "拍摄地点",
    filming_subtitle: "探索全球电影真实拍摄地",
    filming_filter_country: "所有国家",
    filming_filter_type: "所有类型",
    filming_filter_sort: "最多地点",
    filming_sort_count: "最多地点",
    filming_sort_rating: "最高评分",
    filming_sort_year: "最新",
    filming_sort_title: "A–Z",
    filming_search: "搜索电影…",
    filming_hotel_near: "查找附近酒店 →",
    filming_map_title: "拍摄地图",
    filming_loading: "加载目录中…",
    filming_stats: "部电影 · 拍摄地 · 个国家",
    filming_filter_year: "年份",
    filming_near_me: "📍 附近",
    filming_all_media: "全部",
    filming_movies_only: "电影",
    filming_tv_only: "电视剧",
    filming_layer_film: "拍摄地点",
    filming_layer_hotel: "酒店",
    filming_layer_tourism: "旅游局",
    filming_cluster_toggle: "聚合标记",
    filming_heatmap_toggle: "热力图",
    filming_fullscreen: "全屏",
    err_server_busy: "服务器繁忙，请30秒后重试。",
    err_private: "该视频为私密视频或需要登录。",
    err_geo: "该视频在您所在地区不可用。",
    err_deleted: "该视频已被删除或不再存在。",
    err_download: "无法下载此视频，请确认视频为公开状态。",
    err_no_frames: "无法从视频中提取图像。",
    err_timeout: "分析超时，请尝试较短的视频。",
    err_session: "会话已过期，请重新分析。",
    err_generic: "发生错误，请重试。",
    err_low_confidence: "无法确定识别电影，请手动搜索。",
    search_manually: "手动搜索",
    err_rate_limited: "请求过多。请等待一分钟后再试。",
    err_rate_limited_daily: "已达每日限额。请明天再来。",
    err_video_too_short: "视频太短。请尝试至少3秒的片段。",
    err_file_too_large: "文件太大。请尝试较短的视频。",
    err_video_blocked: "视频因版权原因被屏蔽。",
    err_unsupported: "不支持的平台或格式。",
    genres: {
      horror: "恐怖", action: "动作", comedy: "喜剧", scifi: "科幻",
      trending: "🔥 热门", romance: "爱情", animation: "动画",
      thriller: "惊悚", drama: "剧情", crime: "犯罪",
      documentary: "纪录片", fantasy: "奇幻", series: "📺 电视剧", family: "家庭"
    }
  }
};

// ════ CONFIG STREAMING ════
const STREAMING_META = {
  Netflix: { color: "#e50914", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/24px-Netflix_2015_logo.svg.png" },
  "Amazon Prime Video": { color: "#00a8e0", logo: "" },
  "Disney+": { color: "#113ccf", logo: "" },
  "Apple TV+": { color: "#a2aaad", logo: "" },
  "Paramount+": { color: "#0064ff", logo: "" }, "Canal+": { color: "#000", logo: "" },
  OCS: { color: "#e85d04", logo: "" }, Crunchyroll: { color: "#f47521", logo: "" },
  Mubi: { color: "#2196f3", logo: "" }, Hulu: { color: "#1ce783", logo: "" }
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

// ════ ÉTAT CATALOGUE LIEUX ════
let _filmingMap = null;
let _filmingMarkerClusterGroup = null;
let _filmingHotelLayer = null;
let _filmingTourismLayer = null;
let _filmingFilmLayer = null;
let _filmingHeatmapLayer = null;
let _filmingLayerControl = null;
let _filmingCurrentPage = 1;
let _filmingCurrentCountry = "";
let _filmingCurrentCity = "";
let _filmingCurrentType = "";
let _filmingCurrentSort = "count_locations";
let _filmingCurrentQ = "";
let _filmingStats = null;
let _filmingCountries = [];
let _filmingAllMarkers = []; // [{lat,lng,title,poster,tmdb_id,location_name,country}]
let _filmingLeafletReady = false;

// ════ TRADUCTIONS ERREURS ════
function tErr(code) {
  const d = dict[currentLang] || dict.fr;
  const map = {
    server_busy: d.err_server_busy,
    video_private: d.err_private,
    video_geo: d.err_geo,
    video_deleted: d.err_deleted,
    download_failed: d.err_download,
    download_empty: d.err_download,
    no_frames: d.err_no_frames,
    timeout: d.err_timeout,
    session_expired: d.err_session,
    unexpected: d.err_generic,
    low_confidence: d.err_low_confidence,
    rate_limited: d.err_rate_limited || "Trop de requêtes. Attendez une minute.",
    rate_limited_daily: d.err_rate_limited_daily || "Limite journalière atteinte.",
    video_too_short: d.err_video_too_short || "Vidéo trop courte (moins de 3s).",
    file_too_large: d.err_file_too_large || "Fichier trop volumineux.",
    download_timeout: d.err_timeout,
    video_blocked: d.err_video_blocked || "Vidéo bloquée pour droits d'auteur.",
    unsupported_platform: d.err_unsupported || "Plateforme non supportée.",
    unsupported: d.err_unsupported || "Format non supporté.",
  };
  return map[code] || d.err_generic;
}

// ════ AUDIO ════
let audioCtx = null, bgMusicGain = null, bgMusicInterval = null;
function initAudio() {
  if (audioCtx) return;
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    bgMusicGain = audioCtx.createGain();
    bgMusicGain.gain.value = 0.12;
    bgMusicGain.connect(audioCtx.destination);
  } catch(e) {}
}
function playTone(freq, duration, type = 'square', volume = 0.1) {
  if (!audioCtx) return;
  try {
    const osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
    osc.type = type; osc.frequency.value = freq;
    gain.gain.setValueAtTime(volume, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.start(); osc.stop(audioCtx.currentTime + duration);
  } catch(e) {}
}
function playCoinSound() { playTone(988, 0.08); setTimeout(() => playTone(1319, 0.1), 60); }
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
    const freq = notes[i % notes.length], dur = durations[i % durations.length];
    try {
      const osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
      osc.type = 'square'; osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
      osc.connect(gain); gain.connect(bgMusicGain);
      osc.start(); osc.stop(audioCtx.currentTime + dur);
    } catch(e) {}
    i++;
  }, 250);
}
function stopBgMusic() { clearInterval(bgMusicInterval); bgMusicInterval = null; }

// ════ UTILITAIRES DE LANGUE ════
function getLangCode() { const m = { "en-US": "en-US", "en-GB": "en-GB", fr: "fr-FR", es: "es-ES", de: "de-DE", zh: "zh-CN" }; return m[currentLang] || "fr-FR"; }
function getRegionCode() { return (dict[currentLang] || dict.fr).providers_country || "FR"; }
function getTMDBLang() { const m = { "en-US": "en", "en-GB": "en", fr: "fr", es: "es", de: "de", zh: "zh" }; return m[currentLang] || "fr"; }
function t(key) { return (dict[currentLang] || dict.fr)[key] || key; }
function tg(key) { return ((dict[currentLang] || dict.fr).genres || {})[key] || key; }

function initLang() {
  const pathLang = window.location.pathname.replace(/\//g, "");
  const pathMap = { en: "en-US", "en-US": "en-US", "en-GB": "en-GB", fr: "fr", es: "es", de: "de", zh: "zh" };
  if (pathMap[pathLang]) currentLang = pathMap[pathLang];
  document.getElementById("lang-selector").value = currentLang;
  applyLang(); genererNav();
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
  const selNote = document.querySelector("#filtre-note option");
  if (selNote) selNote.textContent = "⭐ " + (langData.min_score || "Note min");
  const selAnnee = document.querySelector("#filtre-annee option");
  if (selAnnee) selAnnee.textContent = "📅 " + (langData.year || "Année");
  const btr = document.getElementById("btn-reset");
  if (btr) btr.innerHTML = `<i class="fas fa-times"></i> ${langData.reset || "Reset"}`;
  // Bouton filming dans la nav
  const btnFilming = document.getElementById("btn-genre-filming");
  if (btnFilming) btnFilming.textContent = langData.filming_btn || "📍 Lieux de tournage";
}
function genererNav() {
  const nav = document.getElementById("genre-nav");
  const g = dict[currentLang]?.genres || dict.fr.genres;
  const ld = dict[currentLang] || dict.fr;
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
    <a class="btn-genre trending" onclick="chargerTrending()"><i class="fas fa-bolt"></i> ${g.trending}</a>
    <a class="btn-genre filming" id="btn-genre-filming" onclick="chargerLieuxDeTournage()"><i class="fas fa-map-marker-alt"></i> ${ld.filming_btn || "📍 Lieux de tournage"}</a>`;
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
  currentLang = newLang; applyLang(); genererNav();
  const langPath = { "en-US": "en", "en-GB": "en-GB", fr: "fr", es: "es", de: "de", zh: "zh" }[currentLang] || "fr";
  history.replaceState(null, "", "/" + langPath);
  const detailPage = document.getElementById("page-film-detail"), gridPage = document.getElementById("genre-grid");
  if (currentMovieId && detailPage.style.display !== "none") { afficherDetails(currentMovieId, currentMediaType); return; }
  if (gridPage.style.display !== "none") {
    if (currentGenreName === "trending") chargerTrending();
    else if (currentGenreName === "series") chargerSeries();
    else if (currentGenreName === "filming") chargerLieuxDeTournage();
    else if (currentGenreName) chargerGenre(currentGenreName, currentPage);
    return;
  }
  chargerTrending().then(() => { document.getElementById("hero").style.display = "block"; document.getElementById("genre-nav").style.display = "flex"; });
}

// ════ ERREURS ════
function afficherErreur(msg) {
  const el = document.getElementById("error-message");
  document.getElementById("error-text").textContent = msg;
  el.classList.add("visible"); el.style.display = "flex";
  setTimeout(cacherErreur, 10000);
}
function cacherErreur() { const el = document.getElementById("error-message"); el.classList.remove("visible"); el.style.display = "none"; }
function toast(msg, dur = 3000) { const t = document.getElementById("toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), dur); }

function afficherErreurRiche(data) {
  const d = dict[currentLang] || dict.fr;
  const code = data.code || "unexpected";
  const msg = data.message || tErr(code);
  const searchQ = encodeURIComponent(document.getElementById("input_global").value.trim() || "");
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame();
  document.getElementById("genre-grid").style.display = "block";
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("hero").style.display = "none";
  document.getElementById("filtres-bar").style.display = "none";
  document.getElementById("genre-title").innerText = "";
  const icon = { video_private:"🔒",video_geo:"🌍",video_deleted:"🗑️",download_failed:"📵",server_busy:"⏳",no_frames:"🖼️",timeout:"⏱️",session_expired:"🔄",low_confidence:"🔍" }[code] || "⚠️";
  const retryBtn = (code==="server_busy"||code==="timeout"||code==="unexpected")
    ? `<button class="btn-stream" style="margin-top:8px" onclick="retourAccueil()"><i class="fas fa-redo"></i> Réessayer</button>` : "";
  document.getElementById("movie-cards").innerHTML = `
    <div style="grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 24px;max-width:520px;margin:0 auto;gap:16px;">
      <div style="font-size:3.5rem;line-height:1;">${icon}</div>
      <h3 style="color:var(--text);font-size:1.2rem;margin:0;">${msg}</h3>
      <p style="color:var(--muted);font-size:0.85rem;margin:0;line-height:1.6;">${d.search_manually||"Recherchez le film manuellement :"}</p>
      <div class="streaming-buttons" style="gap:10px;flex-wrap:wrap;justify-content:center;">
        <button class="btn-stream" onclick="document.getElementById('input_global').value='';document.getElementById('input_global').focus();"><i class="fas fa-search"></i> ${d.search_manually||"Rechercher"}</button>
        ${searchQ?`<a href="https://www.google.com/search?q=${searchQ}+film" target="_blank" rel="noopener" class="btn-stream"><i class="fab fa-google"></i> Google</a><a href="https://www.youtube.com/results?search_query=${searchQ}+film+trailer" target="_blank" rel="noopener" class="btn-stream" style="border-color:#ff0000"><i class="fab fa-youtube"></i> YouTube</a><a href="https://www.themoviedb.org/search?query=${searchQ}" target="_blank" rel="noopener" class="btn-stream"><i class="fas fa-film"></i> TMDB</a>`:""}
        ${retryBtn}
      </div>
    </div>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ════ BARRE DE RECHERCHE ════
function majBtnClear() { document.getElementById("btn-clear").classList.toggle("visible", document.getElementById("input_global").value.length > 0); }
function effacerRecherche() { document.getElementById("input_global").value = ""; document.getElementById("btn-clear").classList.remove("visible"); document.getElementById("input_global").focus(); }

// ════ NAVIGATION ════
function _hideAllPages() {
  document.getElementById("page-film-detail").style.display = "none";
  document.getElementById("genre-grid").style.display = "none";
  document.getElementById("privacy-page").style.display = "none";
  document.getElementById("filming-page").style.display = "none";
  document.getElementById("hero").style.display = "none";
  document.getElementById("genre-nav").style.display = "none";
}
function retourAccueil() {
  cacherErreur();
  _hideAllPages();
  document.getElementById("hero").style.display = "block";
  document.getElementById("genre-nav").style.display = "flex";
  document.getElementById("platform-nav").classList.remove("visible");
  lastGrid = null; currentMovieId = null; navStack = [];
}
function retourArriere() {
  if (navStack.length > 0) { const prev = navStack.pop(); afficherDetails(prev.id, prev.type); }
  else { document.getElementById("page-film-detail").style.display = "none"; if (lastGrid) document.getElementById("genre-grid").style.display = "block"; else retourAccueil(); }
}
function hideHero() { document.getElementById("hero").style.display = "none"; document.getElementById("genre-nav").style.display = "flex"; }

// ════ RECHERCHE GLOBALE ════
async function gererRechercheGlobal() {
    const input = document.getElementById("input_global").value.trim();
    if (!input) return;
    cacherErreur();
    document.getElementById("genre-grid").style.display = "none";
    document.getElementById("page-film-detail").style.display = "none";
    document.getElementById("filming-page").style.display = "none";
    const isLink = /^https?:\/\//i.test(input) && (
      /tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com/.test(input) ||
      /instagram\.com/.test(input) || /youtube\.com|youtu\.be/.test(input) ||
      /twitter\.com|x\.com/.test(input) || /facebook\.com|fb\.watch/.test(input) ||
      /dailymotion\.com|dai\.ly/.test(input) || /bilibili\.com/.test(input) ||
      /snapchat\.com/.test(input) || /vimeo\.com/.test(input) ||
      /twitch\.tv/.test(input) || /linkedin\.com/.test(input) ||
      /reddit\.com|redd\.it/.test(input) || /pinterest\.|pin\.it/.test(input) ||
      /bit\.ly|t\.co|tinyurl\.com|ow\.ly|buff\.ly|short\.io|lnk\.to/.test(input)
    ) || /^https?:\/\//i.test(input);
    if (isLink) { demarrerPub(); analyserVideo(input); }
    else {
        hideHero();
        try {
            const data = await safeFetch(`/rechercher?query=${encodeURIComponent(input)}&lang=${getTMDBLang()}`);
            if (data.status === "error") { afficherErreur(data.message || t("err_generic")); return; }
            afficherResultatsRecherche(data, input);
        } catch (e) { afficherErreur(t("err_generic") + " — " + e.message); }
    }
}

// ════ ANNULER ANALYSE ════
function annulerAnalyse() {
  if (analysisAbortController) analysisAbortController.abort();
  _adFinished = true; _analysisResult = null;
  document.getElementById('ad-modal').style.display = 'none';
  clearInterval(_adCountdownInterval);
  document.getElementById("loading-overlay").classList.remove("active");
  stopGame(); retourAccueil();
}

// ════ MINI-JEU ════
let gameState = {
  running: false, score: 0, lives: 3, level: 1,
  heroY: 0, heroVY: 0, jumping: false,
  obstacles: [], coins: [], frame: 0, speed: 3,
  rafId: null, dead: false, started: false, lastTime: 0
};
function gameJump() {
  if (!gameState.running || gameState.dead) { startGame(); return; }
  if (!gameState.jumping) { gameState.heroVY = -9; gameState.jumping = true; }
}
function _hideGameMsgBanner() { const b = document.getElementById("game-msg-banner"); if (b) b.style.display = "none"; }
function startGame() {
  stopGame();
  Object.assign(gameState, { running:true,score:0,lives:3,level:1,heroY:0,heroVY:0,jumping:false,obstacles:[],coins:[],frame:0,speed:3,dead:false,started:true,lastTime:0 });
  const canvas = document.getElementById("game-canvas");
  if (canvas) canvas.querySelectorAll(".game-obstacle,.game-coin").forEach(el=>el.remove());
  const banner = document.getElementById("game-msg-banner");
  if (banner) { banner.innerHTML=(t("game_playing_msg")||"🎬 On cherche votre film…").replace(/\n/g,"<br>"); banner.style.display="block"; }
  const hint = document.getElementById("game-hint");
  if (hint) { hint.textContent=t("game_hint")||"TAP / ESPACE pour sauter"; hint.style.display="block"; }
  initAudio(); startBgMusic();
  gameState.rafId = requestAnimationFrame(gameLoop);
}
function stopGame() {
  if (gameState.rafId) { cancelAnimationFrame(gameState.rafId); gameState.rafId=null; }
  gameState.running = false; stopBgMusic();
  const canvas = document.getElementById("game-canvas");
  if (canvas) canvas.querySelectorAll(".game-obstacle,.game-coin").forEach(el=>el.remove());
  _hideGameMsgBanner();
}
let _lastFrameTime = 0;
const TARGET_FPS = 60, FRAME_MS = 1000/TARGET_FPS;
function gameLoop(timestamp) {
  if (!gameState.running) return;
  const delta = timestamp - _lastFrameTime;
  if (delta < FRAME_MS - 2) { gameState.rafId=requestAnimationFrame(gameLoop); return; }
  _lastFrameTime = timestamp; gameState.frame++;
  const canvas = document.getElementById("game-canvas"); if (!canvas) return;
  const W = canvas.offsetWidth||380;
  const hero = document.getElementById("game-hero"); if (!hero) return;
  if (gameState.jumping) {
    gameState.heroVY += 0.55; gameState.heroY -= gameState.heroVY;
    if (gameState.heroY<=0) { gameState.heroY=0; gameState.heroVY=0; gameState.jumping=false; }
  }
  hero.style.bottom = 28+gameState.heroY+"px";
  gameState.speed = 3+Math.floor(gameState.score/50)*0.4;
  gameState.level = Math.floor(gameState.score/50)+1;
  const lvlEl = document.getElementById("game-level"); if(lvlEl) lvlEl.textContent="LVL "+gameState.level;
  const obsInterval = Math.max(55,110-gameState.level*4);
  if (gameState.frame%obsInterval===0) {
    const obs=document.createElement("div"); obs.className="game-obstacle";
    obs.textContent=["🌵","🧱","🔮","💀","⚡"][Math.floor(Math.random()*5)];
    obs.style.cssText=`left:${W}px;bottom:28px;`; canvas.appendChild(obs);
    gameState.obstacles.push({el:obs,x:W});
  }
  if (gameState.frame%80===40) {
    const coin=document.createElement("div"); coin.className="game-coin"; coin.textContent="🪙";
    const cy=50+Math.random()*60; coin.style.cssText=`left:${W}px;bottom:${28+cy}px;`;
    canvas.appendChild(coin); gameState.coins.push({el:coin,x:W,y:cy});
  }
  gameState.obstacles = gameState.obstacles.filter(ob => {
    ob.x -= gameState.speed; ob.el.style.left=ob.x+"px";
    const hit = ob.x>40&&ob.x<90&&gameState.heroY<35;
    if (hit) {
      gameState.lives--;
      const livesEl=document.getElementById("game-lives"); if(livesEl) livesEl.textContent="❤️".repeat(Math.max(0,gameState.lives));
      ob.el.remove(); if(gameState.lives<=0){gameOver();return false;} return false;
    }
    if(ob.x<-40){ob.el.remove();return false;} return true;
  });
  gameState.coins = gameState.coins.filter(c => {
    c.x -= gameState.speed; c.el.style.left=c.x+"px";
    const hit=c.x>40&&c.x<90&&gameState.heroY>c.y-15&&gameState.heroY<c.y+35;
    if(hit){gameState.score+=5;c.el.remove();playCoinSound();return false;}
    if(c.x<-40){c.el.remove();return false;} return true;
  });
  if(gameState.frame%10===0) gameState.score++;
  const scoreEl=document.getElementById("game-score"); if(scoreEl) scoreEl.textContent=gameState.score;
  gameState.rafId = requestAnimationFrame(gameLoop);
}
function gameOver() {
  gameState.running=false; gameState.dead=true;
  if(gameState.rafId){cancelAnimationFrame(gameState.rafId);gameState.rafId=null;}
  playGameOverSound(); stopBgMusic(); _hideGameMsgBanner();
  const hint=document.getElementById("game-hint"); if(hint){hint.textContent=t("game_over")+gameState.score+" — TAP";hint.style.display="block";}
}

// ════ ANALYSE VIDÉO ════
async function analyserVideo(lien) {
  hideHero(); _adFinished=false; _analysisResult=null;
  const lastAd=parseInt(localStorage.getItem('last_ad')||'0');
  const showAd=Date.now()-lastAd>30*60*1000;
  if(showAd){localStorage.setItem('last_ad',Date.now().toString());demarrerPub();}else{_adFinished=true;}
  const overlay=document.getElementById("loading-overlay"); overlay.classList.add("active"); startGame();
  let progress=0; const progressBar=document.getElementById("prog-fill"); const percentLabel=document.getElementById("prog-percent");
  let progInterval=setInterval(()=>{if(progress<88){progress+=Math.random()*8+3;if(progress>88)progress=88;if(progressBar)progressBar.style.width=progress+"%";if(percentLabel)percentLabel.textContent=Math.round(progress)+"%";}},900);
  analysisAbortController=new AbortController(); const signal=analysisAbortController.signal;
  try {
    const res=await fetch("/analyser",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:lien,lang:getTMDBLang()}),signal});
    if(!res.ok) throw new Error(`http_${res.status}`);
    let data; try{data=await res.json();}catch(e){throw new Error("json_parse");}
    if(data.status==="error"){clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();afficherErreurRiche(data);return;}
    if(data.status==="transcription_needed"){
      clearInterval(progInterval);
      const skipWhisper=data.skip_whisper===true;
      const[ocrText,transcript]=await Promise.allSettled([
        data.frames_base64?.length?runLocalOCR(data.frames_base64):Promise.resolve(""),
        (!skipWhisper&&data.audio_base64)?runLocalWhisper(data.audio_base64):Promise.resolve("")
      ]);
      if(skipWhisper) console.log("⏭️ Whisper.js skippé");
      const continueRes=await fetch("/analyser_continue",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:data.session_id,ocr_text:ocrText.status==="fulfilled"?ocrText.value:"",transcript:transcript.status==="fulfilled"?transcript.value:""}),signal});
      let finalData; try{finalData=await continueRes.json();}catch(e){throw new Error("json_parse");} _afficherResultatFinal(finalData); return;
    }
    if(data.status==="processing"&&data.session_id){clearInterval(progInterval);const sessionId=data.session_id;const finalResult=await pollAnalysisStatus(sessionId,signal);_afficherResultatFinal(finalResult);return;}
    clearInterval(progInterval); _afficherResultatFinal(data);
  } catch(e) {
    clearInterval(progInterval);_adFinished=true;document.getElementById('ad-modal').style.display='none';clearInterval(_adCountdownInterval);overlay.classList.remove("active");stopGame();
    if(e.name==="AbortError") return;
    if(e.message==="json_parse") afficherErreurRiche({code:"unexpected",message:t("err_generic")});
    else if(e.message?.startsWith("http_")){const status=parseInt(e.message.split("_")[1]);afficherErreurRiche({code:status===502||status===503?"server_busy":"unexpected"});}
    else afficherErreurRiche({code:"unexpected",message:t("err_generic")});
  }
}
async function pollAnalysisStatus(sessionId,signal,maxRetries=60){
  const progressBar=document.getElementById("prog-fill"),percentLabel=document.getElementById("prog-percent"); let lastProgress=88;
  for(let i=0;i<maxRetries;i++){
    if(signal.aborted) throw new DOMException("Aborted","AbortError");
    try{
      const res=await fetch(`/analyser_status/${sessionId}`,{signal}); if(!res.ok) throw new Error("Polling failed");
      const data=await res.json();
      let stepProgress=88;
      if(data.step==="downloading") stepProgress=90;
      else if(data.step==="processing") stepProgress=95;
      if(progressBar&&percentLabel){const tp=Math.min(stepProgress,98);if(tp>lastProgress)lastProgress=tp;progressBar.style.width=lastProgress+"%";percentLabel.textContent=Math.round(lastProgress)+"%";}
      if(data.status!=="processing"){if(progressBar)progressBar.style.width="100%";if(percentLabel)percentLabel.textContent="100%";return data;}
      await new Promise(r=>setTimeout(r,2500));
    }catch(e){if(e.name==="AbortError")throw e;console.warn("Polling error",e);await new Promise(r=>setTimeout(r,3000));}
  }
  return{status:"error",code:"timeout",message:tErr("timeout")};
}
async function runLocalOCR(framesBase64){
  try{if(!window.Tesseract)return"";const worker=await Tesseract.createWorker('fra+eng');let fullText="";for(const b64 of framesBase64.slice(0,4)){try{const{data:{text}}=await worker.recognize(`data:image/jpeg;base64,${b64}`);fullText+=text+" ";}catch(e){}}await worker.terminate();return fullText.trim();}catch(e){return"";}
}
async function runLocalWhisper(audioBase64){
  try{if(!audioBase64||!window.getWhisperPipeline)return"";const audioBlob=base64ToBlob(audioBase64,'audio/mp3');const arrayBuffer=await audioBlob.arrayBuffer();const audioCtxLocal=new AudioContext();const audioBuffer=await audioCtxLocal.decodeAudioData(arrayBuffer);const pcm=audioBuffer.getChannelData(0);const pipeline=await window.getWhisperPipeline();const result=await pipeline(pcm,{language:'french'});return result.text||"";}catch(e){return"";}
}
function base64ToBlob(base64,mimeType){
  const byteChars=atob(base64);const byteArrays=[];
  for(let offset=0;offset<byteChars.length;offset+=512){const slice=byteChars.slice(offset,offset+512);const byteNumbers=new Array(slice.length);for(let i=0;i<slice.length;i++)byteNumbers[i]=slice.charCodeAt(i);byteArrays.push(new Uint8Array(byteNumbers));}
  return new Blob(byteArrays,{type:mimeType});
}

// ════ GENRES / TRENDING / SERIES / PLATEFORME ════
async function chargerGenre(genreName,page=1,mediaType="movie"){
  hideHero();cacherErreur();currentGenreName=genreName;currentPage=page;
  const cacheKey=`genre_${genreName}_${page}_${getTMDBLang()}`;const cached=getCached(cacheKey);
  document.querySelectorAll(".btn-genre").forEach(b=>b.classList.remove("active"));
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText=genreName.toUpperCase();
  lastGrid=genreName;navStack=[];
  if(cached){renderCards(cached,genreName,page,10,mediaType);return;}
  document.getElementById("movie-cards").innerHTML=`<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  try{
    const url=`/discover/${encodeURIComponent(genreName)}?lang=${getTMDBLang()}&page=${page}${mediaType==="tv"?"&type=tv":""}`;
    const data=await safeFetch(url);
    if(data.status==="success"){setCache(cacheKey,data.results);renderCards(data.results,genreName,page,data.total_pages,mediaType);}
    else afficherVideGrid(`<i class="fas fa-exclamation-circle"></i> ${data.message||"Genre introuvable."}`);
  }catch(e){afficherVideGrid(`<i class="fas fa-wifi"></i> ${t("err_generic")}`);}
}
async function chargerSeries(page=1){
  hideHero();cacherErreur();currentGenreName="series";currentPage=page;
  document.querySelectorAll(".btn-genre").forEach(b=>b.classList.remove("active"));
  document.querySelector(".btn-genre.series")?.classList.add("active");
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText=tg("series").toUpperCase();
  document.getElementById("movie-cards").innerHTML=`<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid="series";navStack=[];
  try{
    const data=await safeFetch(`/trending?lang=${getTMDBLang()}&type=tv`);
    if(data.status==="success") renderCards(data.results.map(r=>({...r,media_type:"tv"})),"series",1,1,"tv");
    else afficherVideGrid(data.message||"Impossible de charger les séries.");
  }catch(e){afficherVideGrid(t("err_generic"));}
}
async function chargerTrending(){
  hideHero();cacherErreur();currentGenreName="trending";
  const cacheKey=`trending_${getTMDBLang()}`;const cached=getCached(cacheKey);
  document.querySelectorAll(".btn-genre").forEach(b=>b.classList.remove("active"));
  document.querySelector(".btn-genre.trending")?.classList.add("active");
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("platform-nav").classList.remove("visible");
  document.getElementById("genre-title").innerText=tg("trending").toUpperCase();
  if(cached){renderCards(cached,"trending",1,1);return;}
  document.getElementById("movie-cards").innerHTML=`<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  lastGrid="trending";navStack=[];
  try{
    const data=await safeFetch(`/trending?lang=${getTMDBLang()}`);
    if(data.status==="success"){setCache(cacheKey,data.results);renderCards(data.results,"trending",1,1);}
    else afficherVideGrid(data.message||"Impossible de charger les tendances.");
  }catch(e){afficherVideGrid(t("err_generic"));}
}
async function chargerParPlateforme(platformKey){
  hideHero();cacherErreur();
  const nameMap={netflix:"NETFLIX",amazon:"PRIME VIDEO",disney:"DISNEY+",apple:"APPLE TV+",paramount:"PARAMOUNT+",hulu:"HULU"};
  currentGenreName=platformKey;
  document.getElementById("page-film-detail").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("genre-grid").style.display="block";
  document.getElementById("genre-title").innerText="📺 "+(nameMap[platformKey]||platformKey.toUpperCase());
  document.getElementById("movie-cards").innerHTML=`<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)"><i class="fas fa-circle-notch fa-spin" style="font-size:2rem"></i></div>`;
  document.querySelectorAll(".btn-platform").forEach(b=>b.classList.remove("active"));
  event?.currentTarget?.classList.add("active");
  lastGrid=platformKey;navStack=[];
  try{
    const data=await safeFetch(`/trending?lang=${getTMDBLang()}`);
    if(data.status==="success") renderCards(data.results,platformKey,1,1);
    else afficherVideGrid(data.message||"Aucun résultat.");
  }catch(e){afficherVideGrid(t("err_generic"));}
}
function afficherVideGrid(msg){document.getElementById("filtres-bar").style.display="none";document.getElementById("movie-cards").innerHTML=`<p style="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px">${msg}</p>`;}

// ════ RENDER CARDS ════
function renderCards(results,genreName,page,totalPages,mediaType="movie"){
  _allResults=results||[];_currentTotalPages=totalPages||1;
  peuplerFiltreAnnee(_allResults);
  document.getElementById("filtres-bar").style.display=_allResults.length>0?"flex":"none";
  document.getElementById("filtre-count").textContent=_allResults.length+" film"+(_allResults.length>1?"s":"");
  appliquerFiltres();
  if(genreName!=="trending"&&genreName!=="search"){
    setTimeout(()=>{
      const container=document.getElementById("movie-cards"),existing=container.querySelector(".pagination");
      if(existing)existing.remove();
      const pag=document.createElement("div");pag.className="pagination";
      const isSeries=genreName==="series";
      pag.innerHTML=`<button class="btn-page" onclick="${isSeries?`chargerSeries(${page-1})`:`chargerGenre('${genreName}',${page-1})`}" ${page<=1?"disabled":""}><i class="fas fa-chevron-left"></i></button><span class="page-info">${page}${totalPages?" / "+totalPages:""}</span><button class="btn-page" onclick="${isSeries?`chargerSeries(${page+1})`:`chargerGenre('${genreName}',${page+1})`}" ${totalPages&&page>=totalPages?"disabled":""}><i class="fas fa-chevron-right"></i></button>`;
      container.appendChild(pag);
    },0);
  }
  window.scrollTo({top:0,behavior:"smooth"});
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
  if(tri==="note_desc") res.sort((a,b)=>(b.vote_average||0)-(a.vote_average||0));
  else if(tri==="note_asc") res.sort((a,b)=>(a.vote_average||0)-(b.vote_average||0));
  else if(tri==="recent") res.sort((a,b)=>(b.release_date||b.first_air_date||"").localeCompare(a.release_date||a.first_air_date||""));
  else if(tri==="ancien") res.sort((a,b)=>(a.release_date||a.first_air_date||"").localeCompare(b.release_date||b.first_air_date||""));
  document.getElementById("filtre-count").textContent=res.length+" film"+(res.length>1?"s":"");
  renderCardsFiltered(res);
}
function reinitFiltres(){document.getElementById("filtre-annee").value="";document.getElementById("filtre-note").value="";document.getElementById("filtre-tri").value="pop";appliquerFiltres();}
function renderCardsFiltered(results){
  const container=document.getElementById("movie-cards"),oldPag=container.querySelector(".pagination");
  [...container.children].forEach(c=>{if(!c.classList.contains("pagination"))c.remove();});
  if(!results||results.length===0){
    const p=document.createElement("p");p.style.cssText="color:var(--muted);grid-column:1/-1;text-align:center;padding:40px";p.textContent="Aucun résultat avec ces filtres.";
    if(oldPag)container.insertBefore(p,oldPag);else container.appendChild(p);return;
  }
  const fragment=document.createDocumentFragment();
  results.forEach(m=>{
    const year=(m.release_date||m.first_air_date||"N/A").split("-")[0];
    const rating=m.vote_average?m.vote_average.toFixed(1):"0";
    const title=m.title||m.name||"Titre inconnu";
    const isTv=m.media_type==="tv"||!!m.first_air_date;
    const poster=m.poster_path?`https://image.tmdb.org/t/p/w300${m.poster_path}`:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
    const div=document.createElement("div");div.className="movie-card";div.setAttribute("role","button");div.setAttribute("tabindex","0");div.setAttribute("aria-label",title);
    div.onclick=()=>afficherDetails(m.id,isTv?"tv":"movie");div.onkeydown=e=>{if(e.key==="Enter")afficherDetails(m.id,isTv?"tv":"movie");};
    div.innerHTML=`${isTv?`<span class="card-type-badge">TV</span>`:""}<img src="${poster}" alt="${title}" loading="lazy"><div class="card-body"><h4>${title}</h4><div class="card-meta"><span><i class="fas fa-calendar" style="font-size:.65rem;opacity:.5"></i> ${year}</span><span class="rating"><i class="fas fa-star" style="font-size:.65rem"></i> ${rating}</span></div></div>`;
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

// ════════════════════════════════════════════════════════════
// ════ LIEUX DE TOURNAGE — PAGE CATALOGUE COMPLÈTE ══════════
// ════════════════════════════════════════════════════════════

async function chargerLieuxDeTournage(page = 1) {
    hideHero(); cacherErreur();
    currentGenreName = "filming";
    _filmingCurrentPage = page;

    document.getElementById("genre-grid").style.display = "none";
    document.getElementById("page-film-detail").style.display = "none";

    document.querySelectorAll(".btn-genre").forEach(b => b.classList.remove("active"));
    document.getElementById("btn-genre-filming")?.classList.add("active");

    // Créer la page si elle n'existe pas
    let filmingPage = document.getElementById("filming-page");
    if (!filmingPage) {
        filmingPage = document.createElement("div");
        filmingPage.id = "filming-page";
        document.body.insertBefore(filmingPage, document.getElementById("privacy-page"));
    }
    filmingPage.style.display = "block";
    navStack = [];

    // Chargement stats en parallèle
    if (!_filmingStats) {
        try {
            const stats = await safeFetch("/films-tournes/stats");
            _filmingStats = stats;
        } catch(e) {}
    }
    if (!_filmingCountries.length) {
        try {
            const c = await safeFetch("/films-tournes/pays");
            _filmingCountries = c.countries || [];
        } catch(e) {}
    }

    _renderFilmingPage(filmingPage);
    await _loadFilmingCatalogue();
}

function _renderFilmingPage(container) {
    const ld = dict[currentLang] || dict.fr;
    const stats = _filmingStats;
    const statsHtml = stats
        ? `<div class="filming-stats-bar">
            <span><strong>${stats.total_films?.toLocaleString() || "—"}</strong> ${ld.filming_movies_only}</span>
            <span class="filming-stats-sep">·</span>
            <span><strong>${stats.total_locations?.toLocaleString() || "—"}</strong> lieux</span>
            <span class="filming-stats-sep">·</span>
            <span><strong>${stats.total_countries?.toLocaleString() || "—"}</strong> pays</span>
           </div>`
        : "";

    const countriesOptions = _filmingCountries.slice(0, 80).map(c =>
        `<option value="${escapeHtml(c.country)}" ${_filmingCurrentCountry===c.country?"selected":""}>${escapeHtml(c.country)} (${c.count})</option>`
    ).join("");

    container.innerHTML = `
      <div class="filming-header">
        <button class="btn-back" onclick="retourAccueil()">
          <i class="fas fa-arrow-left"></i> <span>${ld.back_home || "Accueil"}</span>
        </button>
        <div class="filming-hero">
          <h1 class="filming-title"><i class="fas fa-map-marked-alt"></i> ${ld.filming_title}</h1>
          <p class="filming-subtitle">${ld.filming_subtitle}</p>
          ${statsHtml}
        </div>
      </div>

      <!-- ══ CARTE LEAFLET PRO ══ -->
      <div class="filming-map-wrap" id="filming-map-wrap">
        <div class="filming-map-toolbar">
          <div class="filming-map-toolbar-left">
            <button class="fmap-btn active" id="fmap-layer-film" onclick="toggleFilmingLayer('film')" title="${ld.filming_layer_film}">
              <i class="fas fa-film"></i> <span>${ld.filming_layer_film}</span>
            </button>
            <button class="fmap-btn" id="fmap-layer-hotel" onclick="toggleFilmingLayer('hotel')" title="${ld.filming_layer_hotel}">
              <i class="fas fa-hotel"></i> <span>${ld.filming_layer_hotel}</span>
            </button>
            <button class="fmap-btn" id="fmap-layer-tourism" onclick="toggleFilmingLayer('tourism')" title="${ld.filming_layer_tourism}">
              <i class="fas fa-info-circle"></i> <span>${ld.filming_layer_tourism}</span>
            </button>
          </div>
          <div class="filming-map-toolbar-right">
            <button class="fmap-btn" id="fmap-cluster" onclick="toggleFilmingCluster()" title="${ld.filming_cluster_toggle}">
              <i class="fas fa-layer-group"></i>
            </button>
            <button class="fmap-btn" id="fmap-heatmap" onclick="toggleFilmingHeatmap()" title="${ld.filming_heatmap_toggle}">
              <i class="fas fa-fire"></i>
            </button>
            <button class="fmap-btn" id="fmap-near-me" onclick="filmingNearMe()" title="${ld.filming_near_me}">
              <i class="fas fa-crosshairs"></i>
            </button>
            <button class="fmap-btn" id="fmap-fullscreen" onclick="toggleFilmingMapFullscreen()" title="${ld.filming_fullscreen}">
              <i class="fas fa-expand"></i>
            </button>
          </div>
        </div>
        <div id="filming-leaflet-map"></div>
        <div class="filming-map-legend">
          <span class="fmap-legend-item"><span class="fmap-dot fmap-dot-film"></span> ${ld.filming_layer_film}</span>
          <span class="fmap-legend-item"><span class="fmap-dot fmap-dot-hotel"></span> ${ld.filming_layer_hotel}</span>
          <span class="fmap-legend-item"><span class="fmap-dot fmap-dot-tourism"></span> ${ld.filming_layer_tourism}</span>
        </div>
      </div>

      <!-- ══ FILTRES CATALOGUE ══ -->
      <div class="filming-filters-wrap">
        <div class="filming-search-row">
          <div class="filming-search-box">
            <i class="fas fa-search"></i>
            <input type="text" id="filming-search-input" placeholder="${ld.filming_search}"
              value="${escapeHtml(_filmingCurrentQ)}"
              oninput="debounceFilmingSearch(this.value)"
              onkeydown="if(event.key==='Enter')chargerLieuxDeTournage(1)">
          </div>
          <div class="filming-media-toggle">
            <button class="fmedia-btn ${!_filmingCurrentType?"active":""}" onclick="setFilmingType('')">
              ${ld.filming_all_media}
            </button>
            <button class="fmedia-btn ${_filmingCurrentType==="movie"?"active":""}" onclick="setFilmingType('movie')">
              <i class="fas fa-film"></i> ${ld.filming_movies_only}
            </button>
            <button class="fmedia-btn ${_filmingCurrentType==="tv"?"active":""}" onclick="setFilmingType('tv')">
              <i class="fas fa-tv"></i> ${ld.filming_tv_only}
            </button>
          </div>
        </div>

        <div class="filming-filters-row">
          <select id="filming-filter-country" onchange="setFilmingCountry(this.value)">
            <option value="">${ld.filming_filter_country}</option>
            ${countriesOptions}
          </select>
          <select id="filming-filter-sort" onchange="setFilmingSort(this.value)">
            <option value="count_locations" ${_filmingCurrentSort==="count_locations"?"selected":""}>${ld.filming_sort_count}</option>
            <option value="rating" ${_filmingCurrentSort==="rating"?"selected":""}>${ld.filming_sort_rating}</option>
            <option value="year" ${_filmingCurrentSort==="year"?"selected":""}>${ld.filming_sort_year}</option>
            <option value="title" ${_filmingCurrentSort==="title"?"selected":""}>${ld.filming_sort_title}</option>
          </select>
          <button class="fmap-btn filming-reset-btn" onclick="resetFilmingFilters()">
            <i class="fas fa-times"></i> Reset
          </button>
        </div>
      </div>

      <!-- ══ GRILLE DE FILMS ══ -->
      <div class="filming-grid-wrap">
        <div id="filming-result-count" class="filming-result-count"></div>
        <div id="filming-cards" class="filming-cards"></div>
        <div id="filming-pagination" class="filming-pagination"></div>
      </div>
    `;

    // Init Leaflet
    _initFilmingLeafletMap();
}

// ── Debounce recherche ────────────────────────────────────────────────────────
let _filmingSearchTimeout = null;
function debounceFilmingSearch(val) {
    _filmingCurrentQ = val;
    clearTimeout(_filmingSearchTimeout);
    _filmingSearchTimeout = setTimeout(() => chargerLieuxDeTournage(1), 500);
}
function setFilmingType(type) { _filmingCurrentType = type; chargerLieuxDeTournage(1); }
function setFilmingCountry(country) { _filmingCurrentCountry = country; chargerLieuxDeTournage(1); }
function setFilmingSort(sort) { _filmingCurrentSort = sort; chargerLieuxDeTournage(1); }
function resetFilmingFilters() {
    _filmingCurrentCountry = ""; _filmingCurrentCity = ""; _filmingCurrentType = "";
    _filmingCurrentQ = ""; _filmingCurrentSort = "count_locations";
    chargerLieuxDeTournage(1);
}

// ── Chargement catalogue API ──────────────────────────────────────────────────
async function _loadFilmingCatalogue() {
    const cardsEl = document.getElementById("filming-cards");
    const countEl = document.getElementById("filming-result-count");
    if (!cardsEl) return;

    cardsEl.innerHTML = `<div class="filming-loading"><i class="fas fa-circle-notch fa-spin"></i> ${t("filming_loading")}</div>`;

    const params = new URLSearchParams({
        page: _filmingCurrentPage,
        per_page: 24,
        sort: _filmingCurrentSort,
    });
    if (_filmingCurrentCountry) params.set("country", _filmingCurrentCountry);
    if (_filmingCurrentCity)    params.set("city",    _filmingCurrentCity);
    if (_filmingCurrentType)    params.set("media_type", _filmingCurrentType);
    if (_filmingCurrentQ)       params.set("q", _filmingCurrentQ);

    try {
        const data = await safeFetch(`/films-tournes?${params}`);
        if (data.status !== "success") {
            cardsEl.innerHTML = `<p style="color:var(--muted);text-align:center;padding:40px">${t("err_generic")}</p>`;
            return;
        }

        if (countEl) countEl.textContent = `${data.total.toLocaleString()} films`;

        _renderFilmingCards(cardsEl, data.results);
        _renderFilmingPagination(data.page, data.total_pages);

        // Mettre à jour la carte avec les marqueurs de cette page
        _updateFilmingMapMarkers(data.results);

    } catch(e) {
        if (cardsEl) cardsEl.innerHTML = `<p style="color:var(--muted);text-align:center;padding:40px">${t("err_generic")}</p>`;
    }
}

function _renderFilmingCards(container, results) {
    if (!results || results.length === 0) {
        container.innerHTML = `<p style="color:var(--muted);text-align:center;padding:60px;grid-column:1/-1">Aucun film trouvé avec ces filtres.</p>`;
        return;
    }
    const ld = dict[currentLang] || dict.fr;
    container.innerHTML = results.map(f => {
        const poster = f.poster_path
            ? `https://image.tmdb.org/t/p/w300${f.poster_path}`
            : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
        const rating = f.vote_average ? f.vote_average.toFixed(1) : "—";
        const year = f.year || "—";
        const isTv = f.media_type === "tv";
        const locCount = f.location_count || 0;
        const countries = (f.countries || []).slice(0, 3).join(", ");
        const primaryLoc = f.primary_location;

        const bookingUrl = primaryLoc
            ? `https://www.booking.com/searchresults.html?ss=${encodeURIComponent(primaryLoc.name)}&aid=SHADOWFRAME`
            : null;
        const tripadUrl = primaryLoc
            ? `https://www.tripadvisor.com/Search?q=${encodeURIComponent(primaryLoc.name)}`
            : null;

        return `
          <div class="filming-card" onclick="afficherDetails(${f.tmdb_id},'${isTv?"tv":"movie"}')" role="button" tabindex="0">
            <div class="filming-card-img-wrap">
              ${isTv ? `<span class="card-type-badge">TV</span>` : ""}
              <img src="${poster}" alt="${escapeHtml(f.title)}" loading="lazy">
              <div class="filming-card-loc-badge">
                <i class="fas fa-map-marker-alt"></i> ${locCount}
              </div>
            </div>
            <div class="filming-card-body">
              <h4>${escapeHtml(f.title)}</h4>
              <div class="filming-card-meta">
                <span class="filming-card-year">${year}</span>
                <span class="filming-card-rating"><i class="fas fa-star"></i> ${rating}</span>
              </div>
              ${countries ? `<div class="filming-card-countries"><i class="fas fa-globe-europe"></i> ${escapeHtml(countries)}</div>` : ""}
              ${primaryLoc ? `<div class="filming-card-primary-loc"><i class="fas fa-map-pin"></i> ${escapeHtml(primaryLoc.name)}</div>` : ""}
              <div class="filming-card-actions">
                ${primaryLoc ? `
                  <a href="https://www.google.com/maps?q=${primaryLoc.lat},${primaryLoc.lng}"
                     target="_blank" rel="noopener" class="filming-action-btn filming-maps-btn"
                     onclick="event.stopPropagation()" title="Google Maps">
                    <i class="fas fa-map"></i>
                  </a>` : ""}
                ${bookingUrl ? `
                  <a href="${bookingUrl}" target="_blank" rel="sponsored noopener"
                     class="filming-action-btn filming-booking-btn"
                     onclick="event.stopPropagation()" title="${ld.filming_hotel_near}">
                    <i class="fas fa-bed"></i>
                  </a>` : ""}
                ${tripadUrl ? `
                  <a href="${tripadUrl}" target="_blank" rel="noopener"
                     class="filming-action-btn filming-tripadvisor-btn"
                     onclick="event.stopPropagation()" title="TripAdvisor">
                    <i class="fas fa-star"></i>
                  </a>` : ""}
              </div>
            </div>
          </div>`;
    }).join("");
}

function _renderFilmingPagination(page, totalPages) {
    const pag = document.getElementById("filming-pagination");
    if (!pag) return;
    if (totalPages <= 1) { pag.innerHTML = ""; return; }

    const maxBtns = 5;
    const start = Math.max(1, page - Math.floor(maxBtns / 2));
    const end   = Math.min(totalPages, start + maxBtns - 1);

    let html = `<button class="btn-page" onclick="chargerLieuxDeTournage(${page-1})" ${page<=1?"disabled":""}><i class="fas fa-chevron-left"></i></button>`;
    for (let i = start; i <= end; i++) {
        html += `<button class="btn-page ${i===page?"active":""}" onclick="chargerLieuxDeTournage(${i})">${i}</button>`;
    }
    html += `<button class="btn-page" onclick="chargerLieuxDeTournage(${page+1})" ${page>=totalPages?"disabled":""}><i class="fas fa-chevron-right"></i></button>`;
    html += `<span class="page-info">${page} / ${totalPages}</span>`;
    pag.innerHTML = html;
}

// ════════════════════════════════════════════════════════════
// ════ CARTE LEAFLET PROFESSIONNELLE ════════════════════════
// ════════════════════════════════════════════════════════════

function _initFilmingLeafletMap() {
    _ensureLeafletFull(() => {
        const mapEl = document.getElementById("filming-leaflet-map");
        if (!mapEl || !window.L) return;

        // Détruire carte précédente
        if (_filmingMap) { _filmingMap.remove(); _filmingMap = null; }
        _filmingAllMarkers = [];
        _filmingFilmLayer = null;
        _filmingHotelLayer = null;
        _filmingTourismLayer = null;
        _filmingHeatmapLayer = null;
        _filmingMarkerClusterGroup = null;

        // Fond de carte : plusieurs tuiles disponibles
        const tileLayers = {
            "🌍 OpenStreetMap": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                maxZoom: 19,
            }),
            "🗺️ CartoDB Dark": L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/">CARTO</a>',
                subdomains: 'abcd', maxZoom: 19,
            }),
            "🛰️ CartoDB Voyager": L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
                attribution: '© OpenStreetMap © CARTO',
                subdomains: 'abcd', maxZoom: 19,
            }),
            "🏔️ Stadia Outdoors": L.tileLayer("https://tiles.stadiamaps.com/tiles/outdoors/{z}/{x}/{y}{r}.png", {
                attribution: '© <a href="https://stadiamaps.com/">Stadia Maps</a> © OpenStreetMap',
                maxZoom: 20,
            }),
        };

        // Créer la carte avec fond sombre par défaut
        _filmingMap = L.map(mapEl, {
            center: [20, 0],
            zoom: 2,
            zoomControl: false,
            layers: [tileLayers["🗺️ CartoDB Dark"]],
        });

        // Contrôles positionnés
        L.control.zoom({ position: "topright" }).addTo(_filmingMap);

        // Contrôle de fond de carte
        L.control.layers(tileLayers, {}, { position: "topright", collapsed: true }).addTo(_filmingMap);

        // Contrôle d'échelle
        L.control.scale({ position: "bottomright", imperial: false }).addTo(_filmingMap);

        // Layer clusters pour films
        if (window.L.markerClusterGroup) {
            _filmingMarkerClusterGroup = L.markerClusterGroup({
                maxClusterRadius: 60,
                showCoverageOnHover: false,
                iconCreateFunction: (cluster) => {
                    const count = cluster.getChildCount();
                    const size = count > 100 ? 50 : count > 30 ? 40 : 32;
                    return L.divIcon({
                        html: `<div class="fmap-cluster" style="width:${size}px;height:${size}px;font-size:${count>99?"10px":"12px"}">${count > 999 ? "999+" : count}</div>`,
                        className: "",
                        iconSize: [size, size],
                        iconAnchor: [size/2, size/2],
                    });
                },
            });
            _filmingMap.addLayer(_filmingMarkerClusterGroup);
        }

        // Layers overlay
        _filmingFilmLayer    = L.layerGroup().addTo(_filmingMap);
        _filmingHotelLayer   = L.layerGroup(); // pas ajouté par défaut
        _filmingTourismLayer = L.layerGroup(); // pas ajouté par défaut

        // Minimap (si disponible)
        if (window.L.Control && window.L.Control.MiniMap) {
            const miniLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", { subdomains: "abcd" });
            new L.Control.MiniMap(miniLayer, { position: "bottomleft", toggleDisplay: true, minimized: true }).addTo(_filmingMap);
        }

        // Easy print si disponible
        if (window.L.easyPrint) {
            L.easyPrint({ position: "topright", filename: "shadowframe-filming-map", exportOnly: true }).addTo(_filmingMap);
        }

        _filmingLeafletReady = true;

        // Géolocalisation douce au démarrage
        if (navigator.geolocation && !_filmingCurrentCountry) {
            navigator.geolocation.getCurrentPosition(pos => {
                _filmingMap.flyTo([pos.coords.latitude, pos.coords.longitude], 5, { duration: 1.5 });
            }, () => {}, { timeout: 3000 });
        }
    });
}

function _ensureLeafletFull(callback) {
    if (window.L && window.L.markerClusterGroup) { callback(); return; }

    const loaded = [];

    // CSS Leaflet
    if (!document.querySelector('link[href*="leaflet"]')) {
        const lk = document.createElement("link");
        lk.rel = "stylesheet";
        lk.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(lk);
    }
    // CSS MarkerCluster
    if (!document.querySelector('link[href*="MarkerCluster"]')) {
        const lk2 = document.createElement("link");
        lk2.rel = "stylesheet";
        lk2.href = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css";
        document.head.appendChild(lk2);
        const lk3 = document.createElement("link");
        lk3.rel = "stylesheet";
        lk3.href = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css";
        document.head.appendChild(lk3);
    }

    const scripts = [
        { src: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",                      check: () => !!window.L },
        { src: "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js", check: () => !!window.L?.markerClusterGroup },
        { src: "https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js",             check: () => !!window.L?.heatLayer },
        { src: "https://unpkg.com/leaflet-minimap@3.6.1/dist/Control.MiniMap.min.js",   check: () => !!window.L?.Control?.MiniMap },
        { src: "https://unpkg.com/leaflet.fullscreen@1.6.0/Control.FullScreen.js",      check: () => !!window.L?.control?.fullscreen },
    ];

    function loadNext(idx) {
        if (idx >= scripts.length) { callback(); return; }
        const { src, check } = scripts[idx];
        if (check()) { loadNext(idx + 1); return; }
        const s = document.createElement("script");
        s.src = src;
        s.onload = () => loadNext(idx + 1);
        s.onerror = () => loadNext(idx + 1); // on continue même si un script échoue
        document.head.appendChild(s);
    }
    loadNext(0);
}

// ── Mise à jour des marqueurs films ──────────────────────────────────────────
function _updateFilmingMapMarkers(films) {
    if (!_filmingLeafletReady || !_filmingMap) return;

    // Vider les couches
    if (_filmingMarkerClusterGroup) _filmingMarkerClusterGroup.clearLayers();
    if (_filmingFilmLayer) _filmingFilmLayer.clearLayers();

    const ld = dict[currentLang] || dict.fr;
    const bounds = [];

    films.forEach(f => {
        const loc = f.primary_location;
        if (!loc || loc.lat === null || loc.lat === undefined) return;

        const posterUrl = f.poster_path
            ? `https://image.tmdb.org/t/p/w92${f.poster_path}`
            : null;

        // Icône custom cinéma
        const iconHtml = posterUrl
            ? `<div class="fmap-marker-film" style="background-image:url('${posterUrl}')"></div>`
            : `<div class="fmap-marker-film fmap-marker-no-poster"><i class="fas fa-film"></i></div>`;

        const icon = L.divIcon({
            html: iconHtml,
            className: "",
            iconSize: [36, 36],
            iconAnchor: [18, 36],
            popupAnchor: [0, -38],
        });

        const marker = L.marker([loc.lat, loc.lng], { icon });

        // Popup riche
        const bookingUrl = `https://www.booking.com/searchresults.html?ss=${encodeURIComponent(loc.name)}&aid=SHADOWFRAME`;
        const tripadUrl  = `https://www.tripadvisor.com/Search?q=${encodeURIComponent(loc.name)}`;
        const mapsUrl    = `https://www.google.com/maps?q=${loc.lat},${loc.lng}`;

        marker.bindPopup(`
          <div class="fmap-popup">
            ${posterUrl ? `<img src="${posterUrl}" class="fmap-popup-poster" alt="">` : ""}
            <div class="fmap-popup-body">
              <div class="fmap-popup-title">${escapeHtml(f.title)}</div>
              <div class="fmap-popup-meta">${f.year||""}${f.vote_average?` · ⭐ ${f.vote_average.toFixed(1)}`:""}</div>
              <div class="fmap-popup-loc"><i class="fas fa-map-pin"></i> ${escapeHtml(loc.name)}</div>
              <div class="fmap-popup-country">${escapeHtml(loc.country||"")}</div>
              <div class="fmap-popup-actions">
                <button class="fmap-popup-btn fmap-popup-detail" onclick="afficherDetails(${f.tmdb_id},'${f.media_type||"movie"}')">
                  <i class="fas fa-info-circle"></i> Détails
                </button>
                <a href="${mapsUrl}" target="_blank" rel="noopener" class="fmap-popup-btn fmap-popup-maps">
                  <i class="fas fa-map"></i> Maps
                </a>
                <a href="${bookingUrl}" target="_blank" rel="sponsored noopener" class="fmap-popup-btn fmap-popup-booking">
                  <i class="fas fa-bed"></i> Hôtel
                </a>
                <a href="${tripadUrl}" target="_blank" rel="noopener" class="fmap-popup-btn fmap-popup-trip">
                  <i class="fas fa-star"></i> Trip
                </a>
              </div>
            </div>
          </div>
        `, { maxWidth: 280 });

        if (_filmingMarkerClusterGroup) {
            _filmingMarkerClusterGroup.addLayer(marker);
        } else {
            marker.addTo(_filmingFilmLayer);
        }

        bounds.push([loc.lat, loc.lng]);
        _filmingAllMarkers.push({ lat: loc.lat, lng: loc.lng, marker, film: f });
    });

    // Heatmap si activée
    _refreshHeatmap();
}

// ── Hôtels via Overpass API (OpenStreetMap) ───────────────────────────────────
async function _loadHotelsInView() {
    if (!_filmingMap || !_filmingHotelLayer) return;
    const bounds = _filmingMap.getBounds();
    const bbox = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;

    // Limiter aux zooms élevés pour éviter trop de requêtes
    if (_filmingMap.getZoom() < 8) return;

    const overpassUrl = `https://overpass-api.de/api/interpreter?data=[out:json][timeout:10];(node["tourism"="hotel"](${bbox});node["tourism"="hostel"](${bbox});node["tourism"="guest_house"](${bbox}););out body;`;

    try {
        const res = await fetch(overpassUrl);
        const data = await res.json();
        _filmingHotelLayer.clearLayers();

        const hotelIcon = L.divIcon({
            html: `<div class="fmap-marker-hotel"><i class="fas fa-bed"></i></div>`,
            className: "", iconSize: [28, 28], iconAnchor: [14, 28],
        });

        (data.elements || []).slice(0, 100).forEach(el => {
            if (!el.lat || !el.lon) return;
            const name = el.tags?.name || "Hôtel";
            const stars = el.tags?.stars ? "★".repeat(parseInt(el.tags.stars)) : "";
            const bookUrl = `https://www.booking.com/searchresults.html?ss=${encodeURIComponent(name)}&aid=SHADOWFRAME`;
            const marker = L.marker([el.lat, el.lon], { icon: hotelIcon });
            marker.bindPopup(`
              <div class="fmap-popup-small">
                <strong>${escapeHtml(name)}</strong>
                ${stars ? `<div style="color:#ffd700;font-size:.8rem">${stars}</div>` : ""}
                <a href="${bookUrl}" target="_blank" rel="sponsored noopener" class="fmap-popup-btn fmap-popup-booking" style="margin-top:8px;display:inline-block">
                  <i class="fas fa-bed"></i> Réserver
                </a>
              </div>
            `);
            _filmingHotelLayer.addLayer(marker);
        });
    } catch(e) {}
}

// ── Offices de tourisme via Overpass ─────────────────────────────────────────
async function _loadTourismOfficesInView() {
    if (!_filmingMap || !_filmingTourismLayer) return;
    const bounds = _filmingMap.getBounds();
    const bbox = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;
    if (_filmingMap.getZoom() < 8) return;

    const overpassUrl = `https://overpass-api.de/api/interpreter?data=[out:json][timeout:10];(node["tourism"="information"]["information"="office"](${bbox}););out body;`;

    try {
        const res = await fetch(overpassUrl);
        const data = await res.json();
        _filmingTourismLayer.clearLayers();

        const tourIcon = L.divIcon({
            html: `<div class="fmap-marker-tourism"><i class="fas fa-info"></i></div>`,
            className: "", iconSize: [24, 24], iconAnchor: [12, 24],
        });

        (data.elements || []).slice(0, 50).forEach(el => {
            if (!el.lat || !el.lon) return;
            const name = el.tags?.name || "Office de tourisme";
            const marker = L.marker([el.lat, el.lon], { icon: tourIcon });
            marker.bindPopup(`
              <div class="fmap-popup-small">
                <strong>${escapeHtml(name)}</strong>
                <p style="color:var(--muted);font-size:.75rem;margin:4px 0">${el.tags?.["addr:city"] || ""}</p>
              </div>
            `);
            _filmingTourismLayer.addLayer(marker);
        });
    } catch(e) {}
}

// ── Contrôles des layers ──────────────────────────────────────────────────────
function toggleFilmingLayer(layer) {
    if (!_filmingMap) return;
    const btn = document.getElementById(`fmap-layer-${layer}`);

    if (layer === "film") {
        const target = _filmingMarkerClusterGroup || _filmingFilmLayer;
        if (_filmingMap.hasLayer(target)) { _filmingMap.removeLayer(target); btn?.classList.remove("active"); }
        else { _filmingMap.addLayer(target); btn?.classList.add("active"); }
    }
    if (layer === "hotel") {
        if (_filmingMap.hasLayer(_filmingHotelLayer)) {
            _filmingMap.removeLayer(_filmingHotelLayer); btn?.classList.remove("active");
        } else {
            _filmingMap.addLayer(_filmingHotelLayer); btn?.classList.add("active");
            _loadHotelsInView();
            _filmingMap.on("moveend", _loadHotelsInView);
        }
    }
    if (layer === "tourism") {
        if (_filmingMap.hasLayer(_filmingTourismLayer)) {
            _filmingMap.removeLayer(_filmingTourismLayer); btn?.classList.remove("active");
        } else {
            _filmingMap.addLayer(_filmingTourismLayer); btn?.classList.add("active");
            _loadTourismOfficesInView();
            _filmingMap.on("moveend", _loadTourismOfficesInView);
        }
    }
}

function toggleFilmingCluster() {
    if (!_filmingMap || !_filmingMarkerClusterGroup) return;
    const btn = document.getElementById("fmap-cluster");
    if (_filmingMap.hasLayer(_filmingMarkerClusterGroup)) {
        _filmingMap.removeLayer(_filmingMarkerClusterGroup);
        // Déplacer les marqueurs sur le layer non-clusterisé
        _filmingAllMarkers.forEach(({ lat, lng, marker }) => {
            _filmingFilmLayer.addLayer(marker);
        });
        btn?.classList.remove("active");
    } else {
        _filmingFilmLayer.clearLayers();
        _filmingMap.addLayer(_filmingMarkerClusterGroup);
        btn?.classList.add("active");
    }
}

function toggleFilmingHeatmap() {
    if (!_filmingMap) return;
    const btn = document.getElementById("fmap-heatmap");
    if (_filmingHeatmapLayer && _filmingMap.hasLayer(_filmingHeatmapLayer)) {
        _filmingMap.removeLayer(_filmingHeatmapLayer);
        btn?.classList.remove("active");
    } else {
        _refreshHeatmap(true);
        btn?.classList.add("active");
    }
}

function _refreshHeatmap(forceAdd = false) {
    if (!_filmingMap || !window.L?.heatLayer) return;
    const btn = document.getElementById("fmap-heatmap");
    const isActive = btn?.classList.contains("active") || forceAdd;
    if (!isActive) return;

    if (_filmingHeatmapLayer) _filmingMap.removeLayer(_filmingHeatmapLayer);
    const points = _filmingAllMarkers.map(m => [m.lat, m.lng, 0.5]);
    _filmingHeatmapLayer = L.heatLayer(points, {
        radius: 35, blur: 25, maxZoom: 10,
        gradient: { 0.2: "#00ffcc33", 0.5: "#00ffcc88", 0.8: "#00ffcccc", 1.0: "#00ffcc" },
    }).addTo(_filmingMap);
}

function filmingNearMe() {
    if (!_filmingMap || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(pos => {
        _filmingMap.flyTo([pos.coords.latitude, pos.coords.longitude], 9, { duration: 2 });
        // Pulse marker
        const pulseIcon = L.divIcon({ html: `<div class="fmap-near-me-pulse"></div>`, className: "", iconSize: [24,24], iconAnchor: [12,12] });
        L.marker([pos.coords.latitude, pos.coords.longitude], { icon: pulseIcon }).addTo(_filmingMap)
         .bindPopup("📍 Vous êtes ici").openPopup();
    }, () => toast("Géolocalisation refusée"));
}

function toggleFilmingMapFullscreen() {
    const wrap = document.getElementById("filming-map-wrap");
    if (!wrap) return;
    const btn = document.getElementById("fmap-fullscreen");
    if (wrap.classList.contains("fmap-fullscreen-mode")) {
        wrap.classList.remove("fmap-fullscreen-mode");
        btn?.querySelector("i")?.setAttribute("class", "fas fa-expand");
    } else {
        wrap.classList.add("fmap-fullscreen-mode");
        btn?.querySelector("i")?.setAttribute("class", "fas fa-compress");
    }
    setTimeout(() => _filmingMap?.invalidateSize(), 300);
}

// ════ NOT FOUND ════
function afficherNotFound(data) {
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
  document.getElementById("streaming_section").innerHTML=`${titreHtml}<h3 style="margin-bottom:12px"><i class="fas fa-search"></i> ${t("searching")}</h3><div class="streaming-buttons" style="margin-top:10px;">${data.search_youtube?`<a href="${data.search_youtube}" target="_blank" rel="noopener" class="btn-stream"><i class="fab fa-youtube"></i> YouTube</a>`:""}${data.search_google?`<a href="${data.search_google}" target="_blank" rel="noopener" class="btn-stream"><i class="fab fa-google"></i> Google</a>`:""}${data.search_tmdb?`<a href="${data.search_tmdb}" target="_blank" rel="noopener" class="btn-stream"><i class="fas fa-film"></i> TMDB</a>`:""}</div>`;
  window.scrollTo({top:0,behavior:"smooth"});
}

// ════ DÉTAILS DU FILM ════
async function afficherDetails(movieId, mediaType="movie") {
  if(currentMovieId&&currentMovieId!==movieId) navStack.push({id:currentMovieId,type:currentMediaType});
  currentMovieId=movieId; currentMediaType=mediaType; cacherErreur();
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("filming-page").style.display="none";
  showDetailLoading();
  try {
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
    afficherDetailFilm({
      status:"success",title:data.title||data.name||"Inconnu",synopsis:data.overview||"",
      image:data.poster_path?`https://image.tmdb.org/t/p/w500${data.poster_path}`:"",
      streaming:providers.map(p=>p.provider_name),streaming_logos:providers.map(p=>({name:p.provider_name,logo_path:p.logo_path})),
      similar,cast,trailer:trailerUrl,confidence:null,is_fake:false,vote_average:data.vote_average,vote_count:data.vote_count,
      runtime:data.runtime||data.episode_run_time?.[0],genres,year,tmdb_id:movieId,is_series:isTv,seasons:isTv?(data.seasons||[]):null
    });
  } catch(e) {
    afficherErreur(t("err_generic")); document.getElementById("page-film-detail").style.display="none";
    if(lastGrid) document.getElementById("genre-grid").style.display="block";
  }
}

function showDetailLoading() {
  document.getElementById("page-film-detail").style.display="block";
  document.getElementById("titre_film").innerText="…";
  document.getElementById("affiche_film").src="";
  ["synopsis_film","detail_tags","detail_rating","streaming_section","cast_section","trailer_section","similar_section","seasons_section","fake_alert"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";});
  ["crew_section","locations_section","finance_section","eidr_badge"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML="";})
  document.getElementById("confidence_wrap").style.display="none";
  document.getElementById("food-partner").classList.remove("visible");
}

function afficherDetailFilm(data) {
  document.getElementById("page-film-detail").style.display="block";
  document.getElementById("genre-grid").style.display="none";
  document.getElementById("filming-page").style.display="none";
  document.getElementById("hero").style.display="none";
  document.getElementById("back-label").innerText=lastGrid?t("back_list"):t("back_home");
  document.getElementById("fake_alert").innerHTML=data._lowConfWarning?`<div class="fake-alert"><i class="fas fa-exclamation-triangle"></i> Résultat incertain — (${Math.round(data.confidence)}% de confiance). Vérifiez manuellement si besoin.</div>`:data.is_fake?`<div class="fake-alert"><i class="fas fa-exclamation-triangle"></i> Contenu humoristique possible.</div>`:"";
  document.getElementById("titre_film").innerText=data.title||"Inconnu";
  const imgEl=document.getElementById("affiche_film");
  if(data.image){imgEl.src=data.image;imgEl.style.display="block";}else imgEl.style.display="none";
  const tagsEl=document.getElementById("detail_tags");tagsEl.innerHTML="";
  if(data.is_series) tagsEl.innerHTML+=`<span class="tag series"><i class="fas fa-tv"></i> ${t("series_tag")}</span>`;
  if(data.year) tagsEl.innerHTML+=`<span class="tag year"><i class="fas fa-calendar"></i> ${data.year}</span>`;
  if(data.runtime) tagsEl.innerHTML+=`<span class="tag"><i class="fas fa-clock"></i> ${data.runtime} min</span>`;
  (data.genres||[]).forEach(g=>tagsEl.innerHTML+=`<span class="tag genre">${g}</span>`);
  const confWrap=document.getElementById("confidence_wrap");
  if(data.confidence!==null&&data.confidence!==undefined){
    const pct=Math.round(data.confidence);const color=pct>=70?"#00ffcc":pct>=40?"#ffd700":"#ff4444";
    const lbl=pct>=70?(currentLang.startsWith("en")?"High confidence":"Confiance élevée"):pct>=40?(currentLang.startsWith("en")?"Medium confidence":"Confiance moyenne"):(currentLang.startsWith("en")?"Low confidence":"Confiance faible");
    confWrap.style.display="block";document.getElementById("conf-bar-inner").style.width=pct+"%";document.getElementById("conf-bar-inner").style.background=color;document.getElementById("conf-pct-label").textContent=pct+"% — "+lbl;document.getElementById("conf-pct-label").style.color=color;
  }else confWrap.style.display="none";
  const ratingEl=document.getElementById("detail_rating");ratingEl.innerHTML=data.vote_average?`<i class="fas fa-star" style="color:var(--gold)"></i> ${parseFloat(data.vote_average).toFixed(1)}<small> / 10 · ${data.vote_count?data.vote_count.toLocaleString()+" votes":""}</small>`:"";
  const synEl=document.getElementById("synopsis_film");
  if(data.scene_description){synEl.innerHTML=`<div style="background:rgba(0,255,204,.06);border-left:3px solid var(--primary);padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:14px;font-size:.82rem;color:var(--muted)"><span style="color:var(--primary);font-weight:600;font-size:.73rem;text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:6px"><i class="fas fa-film"></i> ${t("scene_identified")}</span>${data.scene_description}</div><span style="font-size:.73rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:8px">Synopsis</span>${data.synopsis||t("no_synopsis")}`;}
  else synEl.textContent=data.synopsis||t("no_synopsis");
  setTimeout(()=>document.getElementById("food-partner").classList.add("visible"),400);
  const streamEl=document.getElementById("streaming_section");
  const streamList=data.streaming||[],streamLogos=data.streaming_logos||[];
  if(streamList.length>0){
    const btns=streamList.map((name,i)=>{
      const base=STREAMING_LINKS[name]||"https://www.google.com/search?q=";const url=base+encodeURIComponent(data.title||"");
      const meta=STREAMING_META[name]||{color:"#fff",logo:""};const logoPath=streamLogos[i]?.logo_path;
      const logoSrc=logoPath?`https://image.tmdb.org/t/p/w45${logoPath}`:meta.logo||"";
      const aff=name.includes("Amazon")||name.includes("Apple");
      const logoHtml=logoSrc?`<img src="${logoSrc}" class="plat-logo" alt="${name}" onerror="this.style.display='none'">`:` <i class="fas fa-play-circle" style="color:${meta.color}"></i>`;
      return `<a href="${url}" target="_blank" rel="noopener" class="btn-stream ${aff?"affiliate":""}" style="border-color:${meta.color}40">${logoHtml} ${name}</a>`;
    }).join("");
    streamEl.innerHTML=`<h3><i class="fas fa-satellite-dish"></i> ${t("streaming_title")}</h3><div class="streaming-buttons">${btns}</div>`;
  }else{
    streamEl.innerHTML=`<h3><i class="fas fa-satellite-dish"></i> Streaming</h3><p style="color:var(--muted);font-size:.85rem">${t("no_streaming_country")}</p><div class="streaming-buttons" style="margin-top:8px"><a href="https://www.amazon.fr/gp/video/search?phrase=${encodeURIComponent(data.title||"")}" target="_blank" class="btn-stream affiliate" style="border-color:#00a8e040"><i class="fas fa-search" style="color:#00a8e0"></i> Amazon Prime</a><a href="https://www.google.com/search?q=${encodeURIComponent((data.title||"")+" streaming")}" target="_blank" class="btn-stream"><i class="fab fa-google"></i> Google</a></div>`;
  }
  const seasonsEl=document.getElementById("seasons_section");
  if(data.is_series&&data.seasons&&data.seasons.length>0){
    const seasons=data.seasons.filter(s=>s.season_number>0||s.episode_count>0);
    const seasonCards=seasons.map(s=>{
      const poster=s.poster_path?`https://image.tmdb.org/t/p/w154${s.poster_path}`:"";const airYear=s.air_date?s.air_date.split("-")[0]:"";
      const posterHtml=poster?`<img class="season-poster" src="${poster}" alt="${s.name||""}" loading="lazy">`:`<div style="width:48px;height:72px;background:var(--card2);border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:1.2rem">🎬</div>`;
      return `<div class="season-card" id="season-${s.season_number}"><div class="season-header" onclick="toggleSaison(${data.tmdb_id},${s.season_number})">${posterHtml}<div class="season-info"><div class="season-name">${s.name||t("seasons_title")+" "+s.season_number}</div><div class="season-meta">${s.episode_count||0} ${t("episodes_title")}${airYear?" · "+airYear:""}</div></div><i class="fas fa-chevron-down season-chevron"></i></div><div class="episodes-list" id="episodes-${s.season_number}"><div class="episodes-loading"><i class="fas fa-circle-notch fa-spin"></i> ${t("loading_episodes")}</div></div></div>`;
    }).join("");
    seasonsEl.innerHTML=`<h3><i class="fas fa-layer-group"></i> ${t("seasons_title")}</h3>${seasonCards}`;
  }else seasonsEl.innerHTML="";
  const castEl=document.getElementById("cast_section");
  if((data.cast||[]).length>0){
    const items=data.cast.map(c=>{
      const photo=c.profile_path?`https://image.tmdb.org/t/p/w185${c.profile_path}`:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Crect width='60' height='60' fill='%231a1a24' rx='30'/%3E%3Ctext x='50%25' y='50%25' fill='%23555' font-size='24' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%91%A4%3C/text%3E%3C/svg%3E";
      return `<div class="cast-card"><img src="${photo}" alt="${c.name}" loading="lazy"><p>${c.name}${c.character?`<br><span style="color:var(--primary);font-size:.58rem">${c.character}</span>`:""}</p></div>`;
    }).join("");
    castEl.innerHTML=`<h3><i class="fas fa-users"></i> ${t("cast_title")}</h3><div class="cast-list">${items}</div>`;
  }else castEl.innerHTML="";
  const trailerEl=document.getElementById("trailer_section");
  if(data.trailer){
    const embedUrl=data.trailer.replace("watch?v=","embed/").replace("youtu.be/","www.youtube.com/embed/");
    trailerEl.innerHTML=`<h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3><button class="btn-trailer" onclick="afficherTrailer(this,'${embedUrl}')"><i class="fas fa-play"></i> ${t("see_trailer")}</button><iframe id="trailer_iframe" allowfullscreen style="display:none;width:100%;aspect-ratio:16/9;border-radius:12px;border:none;margin-top:10px;"></iframe>`;
  }else{
    const q=encodeURIComponent((data.title||"")+" trailer");
    trailerEl.innerHTML=`<h3><i class="fab fa-youtube"></i> ${t("trailer_title")}</h3><a href="https://www.youtube.com/results?search_query=${q}" target="_blank" rel="noopener" class="btn-trailer"><i class="fas fa-search"></i> ${t("search_trailer")}</a>`;
  }
  const similarEl=document.getElementById("similar_section");
  const similarList=data.similar||[];
  if(similarList.length>0){
    const cards=similarList.map(s=>{
      const poster=s.poster_path?`https://image.tmdb.org/t/p/w200${s.poster_path}`:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300' fill='%231a1a24'%3E%3Crect width='200' height='300'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='28' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";
      const isTv=s.media_type==="tv"||!!s.first_air_date;
      return `<div class="movie-card" onclick="afficherDetails(${s.id},'${isTv?"tv":"movie"}')" style="cursor:pointer"><img src="${poster}" alt="${s.title||s.name||"?"}" loading="lazy" style="aspect-ratio:2/3;object-fit:cover"><div class="card-body"><h4>${s.title||s.name||"?"}</h4></div></div>`;
    }).join("");
    similarEl.innerHTML=`<h3>${t("similar_title")}</h3><div id="similar_cards">${cards}</div>`;
  }else similarEl.innerHTML="";
  if(data.tmdb_id) chargerEnrichissementWikidata(data.tmdb_id,data.media_type||"movie");
  window.scrollTo({top:0,behavior:"smooth"});
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
    episodesList.innerHTML=episodes.map(ep=>{
      const still=ep.still_path?`https://image.tmdb.org/t/p/w185${ep.still_path}`:"";const airDate=ep.air_date?ep.air_date.split("-").reverse().join("/"):"";
      const stillHtml=still?`<img class="episode-still" src="${still}" alt="" loading="lazy">`:"";
      return `<div class="episode-item"><div class="episode-num">${ep.episode_number}</div>${stillHtml}<div class="episode-body"><div class="episode-title">${ep.name||"Episode "+ep.episode_number}</div>${airDate?`<div class="episode-date">${airDate}</div>`:""  }${ep.overview?`<div class="episode-overview">${ep.overview}</div>`:""}</div></div>`;
    }).join("");
  }catch(e){episodesList.innerHTML=`<p style="padding:16px;color:var(--muted);font-size:.82rem;text-align:center"><i class="fas fa-exclamation-circle"></i> Erreur chargement épisodes</p>`;}
}

// ════ PUBLICITÉ ════
let _adFinished=false,_analysisResult=null,_analysisCallback=null,_adCountdownInterval=null;
function demarrerPub(){
  const modal=document.getElementById('ad-modal'),closeBtn=document.getElementById('ad-close-btn'),countdown=document.getElementById('ad-countdown');
  _adFinished=false;modal.style.display='flex';closeBtn.disabled=true;closeBtn.style.background='rgba(255,255,255,0.1)';closeBtn.style.color='var(--text)';
  let seconds=5;countdown.textContent=seconds;
  _adCountdownInterval=setInterval(()=>{seconds--;countdown.textContent=seconds;if(seconds<=0){clearInterval(_adCountdownInterval);closeBtn.disabled=false;countdown.textContent='✕';closeBtn.style.background='rgba(0,255,204,0.2)';closeBtn.style.color='var(--primary)';_publicitéTerminée();}},1000);
}
function fermerPub(){const closeBtn=document.getElementById('ad-close-btn');if(closeBtn.disabled)return;clearInterval(_adCountdownInterval);_publicitéTerminée();}
function _publicitéTerminée(){_adFinished=true;const modal=document.getElementById('ad-modal');modal.style.display='none';if(_analysisResult!==null){_afficherResultatFinal(_analysisResult);_analysisResult=null;}}
function _afficherResultatFinal(data){
  if(!_adFinished){_analysisResult=data;return;}
  const overlay=document.getElementById("loading-overlay"),progressBar=document.getElementById("prog-fill"),percentLabel=document.getElementById("prog-percent");
  if(progressBar)progressBar.style.width="100%";if(percentLabel)percentLabel.textContent="100%";
  setTimeout(()=>overlay.classList.remove("active"),300);stopGame();
  if(data.status==="success"||data.status==="cached"){navStack=[];lastGrid=null;currentMovieId=data.tmdb_id;currentMediaType=data.media_type||"movie";afficherDetailFilm(data);}
  else if(data.status==="not_found") afficherNotFound(data);
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
    if(sections.eidr&&wd?.eidr_id){sections.eidr.innerHTML=`<span class="eidr-badge" title="Identifiant EIDR standard industrie audiovisuelle"><i class="fas fa-fingerprint"></i>EIDR&nbsp;<code>${wd.eidr_id}</code></span>`;sections.eidr.style.display="flex";}
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
  const locItems=allLocs.map(loc=>{
    const hasCoord=loc.lat!==null&&loc.lat!==undefined;const mapsUrl=hasCoord?`https://www.google.com/maps?q=${loc.lat},${loc.lng}`:`https://www.google.com/maps/search/${encodeURIComponent(loc.name)}`;const wdUrl=loc.wikidata_id?`https://www.wikidata.org/wiki/${loc.wikidata_id}`:null;
    return `<div class="location-chip"><a href="${mapsUrl}" target="_blank" rel="noopener" class="loc-maps-link" title="Voir sur Google Maps"><i class="fas fa-map-marker-alt" style="color:var(--primary)"></i> ${escapeHtml(loc.name)}${hasCoord?'<i class="fas fa-external-link-alt" style="font-size:.6rem;opacity:.5"></i>':""}</a>${wdUrl?`<a href="${wdUrl}" target="_blank" rel="noopener" class="loc-wd-link" title="Wikidata"><i class="fab fa-wikipedia-w"></i></a>`:""}</div>`;
  }).join("");
  let mapHtml="";
  if(withGPS.length>0)mapHtml=`<div id="filming-map" class="filming-map-container" style="height:220px;border-radius:12px;overflow:hidden;margin-bottom:16px;border:1px solid var(--border)"><div id="filming-map-inner" style="width:100%;height:100%"></div></div>`;
  container.innerHTML=`<div class="locations-section-inner"><h3><i class="fas fa-map-marked-alt"></i> ${locLabel("title")} <span class="loc-count">${allLocs.length}</span></h3>${mapHtml}<div class="location-chips">${locItems}</div>${withGPS.length>0?`<p class="loc-affiliate"><i class="fas fa-bed"></i><a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(withGPS[0].name)}&aid=SHADOWFRAME" target="_blank" rel="sponsored noopener" class="loc-booking-link">Trouver un hôtel près du lieu de tournage →</a></p>`:""}<p class="wd-source"><i class="fab fa-wikipedia-w"></i> ${locLabel("source")}</p></div>`;
  if(withGPS.length>0&&typeof L!=="undefined") initFilmingMap(withGPS);
  else if(withGPS.length>0) loadLeaflet(()=>initFilmingMap(withGPS));
}
function initFilmingMap(locations){
  try{
    const mapEl=document.getElementById("filming-map-inner");if(!mapEl||!window.L)return;
    if(window._filmingMapDetail){window._filmingMapDetail.remove();window._filmingMapDetail=null;}
    const center=[locations[0].lat,locations[0].lng];
    const map=L.map(mapEl,{zoomControl:true,scrollWheelZoom:false});window._filmingMapDetail=map;
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(map);
    const icon=L.divIcon({className:"",html:`<div style="background:var(--primary,#00ffcc);width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #000;box-shadow:0 2px 8px rgba(0,255,204,.4)"></div>`,iconSize:[28,28],iconAnchor:[14,28]});
    const bounds=[];
    locations.forEach(loc=>{
      const marker=L.marker([loc.lat,loc.lng],{icon}).addTo(map);
      marker.bindPopup(`<strong>${loc.name}</strong><br><a href="https://www.booking.com/searchresults.html?ss=${encodeURIComponent(loc.name)}&aid=SHADOWFRAME" target="_blank" style="color:#00ffcc;font-size:.8rem">🛏 Hôtels →</a> · <a href="https://www.google.com/maps?q=${loc.lat},${loc.lng}" target="_blank" style="color:#00ffcc;font-size:.8rem">Maps →</a>`);
      bounds.push([loc.lat,loc.lng]);
    });
    if(bounds.length===1)map.setView(center,12);else map.fitBounds(bounds,{padding:[30,30]});
  }catch(e){console.warn("Leaflet map KO:",e);}
}
function loadLeaflet(callback){
  if(window.L){callback();return;}
  const link=document.createElement("link");link.rel="stylesheet";link.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";document.head.appendChild(link);
  const script=document.createElement("script");script.src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";script.onload=callback;document.head.appendChild(script);
}
function afficherFinanceWikidata(container,wd){
  if(!wd||(!wd.budget_usd&&!wd.box_office_usd)){container.innerHTML="";return;}
  const fmt=(n)=>n?"$"+(n>=1e9?(n/1e9).toFixed(2)+" Md":n>=1e6?Math.round(n/1e6)+" M":n.toLocaleString()):null;
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
function escapeHtml(str){if(!str)return"";return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

// ════ INIT ════
window.addEventListener("scroll",()=>{document.getElementById("back-top").classList.toggle("visible",window.scrollY>400);});
window.onload=()=>{
  initLang();
  chargerTrending().then(()=>{document.getElementById("hero").style.display="block";document.getElementById("genre-nav").style.display="flex";});
  document.addEventListener("keydown",e=>{if(e.code==="Space"&&document.getElementById("loading-overlay").classList.contains("active")){e.preventDefault();gameJump();}});
  const gc=document.getElementById("game-canvas");
  if(gc){
    gc.addEventListener("touchstart",e=>{e.preventDefault();gameJump();},{passive:false});
    if(!gc.querySelector(".game-ground")){
      gc.innerHTML=`<div class="game-star" style="top:20px;left:15%"></div><div class="game-star" style="top:40px;left:35%"></div><div class="game-star" style="top:15px;left:55%"></div><div class="game-star" style="top:50px;left:70%"></div><div class="game-star" style="top:28px;left:85%"></div><div class="game-cloud" style="width:60px;height:16px;top:28px;left:120%;animation-duration:9s"></div><div class="game-cloud" style="width:38px;height:12px;top:48px;left:140%;animation-duration:13s;animation-delay:-5s"></div><div class="game-cloud" style="width:80px;height:18px;top:16px;left:160%;animation-duration:11s;animation-delay:-3s"></div><div class="game-ground"></div><div class="game-score-display" id="game-score">0</div><div class="game-lives" id="game-lives">❤️❤️❤️</div><div class="game-level-display" id="game-level">LVL 1</div><div id="game-hero" style="left:60px">🥷</div><div class="game-tap-hint" id="game-hint">${t("game_hint")}</div>`;
    }
  }
  if(!localStorage.getItem("cookies_accepted"))setTimeout(()=>{document.getElementById("cookie-consent").style.display="flex";},2000);
};