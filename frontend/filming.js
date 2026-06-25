// ═════════════════════════════════════════════════════════════
// PELIFY — LIEUX DE TOURNAGE
// Version rapide : catalogue à gauche, détail à droite
// ═════════════════════════════════════════════════════════════

let _filmingCurrentPage = 1;
let _filmingCurrentCountry = "";
let _filmingCurrentYear = "";
let _filmingCurrentType = "";
let _filmingCurrentQ = "";

let _filmingStats = null;
let _filmingAllYears = [];
let _filmingAllCountries = [];

let _filmingSearchTimeout = null;
let _filmingDetailMap = null;
let _filmingDetailMarkers = [];

const _filmingFilmsCache = new Map();
const _filmLocationsCache = new Map();

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
  document.getElementById("platform-nav")?.classList.remove("visible");

  filmingPage.style.display = "block";
  filmingPage.classList.add("filming-split-mode");

  navStack = [];

  _renderFilmingPage(filmingPage);

  // Charge uniquement les cartes au départ
  await _loadFilmingCatalogue();

  // Stats légères seulement, pas le gros fallback tout de suite
  safeFetch("/films-tournes/stats")
    .then(d => {
      _filmingStats = d;
      _updateFilmingStats();
    })
    .catch(() => {});
}

function _renderFilmingPage(container) {
  const ld = dict[currentLang] || dict.fr;

  container.innerHTML = `
    <section class="filming-split-layout">
      <aside class="filming-left-panel">
        <div class="filming-left-head">
          <h1 class="filming-title">
            <i class="fas fa-map-marked-alt"></i>
            ${ld.filming_title || "LIEUX DE TOURNAGE"}
          </h1>

          <p class="filming-subtitle">
            ${ld.filming_subtitle || "Explorez les vrais décors du cinéma mondial"}
          </p>

          <div id="filming-stats-bar" class="filming-stats-bar"></div>
        </div>

        <div class="filming-filters-wrap">
          <div class="filming-search-box">
            <i class="fas fa-search"></i>
            <input
              type="text"
              id="filming-search-input"
              placeholder="${ld.filming_search || "Rechercher un film…"}"
              value="${escapeHtml(_filmingCurrentQ || "")}"
              oninput="debounceFilmingSearch(this.value)"
            >
          </div>

          <div class="filming-filter-row">
            <button class="fmedia-btn ${_filmingCurrentType === "" ? "active" : ""}"
                    onclick="setFilmingType('')">
              ${ld.filming_all_media || "Tout"}
            </button>

            <button class="fmedia-btn ${_filmingCurrentType === "movie" ? "active" : ""}"
                    onclick="setFilmingType('movie')">
              ${ld.filming_movies_only || "Films"}
            </button>

            <select id="filming-filter-country" onchange="setFilmingCountry(this.value)">
              <option value="">Tous les lieux</option>
            </select>

            <select id="filming-filter-year" onchange="setFilmingYear(this.value)">
              <option value="">Toutes les années</option>
            </select>

            <button class="btn-reset filming-reset-btn" onclick="resetFilmingFilters()">
              <i class="fas fa-times"></i> Reset
            </button>
          </div>
        </div>

        <div id="filming-cards" class="filming-cards-grid"></div>
        <div id="filming-pagination" class="filming-pagination"></div>
      </aside>

      <aside id="filming-detail-zone" class="filming-right-panel">
        <div class="filming-detail-placeholder">
          <i class="fas fa-map-location-dot"></i>
          <h2>Sélectionne un film</h2>
          <p>Les lieux de tournage et la carte apparaîtront ici.</p>
        </div>
      </aside>
    </section>
  `;

  _updateFilmingFilters();
}

async function _loadFilmingCatalogue() {
  const cardsEl = document.getElementById("filming-cards");
  if (!cardsEl) return [];

  cardsEl.innerHTML = `
    <div class="filming-loading">
      <i class="fas fa-circle-notch fa-spin"></i> Chargement…
    </div>
  `;

  const params = new URLSearchParams({
    page: _filmingCurrentPage,
    per_page: 24,
    sort: "count_locations"
  });

  if (_filmingCurrentType) params.set("media_type", _filmingCurrentType);
  if (_filmingCurrentQ) params.set("q", _filmingCurrentQ);
  if (_filmingCurrentYear) params.set("year", _filmingCurrentYear);
  if (_filmingCurrentCountry) params.set("city", _filmingCurrentCountry);

  try {
    const data = await safeFetch(`/films-tournes?${params}`);

    if (data.status !== "success") {
      cardsEl.innerHTML = `
        <p class="filming-empty">Aucun résultat.</p>
      `;
      return [];
    }

    const results = data.results || [];

    _renderFilmingCards(cardsEl, results);
    _renderFilmingPagination(data.page, data.total_pages);

    // On remplit les filtres progressivement depuis les résultats déjà chargés
    _extractFilmingMetaFromResults(results);
    _updateFilmingFilters();

    return results;
  } catch (e) {
    cardsEl.innerHTML = `
      <p class="filming-empty">Erreur de chargement.</p>
    `;
    return [];
  }
}

