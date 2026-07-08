/**
 * Overlay loading khi gửi báo cáo (VP ngày/tuần, SX).
 * Chống spam: khóa toàn bộ nút gửi ngay khi bấm, chặn gửi trùng,
 * chỉ mở lại sau khi thất bại + cooldown ngắn.
 */
(function () {
    'use strict';

    var overlay = document.getElementById('jp-report-submit-loading');
    if (!overlay) return;

    var msgEl = overlay.querySelector('[data-loading-message]');
    var successOverlay = document.getElementById('jp-report-submit-success');
    var successCloseBtn = document.getElementById('jpReportSubmitSuccessCloseBtn');
    var errorOverlay = document.getElementById('jp-report-submit-error');
    var errorCloseBtn = document.getElementById('jpReportSubmitErrorCloseBtn');

    // Gắn lên body để tránh bị filter/opacity/stacking của .container / CKEditor trên trang VP.
    [overlay, successOverlay, errorOverlay].forEach(function (el) {
        if (el && el.parentNode !== document.body) {
            document.body.appendChild(el);
        }
    });

    var submitting = false;
    var cooldownUntil = 0;
    var pendingRedirectUrl = '';
    var redirectTimer = null;
    var cooldownTimer = null;
    var COOLDOWN_MS = 2500;

    function submitSelector() {
        return 'button[type="submit"], input[type="submit"], .js-prod-submit-trigger, #prodSubmitConfirmBtn';
    }

    function syncCkEditor() {
        if (!window.CKEDITOR || !CKEDITOR.instances) return;
        Object.keys(CKEDITOR.instances).forEach(function (name) {
            if (Object.prototype.hasOwnProperty.call(CKEDITOR.instances, name)) {
                CKEDITOR.instances[name].updateElement();
            }
        });
    }

    function clearRedirectTimer() {
        if (redirectTimer) {
            window.clearTimeout(redirectTimer);
            redirectTimer = null;
        }
    }

    function clearCooldownTimer() {
        if (cooldownTimer) {
            window.clearTimeout(cooldownTimer);
            cooldownTimer = null;
        }
    }

    function goToPendingRedirect() {
        clearRedirectTimer();
        if (!pendingRedirectUrl) return;
        var url = pendingRedirectUrl;
        pendingRedirectUrl = '';
        window.location.href = url;
    }

    function lockAllSubmitButtons() {
        document.querySelectorAll(submitSelector()).forEach(function (btn) {
            btn.disabled = true;
            btn.setAttribute('aria-busy', 'true');
            btn.classList.add('jp-report-submit-locked');
        });
        document.body.classList.add('jp-report-submit-locked');
    }

    function unlockAllSubmitButtons() {
        document.querySelectorAll(submitSelector()).forEach(function (btn) {
            btn.disabled = false;
            btn.removeAttribute('aria-busy');
            btn.classList.remove('jp-report-submit-locked');
        });
        document.body.classList.remove('jp-report-submit-locked');
    }

    function canStartSubmit() {
        if (submitting) return false;
        if (Date.now() < cooldownUntil) return false;
        return true;
    }

    function beginSubmitLock() {
        submitting = true;
        clearCooldownTimer();
        lockAllSubmitButtons();
        document.body.classList.add('jp-report-submitting');
    }

    function endSubmitLockWithCooldown() {
        submitting = false;
        cooldownUntil = Date.now() + COOLDOWN_MS;
        clearCooldownTimer();
        cooldownTimer = window.setTimeout(function () {
            cooldownUntil = 0;
            unlockAllSubmitButtons();
        }, COOLDOWN_MS);
    }

    function show(message) {
        hideSuccess();
        hideError();
        if (msgEl && message) {
            msgEl.textContent = message;
        }
        overlay.hidden = false;
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('jp-report-submitting');
    }

    function hide() {
        overlay.hidden = true;
        overlay.setAttribute('aria-busy', 'false');
        document.body.classList.remove('jp-report-submitting');
    }

    function showSuccess(redirectUrl) {
        hide();
        hideError();
        // Giữ khóa nút sau thành công — không cho spam thêm trước khi chuyển trang.
        submitting = true;
        lockAllSubmitButtons();
        pendingRedirectUrl = redirectUrl || window.location.href;
        if (!successOverlay) {
            window.alert('Gửi báo cáo thành công.');
            goToPendingRedirect();
            return;
        }
        successOverlay.hidden = false;
        document.body.classList.add('jp-report-submit-success-open');
        if (successCloseBtn) {
            window.setTimeout(function () {
                successCloseBtn.focus();
            }, 50);
        }
        // Không tự tắt — người dùng bấm «Đã hiểu» mới chuyển trang.
        clearRedirectTimer();
    }

    function hideSuccess() {
        clearRedirectTimer();
        if (!successOverlay) return;
        successOverlay.hidden = true;
        document.body.classList.remove('jp-report-submit-success-open');
    }

    function showErrorModal() {
        hide();
        hideSuccess();
        if (!errorOverlay) {
            window.alert('Gửi báo cáo thất bại. Vui lòng kiểm tra kết nối mạng rồi gửi lại.');
            return;
        }
        errorOverlay.hidden = false;
        document.body.classList.add('jp-report-submit-error-open');
        if (errorCloseBtn) {
            window.setTimeout(function () {
                errorCloseBtn.focus();
            }, 50);
        }
    }

    function hideError() {
        if (!errorOverlay) return;
        errorOverlay.hidden = true;
        document.body.classList.remove('jp-report-submit-error-open');
    }

    function disableSubmitControls(form) {
        lockAllSubmitButtons();
        if (!form) return;
        form.querySelectorAll(submitSelector()).forEach(function (btn) {
            btn.disabled = true;
        });
    }

    function enableSubmitControls() {
        // Không mở lại ngay — phải hết cooldown sau lỗi mới mở.
        endSubmitLockWithCooldown();
    }

    function isReportSubmit(submitter, form) {
        if (!form) return false;
        if (submitter && submitter.getAttribute('name') === 'action') {
            return (submitter.getAttribute('value') || submitter.value) === 'submit';
        }
        if (submitter && submitter.type === 'submit') {
            var hidden = form.querySelector('input[name="action"][value="submit"]');
            if (hidden) return true;
        }
        return false;
    }

    function buildFormData(form, submitter) {
        var fd;
        try {
            fd = submitter ? new FormData(form, submitter) : new FormData(form);
        } catch (err) {
            fd = new FormData(form);
            if (submitter && submitter.name) {
                fd.append(submitter.name, submitter.value);
            }
        }
        if (!fd.get('action')) {
            var hiddenAction = form.querySelector('input[name="action"]');
            if (hiddenAction && hiddenAction.value) {
                fd.set('action', hiddenAction.value);
            } else {
                fd.set('action', 'submit');
            }
        }
        return fd;
    }

    function submitForm(form, submitter) {
        if (!form || !canStartSubmit()) return false;
        beginSubmitLock();
        syncCkEditor();
        show('Đang gửi báo cáo...');

        var fd = buildFormData(form, submitter || null);
        var url = form.getAttribute('action') || window.location.href;
        var method = (form.getAttribute('method') || 'POST').toUpperCase();

        fetch(url, {
            method: method,
            body: fd,
            credentials: 'same-origin',
            redirect: 'follow',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            showSuccess(resp.url || url);
        }).catch(function () {
            enableSubmitControls();
            showErrorModal();
        });
        return true;
    }

    function armForm(form) {
        if (!form || form.dataset.jpSubmitArmed === '1') return;
        form.dataset.jpSubmitArmed = '1';
        form.addEventListener('submit', function (ev) {
            if (!isReportSubmit(ev.submitter, form)) return;
            ev.preventDefault();
            ev.stopImmediatePropagation();
            submitForm(form, ev.submitter);
        }, true);
    }

    if (successCloseBtn) {
        successCloseBtn.addEventListener('click', goToPendingRedirect);
    }
    if (successOverlay) {
        successOverlay.addEventListener('click', function (ev) {
            if (ev.target === successOverlay || ev.target.classList.contains('jp-report-submit-backdrop')) {
                goToPendingRedirect();
            }
        });
    }
    if (errorCloseBtn) {
        errorCloseBtn.addEventListener('click', hideError);
    }
    if (errorOverlay) {
        errorOverlay.addEventListener('click', function (ev) {
            if (ev.target === errorOverlay || ev.target.classList.contains('jp-report-submit-backdrop')) {
                hideError();
            }
        });
    }

    document.querySelectorAll('form.js-report-submit-form').forEach(armForm);

    window.JpReportSubmitLoading = {
        show: show,
        hide: hide,
        armForm: armForm,
        syncCkEditor: syncCkEditor,
        disableSubmitControls: disableSubmitControls,
        enableSubmitControls: enableSubmitControls,
        submitForm: submitForm,
        canStartSubmit: canStartSubmit,
        showSuccess: showSuccess,
        showErrorModal: showErrorModal,
        hideError: hideError,
    };
})();
