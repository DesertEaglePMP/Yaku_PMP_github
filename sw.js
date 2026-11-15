/* YAKU · service worker: la app funciona sin internet después de la primera visita.
   SI disclosure: code generated with assistance of Claude (Anthropic); reviewed by team YAKU – HIDROTECH. */
const VERSION = "yaku-v6";
const NUCLEO = ["./", "./index.html", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/maskable-192.png", "./icons/maskable-512.png",
  "./icons/apple-touch-icon.png", "./icons/favicon-32.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(NUCLEO)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
// Red primero (para recibir datos y versiones nuevas); si no hay internet, se usa la copia guardada.
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  // Las consultas a la NASA, mapas e imágenes externas van directo a internet (sin pasar por la caché)
  if (new URL(req.url).origin !== location.origin && !req.url.includes("fonts.g")) return;
  e.respondWith(
    fetch(req).then(res => {
      if (res && res.ok && (new URL(req.url).origin === location.origin || req.url.includes("fonts.g"))) {
        const copia = res.clone();
        caches.open(VERSION).then(c => c.put(req, copia));
      }
      return res;
    }).catch(() => caches.match(req).then(r => r || caches.match("./index.html")))
  );
});
