/* Service Worker: Offline-Hülle, Web-Push-Alarme. Medien und API werden nie zwischengespeichert
   (außer der Alarmliste als Offline-Fallback). */
const CACHE = 'hornet3000-v1';
const SHELL = [
  '/', '/assets/style.css', '/assets/app.js', '/assets/knowledge.html',
  '/assets/icons/icon-192.png', '/assets/icons/favicon.svg',
  '/assets/fonts/bitter-latin-700-normal.woff2', '/assets/fonts/bitter-latin-600-normal.woff2',
  '/assets/fonts/atkinson-hyperlegible-latin-400-normal.woff2', '/assets/fonts/atkinson-hyperlegible-latin-700-normal.woff2',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname === '/api/alerts') {            // Liste: online frisch, offline zuletzt bekannter Stand
    e.respondWith(fetch(req).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(req, c)); } return r; })
      .catch(() => caches.match(req)));
    return;
  }
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/') || url.pathname.startsWith('/share/')) return;
  if (req.mode === 'navigate') {                   // Seite: online frisch, offline Hülle
    e.respondWith(fetch(req).catch(() => caches.match('/')));
    return;
  }
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(req, c)); } return r; }).catch(() => hit);
    return hit || net;
  }));
});

self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { title: 'Hornet3000', body: e.data ? e.data.text() : '' }; }
  const isTest = (d.tag || '').includes('test');
  e.waitUntil(self.registration.showNotification(d.title || 'Hornissen-Alarm', {
    body: d.body || '',
    icon: '/assets/icons/icon-192.png',
    badge: '/assets/icons/badge-96.png',
    image: d.image || undefined,
    tag: d.tag || 'hornet',
    renotify: true,
    requireInteraction: !isTest,
    vibrate: [300, 120, 300, 120, 600],
    data: { url: d.url || '/#alarme' },
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || '/#alarme';
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of all) {
      if ('focus' in c) { await c.focus(); c.postMessage({ goto: target }); return; }
    }
    await self.clients.openWindow(target);
  })());
});
