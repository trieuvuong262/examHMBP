(function () {
    'use strict';

    var cfg = window.JP_MEAL_PUSH;
    if (!cfg || !cfg.publicKey) {
        return;
    }

    var LS_SUBSCRIBED = 'jp_meal_push_subscribed';
    var LS_DISMISSED = 'jp_meal_push_prompt_dismissed';

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

    function getPromptEl() {
        return document.getElementById('jpMealPushPrompt');
    }

    function getSuccessEl() {
        return document.getElementById('jpMealPushSuccess');
    }

    function hideAllPushBanners() {
        var prompt = getPromptEl();
        var success = getSuccessEl();
        if (prompt) {
            prompt.hidden = true;
        }
        if (success) {
            success.hidden = true;
        }
    }

    function showPromptBanner() {
        hideAllPushBanners();
        var prompt = getPromptEl();
        if (prompt) {
            prompt.hidden = false;
        }
    }

    function showSuccessBanner(message) {
        hideAllPushBanners();
        var success = getSuccessEl();
        var text = document.getElementById('jpMealPushSuccessText');
        if (text && message) {
            text.textContent = message;
        }
        if (success) {
            success.hidden = false;
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
            lsRemove(LS_DISMISSED);
            return subscription;
        });
    }

    function fetchServerStatus() {
        if (!cfg.statusUrl) {
            return Promise.resolve({ subscribed: false, subscription_count: 0 });
        }
        return fetchJson(cfg.statusUrl, { credentials: 'same-origin' });
    }

    function isSubscribedLocally() {
        return lsGet(LS_SUBSCRIBED) === '1';
    }

    function isPromptDismissed() {
        return lsGet(LS_DISMISSED) === '1';
    }

    function refreshPushUI() {
        if (!supportsPush()) {
            hideAllPushBanners();
            return Promise.resolve();
        }

        return Promise.all([getBrowserSubscription(), fetchServerStatus()]).then(function (results) {
            var browserSub = results[0];
            var serverStatus = results[1];
            var permission = Notification.permission;

            if (browserSub && permission === 'granted') {
                return saveSubscriptionOnServer(browserSub).then(function () {
                    showSuccessBanner('Đã đăng ký nhắc đẩy trên thiết bị này.');
                }).catch(function () {
                    if (serverStatus.subscribed) {
                        showSuccessBanner('Đã đăng ký nhắc đẩy (đồng bộ từ máy chủ).');
                    } else if (!isPromptDismissed()) {
                        showPromptBanner();
                    }
                });
            }

            if (serverStatus.subscribed || isSubscribedLocally()) {
                showSuccessBanner('Đã đăng ký nhắc đẩy trên tài khoản của bạn.');
                return;
            }

            if (!isPromptDismissed()) {
                showPromptBanner();
            } else {
                hideAllPushBanners();
            }
        }).catch(function () {
            if (!isPromptDismissed() && !isSubscribedLocally()) {
                showPromptBanner();
            }
        });
    }

    window.jpSubscribeMealPush = function () {
        if (!supportsPush()) {
            return Promise.reject(new Error('Trình duyệt không hỗ trợ thông báo đẩy.'));
        }

        return Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                throw new Error('Bạn chưa cho phép thông báo trên trình duyệt.');
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
            showSuccessBanner('Đã bật nhắc đẩy thành công.');
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
            lsRemove(LS_DISMISSED);
            hideAllPushBanners();
            showPromptBanner();
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
        });
    }

    function bindPushUI() {
        var enableBtn = document.getElementById('jpMealPushEnable');
        var dismissBtn = document.getElementById('jpMealPushDismiss');
        var testBtn = document.getElementById('jpMealPushTest');
        var disableBtn = document.getElementById('jpMealPushDisable');

        if (enableBtn) {
            enableBtn.addEventListener('click', function () {
                enableBtn.disabled = true;
                window.jpSubscribeMealPush()
                    .catch(function (err) {
                        window.alert(err.message || 'Không bật được nhắc đẩy.');
                    })
                    .finally(function () {
                        enableBtn.disabled = false;
                    });
            });
        }

        if (dismissBtn) {
            dismissBtn.addEventListener('click', function () {
                lsSet(LS_DISMISSED, '1');
                hideAllPushBanners();
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
                if (!window.confirm('Tắt nhắc đẩy đặt cơm trên thiết bị này?')) {
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
