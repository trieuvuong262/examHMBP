(function () {
    'use strict';

    var cfg = window.JP_PORTAL_PUSH || window.JP_MEAL_PUSH;
    if (!cfg || !cfg.publicKey) {
        return;
    }

    var LS_SUBSCRIBED = 'jp_meal_push_subscribed';
    var permissionWatchStarted = false;
    var isChromium = /Chrome|Chromium|Edg\//.test(navigator.userAgent)
        && !/OPR\/|Opera/.test(navigator.userAgent);

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
        /* Không chặn cuộn / thao tác trang — gợi ý push là tùy chọn. */
    }

    function unlockPage() {
        document.body.classList.remove('jp-meal-push-locked');
    }

    function showOptionalGate() {
        var gate = getGateEl();
        if (!gate) {
            return;
        }
        gate.hidden = false;
        unlockPage();
        prewarmServiceWorker();
        applyBrowserGuideCopy();
    }

    function showMandatoryGate() {
        showOptionalGate();
    }

    function prewarmServiceWorker() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.ready.catch(function () {});
        }
    }

    function recordConsentOnServer(permission, pushSubscribed) {
        if (!cfg.consentUrl) {
            return Promise.resolve();
        }
        return postJson(cfg.consentUrl, {
            browser_permission: permission || (window.Notification ? Notification.permission : 'default'),
            push_subscribed: !!pushSubscribed,
        });
    }

    function completePortalConsent(permission, pushSubscribed) {
        return recordConsentOnServer(permission, pushSubscribed).then(function () {
            hideMandatoryGate();
            hideBlockGuide();
            hideGateError();
        });
    }

    function hideMandatoryGate() {
        var gate = getGateEl();
        if (gate) {
            gate.hidden = true;
        }
        hideGateError();
        unlockPage();
    }

    function dismissPushGate() {
        hideGateError();
        hideBlockGuide();
        var permission = window.Notification ? Notification.permission : 'default';
        return completePortalConsent(permission || 'default', false);
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

    function isAdminDebugPanel() {
        return !!getSuccessEl();
    }

    function showSuccessBanner(message) {
        if (!isAdminDebugPanel()) {
            return;
        }
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
            return Promise.resolve({
                subscribed: false,
                subscription_count: 0,
                consent_recorded: false,
            });
        }
        return fetchJson(cfg.statusUrl, { credentials: 'same-origin' });
    }

    function permissionDeniedMessage() {
        if (isChromium) {
            return (
                'Chrome đang chặn thông báo. Bấm biểu tượng điều chỉnh quyền (hoặc ổ khoá) '
                + 'bên trái địa chỉ → Notifications → Allow, rồi bấm «Kiểm tra lại».'
            );
        }
        return (
            'Trình duyệt đang chặn thông báo. Mở cài đặt trang web → Notifications → Allow, '
            + 'sau đó bấm «Kiểm tra lại».'
        );
    }

    function permissionDismissedMessage() {
        return isChromium
            ? 'Bấm Allow trên hộp thoại Chrome (góc trên thanh địa chỉ), không bấm Block.'
            : 'Bấm Allow trên hộp thoại trình duyệt, không chỉ nút portal.';
    }

    function isFullySubscribed(browserSub, serverStatus, permission) {
        if (permission !== 'granted') {
            return false;
        }
        if (serverStatus && serverStatus.subscribed) {
            return true;
        }
        return !!browserSub;
    }

    function applyBrowserGuideCopy() {
        document.querySelectorAll('[data-jp-push-chrome]').forEach(function (el) {
            el.hidden = !isChromium;
        });
        document.querySelectorAll('[data-jp-push-generic]').forEach(function (el) {
            el.hidden = isChromium;
        });
        var chromeHint = document.getElementById('jpMealPushChromeHint');
        if (chromeHint) {
            chromeHint.hidden = Notification.permission !== 'default' || !isChromium;
        }
    }

    function showBlockGuide() {
        var guide = document.getElementById('jpMealPushBlockGuide');
        var note = document.getElementById('jpMealPushGateNote');
        var chromeHint = document.getElementById('jpMealPushChromeHint');
        var enableBtn = document.getElementById('jpMealPushEnable');
        if (guide) {
            guide.hidden = false;
        }
        if (note) {
            note.hidden = true;
        }
        if (chromeHint) {
            chromeHint.hidden = true;
        }
        if (enableBtn) {
            enableBtn.hidden = true;
        }
        hideGateError();
        applyBrowserGuideCopy();
        startPermissionWatch();
    }

    function hideBlockGuide() {
        var guide = document.getElementById('jpMealPushBlockGuide');
        var note = document.getElementById('jpMealPushGateNote');
        var enableBtn = document.getElementById('jpMealPushEnable');
        if (guide) {
            guide.hidden = true;
        }
        if (note) {
            note.hidden = false;
        }
        if (enableBtn) {
            enableBtn.hidden = false;
        }
        applyBrowserGuideCopy();
    }

    function updateGateForPermission() {
        var enableBtn = document.getElementById('jpMealPushEnable');
        if (!enableBtn) {
            return;
        }
        if (Notification.permission === 'denied') {
            enableBtn.textContent = 'Cho phép nhận thông báo';
            enableBtn.hidden = false;
            hideBlockGuide();
        } else {
            enableBtn.textContent = 'Cho phép nhận thông báo';
            hideBlockGuide();
        }
        applyBrowserGuideCopy();
    }

    function subscribeAfterPermission(permission) {
        if (permission !== 'granted') {
            return Promise.resolve();
        }
        return navigator.serviceWorker.ready.then(function (registration) {
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
            showSuccessBanner('Đã đăng ký push trên thiết bị này.');
            if (window.jpResetAnnouncementPushBaseline) {
                window.jpResetAnnouncementPushBaseline();
            }
        });
    }

    function requestPermissionInClick() {
        if (Notification.permission === 'granted') {
            return Promise.resolve('granted');
        }
        if (Notification.permission === 'denied') {
            return Promise.reject(new Error(permissionDeniedMessage()));
        }
        return Notification.requestPermission();
    }

    window.jpSubscribeMealPush = function () {
        if (!supportsPush()) {
            return Promise.reject(new Error('Trình duyệt không hỗ trợ thông báo đẩy.'));
        }
        hideGateError();
        return requestPermissionInClick()
            .then(function (permission) {
                return completePortalConsent(permission, false).then(function () {
                    return subscribeAfterPermission(permission);
                });
            })
            .catch(function () {
                return completePortalConsent(Notification.permission, false);
            });
    };

    function onEnableButtonClick() {
        if (!supportsPush()) {
            showGateError('Trình duyệt không hỗ trợ thông báo đẩy.');
            return;
        }

        hideGateError();
        hideBlockGuide();

        var enableBtn = document.getElementById('jpMealPushEnable');
        if (enableBtn) {
            enableBtn.disabled = true;
        }

        var permission = Notification.permission;
        var flow;

        if (permission === 'granted') {
            flow = completePortalConsent('granted', false).then(function () {
                return subscribeAfterPermission('granted');
            });
        } else if (permission === 'denied') {
            flow = completePortalConsent('denied', false);
        } else {
            flow = requestPermissionInClick()
                .then(function (result) {
                    return completePortalConsent(result, false).then(function () {
                        if (result === 'granted') {
                            return subscribeAfterPermission('granted');
                        }
                    });
                })
                .catch(function () {
                    return completePortalConsent(Notification.permission, false);
                });
        }

        flow
            .catch(function (err) {
                if (!Notification.permission || Notification.permission !== 'granted') {
                    return completePortalConsent(Notification.permission, false);
                }
                showGateError((err && err.message) || 'Không đăng ký được push.');
            })
            .finally(function () {
                if (enableBtn) {
                    enableBtn.disabled = false;
                }
                updateGateForPermission();
            });
    }

    function startPermissionWatch() {
        if (permissionWatchStarted || !navigator.permissions || !navigator.permissions.query) {
            return;
        }
        permissionWatchStarted = true;
        navigator.permissions.query({ name: 'notifications' }).then(function (status) {
            function onStatusChange() {
                if (status.state === 'granted') {
                    hideBlockGuide();
                    hideGateError();
                    subscribeAfterPermission('granted').catch(function (err) {
                        showGateError(err.message || 'Không đăng ký được push.');
                    });
                } else if (status.state === 'denied') {
                    updateGateForPermission();
                }
            }
            if (status.state === 'granted') {
                onStatusChange();
            }
            status.onchange = onStatusChange;
        }).catch(function () {});
    }

    function recheckAfterUnblock() {
        hideGateError();
        var permission = Notification.permission;

        if (permission === 'granted') {
            hideBlockGuide();
            var recheckBtn = document.getElementById('jpMealPushRecheck');
            if (recheckBtn) {
                recheckBtn.disabled = true;
            }
            return subscribeAfterPermission('granted')
                .catch(function (err) {
                    showGateError(err.message || 'Không đăng ký được push.');
                })
                .finally(function () {
                    if (recheckBtn) {
                        recheckBtn.disabled = false;
                    }
                });
        }

        if (permission === 'default') {
            hideBlockGuide();
            onEnableButtonClick();
            return Promise.resolve();
        }

        showGateError(
            isChromium
                ? 'Chrome vẫn đang Block. Mở điều chỉnh quyền bên trái địa chỉ → Notifications → Allow.'
                : 'Vẫn đang Block — đổi Notifications sang Allow trong cài đặt trang.',
        );
        return Promise.resolve();
    }

    function disableMealPush() {
        return getBrowserSubscription().then(function (subscription) {
            var tasks = [postJson(cfg.unsubscribeUrl, {
                endpoint: subscription ? subscription.endpoint : '',
                clear_consent: true,
            })];
            if (subscription) {
                tasks.push(subscription.unsubscribe());
            }
            return Promise.all(tasks);
        }).then(function () {
            lsRemove(LS_SUBSCRIBED);
            hideSuccessBanner();
            permissionWatchStarted = false;
            showOptionalGate();
            updateGateForPermission();
        });
    }

    function sendTestPush() {
        if (!cfg.testUrl) {
            return Promise.reject(new Error('Chỉ admin mới gửi thử được.'));
        }
        return postJson(cfg.testUrl, {}).then(function (data) {
            showSuccessBanner(data.message || 'Đã gửi thông báo thử đặt cơm.');
        }).catch(function (err) {
            var msg = (err && err.message) || '';
            if (msg.indexOf('Chưa đăng ký') !== -1 || msg.indexOf('bật lại') !== -1) {
                lsRemove(LS_SUBSCRIBED);
                hideSuccessBanner();
                showMandatoryGate();
                updateGateForPermission();
            }
            throw err;
        });
    }

    function sendTestAnnouncementPush() {
        if (!cfg.announcementTestUrl) {
            return Promise.reject(new Error('Chỉ admin mới gửi thử được.'));
        }
        return postJson(cfg.announcementTestUrl, {}).then(function (data) {
            showSuccessBanner(data.message || 'Đã gửi thông báo thử công ty.');
        }).catch(function (err) {
            var msg = (err && err.message) || '';
            if (msg.indexOf('Chưa đăng ký') !== -1 || msg.indexOf('bật lại') !== -1) {
                lsRemove(LS_SUBSCRIBED);
                hideSuccessBanner();
                showMandatoryGate();
                updateGateForPermission();
            }
            throw err;
        });
    }

    function refreshPushUI() {
        if (!supportsPush()) {
            hideMandatoryGate();
            return Promise.resolve();
        }

        applyBrowserGuideCopy();

        return Promise.all([getBrowserSubscription(), fetchServerStatus()]).then(function (results) {
            var browserSub = results[0];
            var serverStatus = results[1];
            var permission = Notification.permission;

            if (!serverStatus.subscribed && lsGet(LS_SUBSCRIBED) === '1') {
                lsRemove(LS_SUBSCRIBED);
            }

            if (serverStatus.consent_recorded) {
                hideMandatoryGate();
                if (isFullySubscribed(browserSub, serverStatus, permission)) {
                    showSuccessBanner('Đã đăng ký push — dùng nút bên phải để gửi thử.');
                } else if (permission === 'granted' && browserSub && !serverStatus.subscribed) {
                    return saveSubscriptionOnServer(browserSub).then(function () {
                        showSuccessBanner('Đã đồng bộ đăng ký push lên server.');
                    }).catch(function () {});
                }
                return;
            }

            if (isFullySubscribed(browserSub, serverStatus, permission)) {
                return recordConsentOnServer('granted', true).then(function () {
                    hideMandatoryGate();
                    showSuccessBanner('Đã đăng ký push — dùng nút bên phải để gửi thử.');
                });
            }

            showOptionalGate();
            updateGateForPermission();
        }).catch(function () {
            showOptionalGate();
            updateGateForPermission();
        });
    }

    function bindPushUI() {
        var enableBtn = document.getElementById('jpMealPushEnable');
        var dismissBtn = document.getElementById('jpMealPushDismiss');
        var skipBtn = document.getElementById('jpMealPushSkip');
        var recheckBtn = document.getElementById('jpMealPushRecheck');
        var reloadBtn = document.getElementById('jpMealPushReload');
        var testBtn = document.getElementById('jpMealPushTest');
        var annTestBtn = document.getElementById('jpAnnPushTest');
        var disableBtn = document.getElementById('jpMealPushDisable');

        applyBrowserGuideCopy();

        if (enableBtn) {
            enableBtn.addEventListener('click', onEnableButtonClick);
        }

        if (dismissBtn) {
            dismissBtn.addEventListener('click', dismissPushGate);
        }

        if (skipBtn) {
            skipBtn.addEventListener('click', dismissPushGate);
        }

        if (recheckBtn) {
            recheckBtn.addEventListener('click', function () {
                recheckAfterUnblock();
            });
        }

        if (reloadBtn) {
            reloadBtn.addEventListener('click', function () {
                window.location.reload();
            });
        }

        if (testBtn) {
            testBtn.addEventListener('click', function () {
                testBtn.disabled = true;
                sendTestPush()
                    .catch(function (err) {
                        window.alert(err.message || 'Không gửi được thông báo thử đặt cơm.');
                    })
                    .finally(function () {
                        testBtn.disabled = false;
                    });
            });
        }

        if (annTestBtn) {
            annTestBtn.addEventListener('click', function () {
                annTestBtn.disabled = true;
                sendTestAnnouncementPush()
                    .catch(function (err) {
                        window.alert(err.message || 'Không gửi được thông báo thử.');
                    })
                    .finally(function () {
                        annTestBtn.disabled = false;
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
