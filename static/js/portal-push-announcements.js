(function () {
    'use strict';

    var cfg = window.JP_PORTAL_PUSH || window.JP_MEAL_PUSH;
    if (!cfg || !cfg.announcementPollUrl) {
        return;
    }

    var LS_LAST_NOTIFIED = 'jp_ann_last_notified_id';
    var LS_BASELINE = 'jp_ann_push_baseline_id';
    var POLL_MS = 45000;

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
        var title = item.title || 'Thông báo mới';
        var body = item.summary || 'Có thông báo mới trên portal.';
        var url = item.url || '/announcements/';
        var tag = 'announcement-' + (item.announcement_id || 'new');

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

    function fetchUnread() {
        return fetch(cfg.announcementPollUrl, { credentials: 'same-origin' })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (!data.ok) {
                    throw new Error(data.message || 'Poll failed');
                }
                return data;
            });
    }

    function maybeNotify(data) {
        if (!data.has_new || !data.announcement_id) {
            return Promise.resolve();
        }

        var annId = String(data.announcement_id);
        var lastNotified = lsGet(LS_LAST_NOTIFIED);
        if (lastNotified === annId) {
            return Promise.resolve();
        }

        return showLocalNotification(data).then(function () {
            lsSet(LS_LAST_NOTIFIED, annId);
        });
    }

    function pollOnce() {
        if (!canPoll()) {
            return Promise.resolve();
        }
        return fetchUnread().then(maybeNotify).catch(function () {});
    }

    function setBaselineFromServer() {
        return fetchUnread().then(function (data) {
            if (data.has_new && data.announcement_id) {
                lsSet(LS_BASELINE, String(data.announcement_id));
                lsSet(LS_LAST_NOTIFIED, String(data.announcement_id));
            } else {
                lsSet(LS_BASELINE, '0');
            }
        }).catch(function () {});
    }

    window.jpResetAnnouncementPushBaseline = function () {
        setBaselineFromServer().then(function () {
            pollOnce();
        });
    };

    function startPolling() {
        if (!canPoll()) {
            return;
        }
        var baseline = lsGet(LS_BASELINE);
        if (baseline === null) {
            setBaselineFromServer().then(function () {
                window.setInterval(pollOnce, POLL_MS);
            });
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
