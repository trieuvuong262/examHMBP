/* Service worker — PWA + web push nhắc đặt cơm. */
self.addEventListener('install', function (event) {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function (event) {
    var data = {
        title: 'Đặt cơm công ty',
        body: 'Mở portal để đặt cơm.',
        url: '/',
        tag: 'meal-reminder',
    };
    if (event.data) {
        try {
            var parsed = event.data.json();
            data = Object.assign(data, parsed);
        } catch (e) {}
    }
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/images/logo/icon-192.png',
            badge: '/static/images/logo/icon-192.png',
            data: { url: data.url || '/' },
            tag: data.tag || 'meal-reminder',
            renotify: true,
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var targetUrl = (event.notification.data && event.notification.data.url) || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            var i;
            for (i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if (client.url.indexOf(targetUrl) !== -1 && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
