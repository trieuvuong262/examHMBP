(function () {
    'use strict';

    var cfg = window.JP_PORTAL_PUSH || window.JP_MEAL_PUSH;
    if (!cfg || !cfg.schedulePollUrl) {
        return;
    }

    var LS_PREFIX = 'jp_sched_notified_';
    var POLL_MS = 15000;

    function lsGet(key) {
        try {
            return localStorage.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function lsSet(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (e) {}
    }

    function canPoll() {
        return (
            'Notification' in window
            && Notification.permission === 'granted'
            && 'serviceWorker' in navigator
        );
    }

    function showLocalNotification(item) {
        var title = item.title || 'Nhắc lịch';
        var body = item.body || 'Đến giờ nhắc việc của bạn.';
        var url = item.url || '/cong-cu/nhac-lich/';
        var tag = 'schedule-reminder-' + (item.reminder_id || 'due');

        return navigator.serviceWorker.ready.then(function (registration) {
            return registration.showNotification(title, {
                body: body,
                icon: '/static/images/logo/icon-192.png',
                badge: '/static/images/logo/icon-192.png',
                tag: tag,
                renotify: true,
                data: { url: url },
            });
        });
    }

    function pollOnce() {
        if (!canPoll()) {
            return Promise.resolve();
        }
        return fetch(cfg.schedulePollUrl, { credentials: 'same-origin' })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (!data.ok || !data.has_due || !data.fire_key) {
                    return;
                }
                var lsKey = LS_PREFIX + data.fire_key;
                if (lsGet(lsKey) === '1') {
                    return;
                }
                return showLocalNotification(data).then(function () {
                    lsSet(lsKey, '1');
                });
            })
            .catch(function () {});
    }

    function startPolling() {
        if (!canPoll()) {
            return;
        }
        pollOnce();
        window.setInterval(pollOnce, POLL_MS);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startPolling);
    } else {
        startPolling();
    }
})();
