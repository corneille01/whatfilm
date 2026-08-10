const CACHE_NAME = "pelify-app-v7";

const APP_SHELL = [
  "/",
  "/frontend/style.css?v=91",
  "/frontend/script.js?v=91",
  "/frontend/filming.js?v=66",
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
    url.pathname.startsWith("/")||
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