function _renderFilmingCards(container, results) {
  if (!results || results.length === 0) {
    container.innerHTML = `
      <p class="filming-empty">Aucun film trouvé.</p>
    `;
    return;
  }

  container.innerHTML = results.map(f => {
    const tmdbId = Number(f.tmdb_id || f.id);
    const mediaType = f.media_type || f.type || "movie";

    if (!tmdbId) return "";

    const cacheKey = `${tmdbId}_${mediaType}`;
    _filmingFilmsCache.set(cacheKey, f);

    const poster = f.poster_path
      ? `https://image.tmdb.org/t/p/w300${f.poster_path}`
      : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' fill='%231a1a24'%3E%3Crect width='300' height='450'/%3E%3Ctext x='50%25' y='50%25' fill='%23444' font-size='40' text-anchor='middle' dominant-baseline='middle'%3E%F0%9F%8E%AC%3C/text%3E%3C/svg%3E";

    const title = f.title || f.name || "Titre inconnu";
    const rating = f.vote_average ? Number(f.vote_average).toFixed(1) : "—";
    const year = f.year || "—";
    const locCount = f.location_count || (f.locations || []).length || 0;

    const primaryLoc =
      f.primary_location ||
      (Array.isArray(f.locations) && f.locations[0]) ||
      null;

    return `
      <article class="filming-card"
               tabindex="0"
               onclick="ouvrirDetailLieuxTournage(${tmdbId}, '${mediaType}')"
               onkeydown="if(event.key==='Enter') ouvrirDetailLieuxTournage(${tmdbId}, '${mediaType}')">
        <div class="filming-card-img-wrap">
          <img src="${poster}" alt="${escapeHtml(title)}" loading="lazy">
          <div class="filming-card-loc-badge">
            <i class="fas fa-map-marker-alt"></i> ${locCount}
          </div>
        </div>

        <div class="filming-card-body">
          <h4>${escapeHtml(title)}</h4>

          <div class="filming-card-meta">
            <span>${year}</span>
            <span><i class="fas fa-star"></i> ${rating}</span>
          </div>

          ${primaryLoc ? `
            <div class="filming-card-primary-loc">
              <i class="fas fa-map-pin"></i>
              ${escapeHtml(primaryLoc.name || primaryLoc.city || "")}
            </div>
          ` : ""}
        </div>
      </article>
    `;
  }).join("");
}

async function ouvrirDetailLieuxTournage(tmdbId, mediaType = "movie") {
  const detailZone = document.getElementById("filming-detail-zone");
  if (!detailZone) return;

  const filmKey = `${tmdbId}_${mediaType}`;
  const film = _filmingFilmsCache.get(filmKey) || {};

  detailZone.innerHTML = `
    <div class="filming-detail-loading">
      <i class="fas fa-circle-notch fa-spin"></i>
      <span>Chargement des lieux de tournage…</span>
    </div>
  `;

  // Ne plus faire scrollIntoView ici : le détail reste à droite
  const locCacheKey = `${tmdbId}_${mediaType}`;
  let locations = _filmLocationsCache.get(locCacheKey) || [];

  if (!locations.length) {
    locations = await _fetchFilmLocations(tmdbId, mediaType, film);
    if (locations.length) {
      _filmLocationsCache.set(locCacheKey, locations);
    }
  }

  _renderFilmingDetailPanel(tmdbId, mediaType, film, locations);
}

async function _fetchFilmLocations(tmdbId, mediaType, film = {}) {
  const candidates = [];

  // 1. Endpoint détail
  candidates.push(`/movie/${tmdbId}/locations?type=${mediaType}`);

  // 2. Fallback : lieux déjà présents dans la carte catalogue
  if (Array.isArray(film.locations) && film.locations.length) {
    const fromCard = film.locations
      .map(l => _normalizeFilmingLocation(l))
      .filter(l => l && l.lat != null && l.lng != null);

    if (fromCard.length) return fromCard;
  }

  for (const url of candidates) {
    try {
      const data = await safeFetch(url);
      const raw = data.locations || data.results || [];
      const clean = raw
        .map(l => _normalizeFilmingLocation(l))
        .filter(l => l && l.lat != null && l.lng != null);

      if (clean.length) return clean;
    } catch (e) {}
  }

  return [];
}

