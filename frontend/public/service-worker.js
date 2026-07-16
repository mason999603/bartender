// Russell PWA service worker — minimal offline shell.
// We keep the caching strategy conservative: cache the app shell aggressively,
// but always go network-first for API calls (a stale reply from Russell is worse
// than a "you're offline" toast).

const CACHE = "russell-shell-v1";
const SHELL = [
    "/",
    "/manifest.json",
    "/icon-192.png",
    "/icon-512.png",
    "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => { /* first-run: no-op */ }))
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        Promise.all([
            caches.keys().then((keys) =>
                Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
            ),
            self.clients.claim(),
        ])
    );
});

self.addEventListener("fetch", (event) => {
    const { request } = event;
    if (request.method !== "GET") return;

    const url = new URL(request.url);

    // Never cache API — Russell needs fresh data.
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/spotify/callback")) {
        return;
    }

    // Same-origin GET: network-first with cache fallback.
    if (url.origin === self.location.origin) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => { });
                    return response;
                })
                .catch(() => caches.match(request).then((r) => r || caches.match("/")))
        );
    }
});
