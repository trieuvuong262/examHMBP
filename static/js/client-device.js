/**
 * Gửi tên máy + IP LAN lên server (cookie + hidden field) cho nhật ký thao tác.
 * IT có thể preset tên máy Windows: localStorage.setItem('jp_device_name', 'TEN-MAY');
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

            setTimeout(function () { finish(''); }, 3500);

            try {
                var pc = new RTCPeerConnection({ iceServers: [] });
                pc.createDataChannel('jp-audit');
                pc.onicecandidate = function (event) {
                    if (!event || !event.candidate || !event.candidate.candidate) return;
                    var match = /([0-9]{1,3}(?:\.[0-9]{1,3}){3})/.exec(event.candidate.candidate);
                    if (!match) return;
                    var ip = match[1];
                    if (isPrivateIp(ip)) {
                        pc.close();
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

    function resolveHostname(localIp) {
        var stored = localStorage.getItem(STORAGE_KEY);
        if (stored && stored.trim()) {
            return stored.trim().slice(0, 128);
        }
        if (localIp) {
            var suffix = localIp.split('.').pop();
            var autoName = 'PC-' + suffix;
            localStorage.setItem(STORAGE_KEY, autoName);
            return autoName;
        }
        return '';
    }

    function publishDeviceInfo(localIp, hostname) {
        setCookie('jp_local_ip', localIp);
        setCookie('jp_hostname', hostname);
        window.__jpClientDevice = {
            localIp: localIp,
            hostname: hostname,
        };
    }

    function ensureHiddenInput(form, name, value) {
        if (!value) return;
        var input = form.querySelector('input[name="' + name + '"]');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            form.appendChild(input);
        }
        input.value = value;
    }

    function attachFormHandlers() {
        document.querySelectorAll('form').forEach(function (form) {
            if (form.dataset.jpDeviceBound === '1') return;
            form.dataset.jpDeviceBound = '1';
            form.addEventListener('submit', function () {
                var info = window.__jpClientDevice || {};
                ensureHiddenInput(form, 'client_local_ip', info.localIp || '');
                ensureHiddenInput(form, 'client_hostname', info.hostname || '');
            });
        });
    }

    detectLocalIp().then(function (localIp) {
        var hostname = resolveHostname(localIp);
        publishDeviceInfo(localIp, hostname);
        attachFormHandlers();
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachFormHandlers);
    } else {
        attachFormHandlers();
    }
})();
