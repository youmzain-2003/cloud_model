/* Club Scout service worker — cache shell for offline use */
const CACHE = "club-scout-v4-ux";
const ASSETS = [
  "./",
  "./index.html",
  "./tool.html",
  "./mobile.html",
  "./manifest.webmanifest",
  "./icon.svg",
  "./sw.js",
  "./assets/app.css",
  "./assets/club_data.js",
  "./assets/sheet.js",
  "./assets/tool.js",
  "./sheet/index.html",
  "./sheet/01-tiers.html",
  "./sheet/02-trainer.html",
  "./sheet/03-sire.html",
  "./sheet/04-family.html",
  "./sheet/05-cross.html",
  "./sheet/06-combo.html",
  "./sheet/07-weight.html",
  "./sheet/08-points.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          if (res.ok && new URL(event.request.url).origin === self.location.origin) {
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return res;
        })
        .catch(() => caches.match("./index.html"));
    })
  );
});
