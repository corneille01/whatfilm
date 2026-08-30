const CACHE_NAME = "pelify-app-v12";

const APP_SHELL = [
  "/",
  "/frontend/style.css?v=115",
  "/frontend/script.js?v=115",
  "/frontend/filming.js?v=69",
  "/frontend/manifest.webmanifest",
  "/.well-known/assetlinks.json",

  "/frontend/images/logo.webp",
  "/frontend/images/logo.png",
  "/frontend/images/icon-192.png",
  "/frontend/images/icon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      for (const url of APP_SHELL) {
        try {
          await cache.add(url);
        } catch (e) {
          console.warn("Cache ignoré:", url, e);
        }
      }
    })
  );

  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    )
  );

  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== "GET") return;

  // ⚠️ Ne JAMAIS mettre en cache les routes d'auth / paiement : ce sont
  // des réponses propres à chaque utilisateur (session, abonnement),
  // et une réponse mise en cache pourrait être reservie à quelqu'un
  // d'autre, ou resservir un vieil état "déconnecté" après connexion.
  if (
    url.pathname.startsWith("/auth/") ||
    url.pathname.startsWith("/billing/")
  ) {
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/"))
    );
    return;
  }

  if (url.pathname.startsWith("/frontend/")) {
    event.respondWith(
      caches.match(req).then(cached => {
        return cached || fetch(req).then(res => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
          return res;
        });
      })
    );
    return;
  }

  if (
    url.pathname === "/trending" ||
    url.pathname.startsWith("/discover/") ||
    url.pathname.startsWith("/discover-provider/") ||
    url.pathname.startsWith("/movie/") ||
    url.pathname.startsWith("/films-tournes")||
    url.pathname.startsWith("/film")||
    url.pathname.startsWith("/genre")||
    url.pathname === "/" ||
    url.pathname.startsWith("/fr")||
    url.pathname.startsWith("/es")||
    url.pathname.startsWith("/de")||
    url.pathname.startsWith("/us")||
    url.pathname.startsWith("/zh")||
    url.pathname.startsWith("/gb")
  ) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async cache => {
        const cached = await cache.match(req);

        const network = fetch(req)
          .then(res => {
            if (res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);

        return cached || network;
      })
    );
  }
});