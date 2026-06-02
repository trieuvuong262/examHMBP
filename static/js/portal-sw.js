/* Service worker tối thiểu — Edge/Chrome nhận PWA "Install JustPlay Portal". */
self.addEventListener('install', function (event) {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});
