(function () {
    'use strict';

    var cfg = window.JP_PORTAL_PUSH || window.JP_MEAL_PUSH;
    if (!cfg || !cfg.publicKey) {
        return;
    }

    var LS_SUBSCRIBED = 'jp_meal_push_subscribed';
    var autoAttempted = false;

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        var i;
        for (i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function supportsPush() {
        return (
            'serviceWorker' in navigator
            && 'PushManager' in window
            && 'Notification' in window
        );
    }

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

    function lsRemove(key) {
        try {
            localStorage.removeItem(key);
        } catch (e) {}
    }

    function getGateEl() {
        return document.getElementById('jpMealPushGate');
    }

    function getSuccessEl() {
        return document.getElementById('jpMealPushSuccess');
    }

    function lockPage() {
        document.body.classList.add('jp-meal-push-locked');
    }

    function unlockPage() {
        document.body.classList.remove('jp-meal-push-locked');
    }

    function showMandatoryGate() {
        var gate = getGateEl();
        if (!gate) {
            return;
        }
        gate.hidden = false;
        lockPage();
    }

    function hideMandatoryGate() {
        var gate = getGateEl();
        if (gate) {
            gate.hidden = true;
        }
        hideGateError();
        unlockPage();
    }

    function showGateError(message) {
        var err = document.getElementById('jpMealPushGateError');
        if (!err) {
            return;
        }
        err.textContent = message || '';
        err.hidden = !message;
    }

    function hideGateError() {
        showGateError('');
    }

    function showSuccessBanner(message) {
        var success = getSuccessEl();
        var text = document.getElementById('jpMealPushSuccessText');
        if (text && message) {
            text.textContent = message;
        }
        if (success) {
            success.hidden = false;
        }
    }

    function hideSuccessBanner() {
        var success = getSuccessEl();
        if (success) {
            success.hidden = true;
        }
    }

    function fetchJson(url, options) {
        return fetch(url, options || {}).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok || !data.ok) {
                    throw new Error((data && data.message) || 'Yêu cầu thất bại.');
                }
                return data;
            });
        });
    }

    function postJson(url, payload) {
        return fetchJson(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload || {}),
        });
    }

    function getBrowserSubscription() {
        if (!supportsPush()) {
            return Promise.resolve(null);
        }
        return navigator.serviceWorker.ready.then(function (registration) {
            return registration.pushManager.getSubscription();
        });
    }

    function saveSubscriptionOnServer(subscription) {
        return postJson(cfg.subscribeUrl, subscription.toJSON()).then(function () {
            lsSet(LS_SUBSCRIBED, '1');
            return subscription;
        });
    }

    function fetchServerStatus() {
        if (!cfg.statusUrl) {
            return Promise.resolve({ subscribed: false, subscription_count: 0 });
        }
        return fetchJson(cfg.statusUrl, { credentials: 'same-origin' });
    }

    function permissionDeniedMessage() {
        return (
            'Trình duyệt đang chặn thông báo. Vào cài đặt trang web → Thông báo → Cho phép, '
            + 'sau đó tải lại trang và bấm «Cho phép nhận nhắc».'
        );
    }

    function isFullySubscribed(browserSub, serverStatus, permission) {
        if (serverStatus && serverStatus.subscribed) {
            return true;
        }
        return !!(browserSub && permission === 'granted');
    }

    window.jpSubscribeMealPush = function () {
        if (!supportsPush()) {
            return Promise.reject(new Error('Trình duyệt không hỗ trợ thông báo đẩy.'));
        }

        hideGateError();

        var permissionPromise;
        if (Notification.permission === 'granted') {
            permissionPromise = Promise.resolve('granted');
        } else if (Notification.permission === 'denied') {
            return Promise.reject(new Error(permissionDeniedMessage()));
        } else {
            permissionPromise = Notification.requestPermission();
        }

        return permissionPromise.then(function (permission) {
            if (permission !== 'granted') {
                throw new Error(
                    permission === 'denied'
                        ? permissionDeniedMessage()
                        : 'Bạn cần chọn Cho phép để tiếp tục dùng portal.',
                );
            }
            return navigator.serviceWorker.ready;
        }).then(function (registration) {
            return registration.pushManager.getSubscription().then(function (existing) {
                if (existing) {
                    return existing;
                }
                return registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(cfg.publicKey),
                });
            });
        }).then(function (subscription) {
            return saveSubscriptionOnServer(subscription);
        }).then(function () {
            hideMandatoryGate();
            showSuccessBanner('Đã bật thông báo portal thành công.');
            if (window.jpResetAnnouncementPushBaseline) {
                window.jpResetAnnouncementPushBaseline();
            }
        });
    };

    function disableMealPush() {
        return getBrowserSubscription().then(function (subscription) {
            var tasks = [postJson(cfg.unsubscribeUrl, subscription ? { endpoint: subscription.endpoint } : {})];
            if (subscription) {
                tasks.push(subscription.unsubscribe());
            }
            return Promise.all(tasks);
        }).then(function () {
            lsRemove(LS_SUBSCRIBED);
            hideSuccessBanner();
            showMandatoryGate();
            scheduleAutoSubscribe();
        });
    }

    function sendTestPush() {
        if (!cfg.testUrl) {
            return Promise.reject(new Error('Chưa cấu hình gửi thử.'));
        }
        return postJson(cfg.testUrl, {}).then(function (data) {
            var text = document.getElementById('jpMealPushSuccessText');
            if (text) {
                text.textContent = data.message || 'Đã gửi thông báo thử.';
            }
        }).catch(function (err) {
            var msg = (err && err.message) || '';
            if (msg.indexOf('Chưa đăng ký') !== -1 || msg.indexOf('bật lại') !== -1) {
                lsRemove(LS_SUBSCRIBED);
                hideSuccessBanner();
                showMandatoryGate();
                scheduleAutoSubscribe();
            }
            throw err;
        });
    }

    function scheduleAutoSubscribe() {
        if (autoAttempted) {
            return;
        }
        autoAttempted = true;
        window.setTimeout(function () {
            window.jpSubscribeMealPush().catch(function (err) {
                showGateError(err.message || 'Không bật được nhắc đẩy.');
            });
        }, 350);
    }

    function refreshPushUI() {
        lsRemove('jp_meal_push_prompt_dismissed');

        if (!supportsPush()) {
            hideMandatoryGate();
            return Promise.resolve();
        }

        return Promise.all([getBrowserSubscription(), fetchServerStatus()]).then(function (results) {
            var browserSub = results[0];
            var serverStatus = results[1];
            var permission = Notification.permission;

            if (!serverStatus.subscribed && lsGet(LS_SUBSCRIBED) === '1') {
                lsRemove(LS_SUBSCRIBED);
            }

            if (isFullySubscribed(browserSub, serverStatus, permission)) {
                if (browserSub && permission === 'granted' && !serverStatus.subscribed) {
                    return saveSubscriptionOnServer(browserSub).then(function () {
                        hideMandatoryGate();
                        showSuccessBanner('Đã đăng ký nhắc đẩy trên thiết bị này.');
                    }).catch(function () {
                        hideMandatoryGate();
                        showSuccessBanner('Đã đăng ký nhắc đẩy trên tài khoản của bạn.');
                    });
                }
                hideMandatoryGate();
                showSuccessBanner('Đã đăng ký thông báo đặt cơm.');
                return;
            }

            showMandatoryGate();
            scheduleAutoSubscribe();
        }).catch(function () {
            showMandatoryGate();
            scheduleAutoSubscribe();
        });
    }

    function bindPushUI() {
        var enableBtn = document.getElementById('jpMealPushEnable');
        var testBtn = document.getElementById('jpMealPushTest');
        var disableBtn = document.getElementById('jpMealPushDisable');

        if (enableBtn) {
            enableBtn.addEventListener('click', function () {
                enableBtn.disabled = true;
                window.jpSubscribeMealPush()
                    .catch(function (err) {
                        showGateError(err.message || 'Không bật được nhắc đẩy.');
                    })
                    .finally(function () {
                        enableBtn.disabled = false;
                    });
            });
        }

        if (testBtn) {
            testBtn.addEventListener('click', function () {
                testBtn.disabled = true;
                sendTestPush()
                    .catch(function (err) {
                        window.alert(err.message || 'Không gửi được thông báo thử.');
                    })
                    .finally(function () {
                        testBtn.disabled = false;
                    });
            });
        }

        if (disableBtn) {
            disableBtn.addEventListener('click', function () {
                if (!window.confirm('Tắt nhắc đẩy đặt cơm trên thiết bị này? Lần sau vào portal sẽ phải bật lại.')) {
                    return;
                }
                disableBtn.disabled = true;
                disableMealPush()
                    .catch(function (err) {
                        window.alert(err.message || 'Không tắt được nhắc đẩy.');
                    })
                    .finally(function () {
                        disableBtn.disabled = false;
                    });
            });
        }

        refreshPushUI();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindPushUI);
    } else {
        bindPushUI();
    }
})();