function _normalizeFilmingLocation(l) {
  if (!l) return null;

  const lat = l.lat ?? l.latitude;
  const lng = l.lng ?? l.lon ?? l.longitude;

  if (lat == null || lng == null) return null;

  return {
    name: l.name || l.label || l.title || "Lieu de tournage",
    city: l.city || "",
    country: l.country && l.country !== "Inconnu" ? l.country : "",
    lat: Number(lat),
    lng: Number(lng),
    address: l.address || "",
    description: l.description || l.scene || ""
  };
}


function _ensureLeafletFull(callback) {
  if (window.L) {
    callback();
    return;
  }

  if (!document.querySelector('link[href*="leaflet.css"]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);
  }

  const script = document.createElement("script");
  script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  script.onload = callback;
  script.onerror = () => {
    console.warn("Leaflet impossible à charger.");
  };

  document.head.appendChild(script);
}

function _renderFilmingDetailPanel(tmdbId, mediaType, film, locations) {
  const detailZone = document.getElementById("filming-detail-zone");
  if (!detailZone) return;

  const title = film.title || film.name || "Film";
  const poster = film.poster_path
    ? `https://image.tmdb.org/t/p/w300${film.poster_path}`
    : "";

  if (!locations.length) {
    detailZone.innerHTML = `
      <div class="filming-detail-panel">
        <div class="filming-detail-header">
          ${poster ? `<img src="${poster}" alt="${escapeHtml(title)}" loading="lazy">` : ""}
          <div>
            <h2>${escapeHtml(title)}</h2>
            <p>Aucun point GPS disponible pour ce film.</p>
            <button class="btn-stream" onclick="afficherDetails(${tmdbId}, '${mediaType}')">
              <i class="fas fa-film"></i> Voir la fiche complète
            </button>
          </div>
        </div>
      </div>
    `;
    return;
  }

  detailZone.innerHTML = `
    <div class="filming-detail-panel">
      <div class="filming-detail-header">
        ${poster ? `<img src="${poster}" alt="${escapeHtml(title)}" loading="lazy">` : ""}

        <div>
          <h2>${escapeHtml(title)}</h2>
          <p>
            <i class="fas fa-map-marker-alt"></i>
            ${locations.length} lieu${locations.length > 1 ? "x" : ""} de tournage
          </p>

          <button class="btn-stream" onclick="afficherDetails(${tmdbId}, '${mediaType}')">
            <i class="fas fa-film"></i> Voir la fiche complète
          </button>
        </div>
      </div>

      <div id="filming-detail-map" class="filming-detail-map"></div>

      <div class="filming-detail-locations">
        ${locations.map((loc, idx) => `
          <button class="filming-location-row"
                  onclick="focusFilmingDetailMarker(${idx})">
            <span class="filming-location-num">${idx + 1}</span>
            <span>
              <strong>${escapeHtml(loc.name)}</strong>
              <small>${escapeHtml([loc.city, loc.country].filter(Boolean).join(", ") || "Lieu non précisé")}</small>
            </span>
          </button>
        `).join("")}
      </div>
    </div>
  `;

  _ensureLeafletFull(() => {
    setTimeout(() => {
      _initFilmingDetailMap(locations);
    }, 100);
  });
}

function _initFilmingDetailMap(locations) {
  const mapEl = document.getElementById("filming-detail-map");
  if (!mapEl || !window.L) return;

  if (_filmingDetailMap) {
    try { _filmingDetailMap.remove(); } catch (e) {}
    _filmingDetailMap = null;
  }

  _filmingDetailMarkers = [];

  _filmingDetailMap = L.map(mapEl, {
    scrollWheelZoom: false,
    zoomControl: true
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap"
  }).addTo(_filmingDetailMap);

  const bounds = L.latLngBounds();

  locations.forEach((loc, idx) => {
    const lat = Number(loc.lat);
    const lng = Number(loc.lng);

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const icon = L.divIcon({
      className: "",
      html: `<div class="filming-detail-marker"><span>${idx + 1}</span></div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 34],
      popupAnchor: [0, -34]
    });

    const marker = L.marker([lat, lng], { icon })
      .addTo(_filmingDetailMap)
      .bindPopup(`
        <strong>${escapeHtml(loc.name)}</strong><br>
        <small>${escapeHtml([loc.city, loc.country].filter(Boolean).join(", "))}</small>
      `);

    _filmingDetailMarkers.push(marker);
    bounds.extend([lat, lng]);
  });

  setTimeout(() => {
    _filmingDetailMap.invalidateSize();

    if (bounds.isValid()) {
      _filmingDetailMap.fitBounds(bounds, {
        padding: [30, 30],
        maxZoom: 13
      });
    }
  }, 250);
}

function focusFilmingDetailMarker(index) {
  const marker = _filmingDetailMarkers[index];
  if (!marker || !_filmingDetailMap) return;

  _filmingDetailMap.flyTo(marker.getLatLng(), 14, { duration: 0.8 });
  marker.openPopup();
}

function _renderFilmingPagination(page, totalPages) {
  const el = document.getElementById("filming-pagination");
  if (!el) return;

  page = Number(page || 1);
  totalPages = Number(totalPages || 1);

  if (totalPages <= 1) {
    el.innerHTML = "";
    return;
  }

  el.innerHTML = `
    <button ${page <= 1 ? "disabled" : ""} onclick="chargerLieuxDeTournage(${page - 1})">
      Précédent
    </button>
    <span>Page ${page} / ${totalPages}</span>
    <button ${page >= totalPages ? "disabled" : ""} onclick="chargerLieuxDeTournage(${page + 1})">
      Suivant
    </button>
  `;
}

function _extractFilmingMetaFromResults(results) {
  const years = new Set(_filmingAllYears);
  const countries = new Set(_filmingAllCountries);

  (results || []).forEach(f => {
    if (f.year) years.add(Number(f.year));

    (f.locations || []).forEach(l => {
      const name = l.country && l.country !== "Inconnu"
        ? l.country
        : l.name;

      if (name && name.length > 1 && name !== "Inconnu") {
        countries.add(name);
      }
    });
  });

  _filmingAllYears = [...years].sort((a, b) => b - a);
  _filmingAllCountries = [...countries].sort((a, b) => a.localeCompare(b));
}

function _updateFilmingFilters() {
  document.querySelectorAll(".fmedia-btn").forEach(btn => {
    const txt = btn.textContent.trim().toLowerCase();
    const isMovieBtn = txt.includes("film");
    btn.classList.toggle(
      "active",
      isMovieBtn ? _filmingCurrentType === "movie" : _filmingCurrentType === ""
    );
  });

  const fy = document.getElementById("filming-filter-year");
  if (fy) {
    const current = fy.value || _filmingCurrentYear;
    fy.innerHTML = `<option value="">Toutes les années</option>` +
      _filmingAllYears.map(y => `<option value="${y}">${y}</option>`).join("");
    fy.value = current;
  }

  const fc = document.getElementById("filming-filter-country");
  if (fc) {
    const current = fc.value || _filmingCurrentCountry;
    fc.innerHTML = `<option value="">Tous les lieux</option>` +
      _filmingAllCountries.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    fc.value = current;
  }

  const si = document.getElementById("filming-search-input");
  if (si) si.value = _filmingCurrentQ;
}

function _updateFilmingStats() {
  const el = document.getElementById("filming-stats-bar");
  if (!el || !_filmingStats) return;

  el.innerHTML = `
    <span><strong>${_filmingStats.total_films?.toLocaleString() || "—"}</strong> Films</span>
    <span class="filming-stats-sep">·</span>
    <span><strong>${_filmingStats.total_locations?.toLocaleString() || "—"}</strong> lieux</span>
  `;
}

function debounceFilmingSearch(val) {
  _filmingCurrentQ = val;
  _filmingCurrentPage = 1;

  clearTimeout(_filmingSearchTimeout);
  _filmingSearchTimeout = setTimeout(() => {
    _loadFilmingCatalogue();
  }, 450);
}

function setFilmingType(type) {
  _filmingCurrentType = type;
  _filmingCurrentPage = 1;
  _updateFilmingFilters();
  _loadFilmingCatalogue();
}

function setFilmingCountry(country) {
  _filmingCurrentCountry = country;
  _filmingCurrentPage = 1;
  _updateFilmingFilters();
  _loadFilmingCatalogue();
}

function setFilmingYear(year) {
  _filmingCurrentYear = year;
  _filmingCurrentPage = 1;
  _updateFilmingFilters();
  _loadFilmingCatalogue();
}

function resetFilmingFilters() {
  _filmingCurrentCountry = "";
  _filmingCurrentYear = "";
  _filmingCurrentType = "";
  _filmingCurrentQ = "";
  _filmingCurrentPage = 1;

  _updateFilmingFilters();
  _loadFilmingCatalogue();
}

// Exposition globale pour les onclick existants
window.chargerLieuxDeTournage = chargerLieuxDeTournage;
window.ouvrirDetailLieuxTournage = ouvrirDetailLieuxTournage;
window.focusFilmingDetailMarker = focusFilmingDetailMarker;
window.debounceFilmingSearch = debounceFilmingSearch;
window.setFilmingType = setFilmingType;
window.setFilmingCountry = setFilmingCountry;
window.setFilmingYear = setFilmingYear;
window.resetFilmingFilters = resetFilmingFilters;