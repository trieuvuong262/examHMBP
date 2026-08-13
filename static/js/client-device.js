/**
 * Gửi tên máy + IP LAN lên server (cookie + hidden field) cho nhật ký thao tác.
 * IT có thể đặt tên máy: localStorage.setItem('jp_device_name', 'TEN-MAY');
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'jp_device_name';
    var COOKIE_DAYS = 7;

    function setCookie(name, value) {
        if (!value) return;
        var maxAge = COOKIE_DAYS * 86400;
        document.cookie = name + '=' + encodeURIComponent(value)
            + '; path=/; max-age=' + maxAge + '; SameSite=Lax';
    }

    function readCookie(name) {
        var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[1]) : '';
    }

    function isPrivateIp(ip) {
        if (!ip) return false;
        if (ip.indexOf('192.168.') === 0) return true;
        if (ip.indexOf('10.') === 0) return true;
        return /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(ip);
    }

    function detectLocalIp() {
        return new Promise(function (resolve) {
            var done = false;
            var finish = function (value) {
                if (done) return;
                done = true;
                resolve(value || '');
            };

            setTimeout(function () { finish(''); }, 4000);

            try {
                var pc = new RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
                });
                pc.createDataChannel('jp-audit');
                pc.onicecandidate = function (event) {
                    if (!event || !event.candidate || !event.candidate.candidate) return;
                    var match = /([0-9]{1,3}(?:\.[0-9]{1,3}){3})/.exec(event.candidate.candidate);
                    if (!match) return;
                    var ip = match[1];
                    if (isPrivateIp(ip)) {
                        try { pc.close(); } catch (e) {}
                        finish(ip);
                    }
                };
                pc.createOffer()
                    .then(function (offer) { return pc.setLocalDescription(offer); })
                    .catch(function () { finish(''); });
            } catch (err) {
                finish('');
            }
        });
    }

    function guessHostnameFromUa() {
        var ua = navigator.userAgent || '';
        if (ua.indexOf('Windows') !== -1) return 'Windows';
        if (ua.indexOf('Macintosh') !== -1 || ua.indexOf('Mac OS') !== -1) return 'Mac';
        if (ua.indexOf('Android') !== -1) return 'Android';
        if (ua.indexOf('iPhone') !== -1 || ua.indexOf('iPad') !== -1) return 'iPhone';
        if (ua.indexOf('Linux') !== -1) return 'Linux';
        return '';
    }

    function resolveHostname(localIp) {
        var stored = localStorage.getItem(STORAGE_KEY);
        if (stored && stored.trim()) {
            return stored.trim().slice(0, 128);
        }
        if (localIp) {
            return ('PC-' + localIp.split('.').pop()).slice(0, 128);
        }
        return guessHostnameFromUa();
    }

    function restoreDeviceInfo() {
        var localIp = readCookie('jp_local_ip');
        var hostname = resolveHostname(localIp);
        if (!localIp) {
            var cookieHost = readCookie('jp_hostname');
            if (cookieHost && !localStorage.getItem(STORAGE_KEY)) {
                hostname = cookieHost;
            }
        }
        publishDeviceInfo(localIp, hostname);
    }

    function publishDeviceInfo(localIp, hostname) {
        setCookie('jp_local_ip', localIp);
        setCookie('jp_hostname', hostname);
        window.__jpClientDevice = {
            localIp: localIp || '',
            hostname: hostname || '',
        };
    }

    function ensureHiddenInput(form, name, value) {
        var input = form.querySelector('input[name="' + name + '"]');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            form.appendChild(input);
        }
        input.value = value || '';
    }

    function applyDeviceToForm(form) {
        var info = window.__jpClientDevice || {};
        ensureHiddenInput(form, 'client_local_ip', info.localIp || '');
        ensureHiddenInput(form, 'client_hostname', info.hostname || '');
    }

    function attachFormHandlers() {
        document.querySelectorAll('form').forEach(function (form) {
            if (form.dataset.jpDeviceBound === '1') return;
            form.dataset.jpDeviceBound = '1';
            form.addEventListener('submit', function (e) {
                var info = window.__jpClientDevice || {};
                if ((!info.localIp && !info.hostname) && window.__jpDeviceDetectPromise) {
                    e.preventDefault();
                    window.__jpDeviceDetectPromise.then(function () {
                        applyDeviceToForm(form);
                        form.submit();
                    });
                    return;
                }
                applyDeviceToForm(form);
            });
        });
    }

    // Khôi phục cookie phiên trước ngay lập tức (ưu tiên tên IT đặt trong localStorage)
    restoreDeviceInfo();

    window.__jpDeviceDetectPromise = detectLocalIp().then(function (localIp) {
        var hostname = resolveHostname(localIp);
        publishDeviceInfo(localIp, hostname);
        attachFormHandlers();
        return window.__jpClientDevice;
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachFormHandlers);
    } else {
        attachFormHandlers();
    }

    // --- Ghi nút vừa bấm vào cookie/hidden field cho nhật ký thao tác ---
    var CLICK_COOKIE = 'jp_clicked_btn';
    var CLICK_FIELD = 'jp_clicked_button';
    var CLICK_COOKIE_SECONDS = 30;

    function setClickCookie(value) {
        if (!value) return;
        document.cookie = CLICK_COOKIE + '=' + encodeURIComponent(value)
            + '; path=/; max-age=' + CLICK_COOKIE_SECONDS + '; SameSite=Lax';
    }

    function buttonLabel(el) {
        if (!el) return '';
        var aria = (el.getAttribute('aria-label') || '').trim();
        if (aria) return aria.slice(0, 80);
        var title = (el.getAttribute('title') || '').trim();
        if (title) return title.slice(0, 80);
        if (el.matches && el.matches('input')) {
            return ((el.value || el.getAttribute('name') || '') + '').trim().slice(0, 80);
        }
        var text = ((el.innerText || el.textContent || '') + '').replace(/\s+/g, ' ').trim();
        if (text) return text.slice(0, 80);
        return ((el.getAttribute('name') || el.getAttribute('value') || '') + '').trim().slice(0, 80);
    }

    function closestClickable(target) {
        if (!target || !target.closest) return null;
        return target.closest('button, input[type="submit"], input[type="button"], input[type="image"], a.btn, [role="button"], .btn');
    }

    function isNavigatingClick(el) {
        if (!el) return false;
        if (el.matches('a[href]')) {
            var href = (el.getAttribute('href') || '').trim();
            if (!href || href === '#' || href.indexOf('javascript:') === 0) return false;
            if (el.getAttribute('data-bs-toggle') || el.getAttribute('data-toggle')) return false;
            return true;
        }
        if (el.matches('input[type="submit"], input[type="image"]')) return true;
        if (el.matches('button')) {
            var type = (el.getAttribute('type') || 'submit').toLowerCase();
            if (type === 'reset') return false;
            if (el.getAttribute('data-bs-toggle') || el.getAttribute('data-toggle')) return false;
            return type === 'submit' || !!el.getAttribute('formaction') || !!el.closest('form');
        }
        if (el.matches('input[type="button"]') && el.getAttribute('formaction')) return true;
        return false;
    }

    function rememberClickedButton(el) {
        var label = buttonLabel(el);
        if (!label) return;
        window.__jpLastClickedButton = label;
        setClickCookie(label);
        var form = el.closest && el.closest('form');
        if (form) {
            ensureHiddenInput(form, CLICK_FIELD, label);
        }
    }

    document.addEventListener('click', function (event) {
        var el = closestClickable(event.target);
        if (!el || !isNavigatingClick(el)) return;
        rememberClickedButton(el);
    }, true);

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || form.tagName !== 'FORM') return;
        var label = window.__jpLastClickedButton || '';
        if (!label) {
            var submitter = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
            label = buttonLabel(submitter);
        }
        if (label) {
            ensureHiddenInput(form, CLICK_FIELD, label);
            setClickCookie(label);
        }
        applyDeviceToForm(form);
    }, true);
})();
