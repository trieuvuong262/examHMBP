(function () {
    'use strict';

    var cfg = window.JP_MEAL_PUSH;
    if (!cfg || !cfg.publicKey) {
        return;
    }

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

    function hasSubscribed() {
        try {
            return localStorage.getItem('jp_meal_push_subscribed') === '1';
        } catch (e) {
            return false;
        }
    }

    function markSubscribed() {
        try {
            localStorage.setItem('jp_meal_push_subscribed', '1');
        } catch (e) {}
    }

    function markPromptDismissed() {
        try {
            localStorage.setItem('jp_meal_push_prompt_dismissed', '1');
        } catch (e) {}
    }

    function shouldShowPrompt() {
        if (!supportsPush()) {
            return false;
        }
        if (hasSubscribed()) {
            return false;
        }
        try {
            return localStorage.getItem('jp_meal_push_prompt_dismissed') !== '1';
        } catch (e) {
            return true;
        }
    }

    function postJson(url, payload) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload || {}),
        }).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok || !data.ok) {
                    throw new Error((data && data.message) || 'Đăng ký push thất bại.');
                }
                return data;
            });
        });
    }

  window.jpSubscribeMealPush = function () {
        if (!supportsPush()) {
            return Promise.reject(new Error('Trình duyệt không hỗ trợ thông báo đẩy.'));
        }
        return Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                throw new Error('Bạn chưa cho phép thông báo.');
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
            return postJson(cfg.subscribeUrl, subscription.toJSON()).then(function () {
                markSubscribed();
                return subscription;
            });
        });
    };

    function bindPrompt() {
        var banner = document.getElementById('jpMealPushPrompt');
        if (!banner || !shouldShowPrompt()) {
            return;
        }
        banner.hidden = false;

        var enableBtn = document.getElementById('jpMealPushEnable');
        var dismissBtn = document.getElementById('jpMealPushDismiss');
        if (enableBtn) {
            enableBtn.addEventListener('click', function () {
                enableBtn.disabled = true;
                window.jpSubscribeMealPush()
                    .then(function () {
                        banner.hidden = true;
                    })
                    .catch(function (err) {
                        enableBtn.disabled = false;
                        window.alert(err.message || 'Không bật được nhắc đẩy.');
                    });
            });
        }
        if (dismissBtn) {
            dismissBtn.addEventListener('click', function () {
                markPromptDismissed();
                banner.hidden = true;
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindPrompt);
    } else {
        bindPrompt();
    }
})();
