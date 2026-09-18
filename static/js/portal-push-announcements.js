(function () {
    'use strict';

    var cfg = window.JP_PORTAL_PUSH || window.JP_MEAL_PUSH;
    if (!cfg || !cfg.announcementPollUrl) {
        return;
    }

    var LS_LAST_NOTIFIED = 'jp_ann_last_notified_id';
    var LS_BASELINE = 'jp_ann_push_baseline_id';
    var POLL_MS = 45000;
    var MAX_BACKOFF_MS = 120000;
    var nextMs = POLL_MS;
    var timer = null;

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

    function markFail() {
        nextMs = Math.min(Math.max(nextMs, POLL_MS) * 2, MAX_BACKOFF_MS);
    }

    function markOk() {
        nextMs = POLL_MS;
    }

    function fetchUnread() {
        return fetch(cfg.announcementPollUrl, { credentials: 'same-origin' })
            .then(function (resp) {
                if (resp.status >= 500 || resp.status === 429) {
                    var err = new Error('poll ' + resp.status);
                    err.backoff = true;
                    throw err;
                }
                return resp.json();
            })
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
            markOk();
            return Promise.resolve();
        }
        return fetchUnread().then(function (data) {
            markOk();
            return maybeNotify(data);
        }).catch(function (err) {
            markFail();
        });
    }

    function scheduleNext() {
        if (timer) {
            window.clearTimeout(timer);
        }
        timer = window.setTimeout(function () {
            pollOnce().then(scheduleNext);
        }, nextMs);
    }

    function setBaselineFromServer() {
        return fetchUnread().then(function (data) {
            markOk();
            if (data.has_new && data.announcement_id) {
                lsSet(LS_BASELINE, String(data.announcement_id));
                lsSet(LS_LAST_NOTIFIED, String(data.announcement_id));
            } else {
                lsSet(LS_BASELINE, '0');
            }
        }).catch(function () {
            markFail();
        });
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
            setBaselineFromServer().then(scheduleNext);
            return;
        }
        pollOnce().then(scheduleNext);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startPolling);
    } else {
        startPolling();
    }
})();
