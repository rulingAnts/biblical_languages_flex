/* FLEx Interlinear PWA Service Worker */
/* Build: 2026-04-19b */

const CACHE_VERSION = 'v2-2026-04-19b';
const CORE_CACHE = `blf-core-${CACHE_VERSION}`;
const DATA_CACHE = `blf-data-${CACHE_VERSION}`;
const RUNTIME_CACHE = `blf-runtime-${CACHE_VERSION}`;

// Core shell + UX assets that must be available offline immediately
const CORE_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/favicon.svg',
  './icons/maskable.svg',
  './robots.txt'
];

// Data files to precache (safe size). Large binary assets are cached on-demand
const DATA_FILES = [
  './assets/strongs_greek.json',
  './assets/data/1Corinthians.json',
  './assets/data/1John.json',
  './assets/data/1Peter.json',
  './assets/data/1Thessalonians.json',
  './assets/data/1Timothy.json',
  './assets/data/2Corinthians.json',
  './assets/data/2John.json',
  './assets/data/2Peter.json',
  './assets/data/2Thessalonians.json',
  './assets/data/2Timothy.json',
  './assets/data/3John.json',
  './assets/data/Acts.json',
  './assets/data/Colossians.json',
  './assets/data/Ephesians.json',
  './assets/data/Galatians.json',
  './assets/data/Hebrews.json',
  './assets/data/James.json',
  './assets/data/John.json',
  './assets/data/Jude.json',
  './assets/data/Luke.json',
  './assets/data/Mark.json',
  './assets/data/Matthew.json',
  './assets/data/Philemon.json',
  './assets/data/Philippians.json',
  './assets/data/Revelation.json',
  './assets/data/Romans.json',
  './assets/data/Titus.json',
  './assets/data/guid_map.json'
];

self.addEventListener('install', event => {
  // Take over immediately on new deploy
  self.skipWaiting();
  event.waitUntil((async () => {
    const core = await caches.open(CORE_CACHE);
    await core.addAll(CORE_ASSETS);
    const data = await caches.open(DATA_CACHE);
    await data.addAll(DATA_FILES);
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    // Clean old caches
    const names = await caches.keys();
    await Promise.all(names.map(name => {
      if (!name.includes(CACHE_VERSION)) {
        return caches.delete(name);
      }
    }));
    // Become the active worker for current clients
    await self.clients.claim();
  })());
});

self.addEventListener('message', event => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin
  if (url.origin !== location.origin) return;

  // App shell navigation: network-first, fallback to cached index
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        // Cache the latest index.html for offline
        const copy = fresh.clone();
        const cache = await caches.open(CORE_CACHE);
        cache.put('./index.html', copy);
        return fresh;
      } catch (err) {
        const cache = await caches.open(CORE_CACHE);
        const cached = await cache.match('./index.html');
        if (cached) return cached;
        return new Response('Offline', { status: 503, statusText: 'Offline' });
      }
    })());
    return;
  }

  // Data JSON: stale-while-revalidate from DATA_CACHE
  if (url.pathname.startsWith(self.registration.scope.replace(location.origin, '') + 'assets/data/')) {
    event.respondWith(staleWhileRevalidate(req, DATA_CACHE));
    return;
  }

  // Large binary assets (SWORD modules, fwbackup): cache-first in RUNTIME_CACHE on demand
  if (url.pathname.includes('/sword_repo/') || url.pathname.endsWith('.fwbackup')) {
    event.respondWith(cacheFirst(req, RUNTIME_CACHE));
    return;
  }

  // Default: try cache, else network, and cache successful GETs in runtime
  event.respondWith((async () => {
    const cache = await caches.open(RUNTIME_CACHE);
    const cached = await cache.match(req);
    if (cached) return cached;
    try {
      const res = await fetch(req);
      if (req.method === 'GET' && res.ok && (res.type === 'basic' || res.type === 'cors')) {
        cache.put(req, res.clone());
      }
      return res;
    } catch (err) {
      if (req.destination === 'document') {
        const core = await caches.open(CORE_CACHE);
        const fallback = await core.match('./index.html');
        if (fallback) return fallback;
      }
      throw err;
    }
  })());
});

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  const networkPromise = fetch(req).then(res => {
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  }).catch(() => undefined);
  return cached || networkPromise || new Response('Offline', { status: 503 });
}

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res && res.ok) cache.put(req, res.clone());
  return res;
}
