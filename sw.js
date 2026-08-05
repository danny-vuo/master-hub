// Minimal service worker — required by Chrome/Edge to make the Hub installable
// as a standalone app (which enables the Launch Handler "focus-existing" behavior
// in manifest.json). Intentionally does no caching: tools.json/pulse.json/updates.json
// must always be fetched fresh, so every request just passes straight to the network.
self.addEventListener('install', (event) => {
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  self.clients.claim();
});
self.addEventListener('fetch', (event) => {
  // No-op: let the browser handle every request normally.
});
