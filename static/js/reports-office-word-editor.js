(function () {
    'use strict';

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function parseCkUploadResponse(xhr, fallback) {
        var text = (xhr && xhr.responseText) || fallback || '';
        text = String(text).trim().replace(/^\uFEFF/, '');
        if (!text) {
            return null;
        }
        return JSON.parse(text);
    }

    if (window.CKEDITOR) {
        CKEDITOR.config.versionCheck = false;

        CKEDITOR.on('instanceCreated', function (ev) {
            ev.editor.on('fileUploadRequest', function (evt) {
                var xhr = evt.data.fileLoader.xhr;
                var token = getCsrfToken();
                if (token) {
                    xhr.setRequestHeader('X-CSRFToken', token);
                }
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                var loader = evt.data.fileLoader;
                var dateInput = document.getElementById('id_report_date')
                    || document.querySelector('input[name="report_date"]');
                if (loader && dateInput && dateInput.value) {
                    var join = loader.uploadUrl.indexOf('?') >= 0 ? '&' : '?';
                    loader.uploadUrl = loader.uploadUrl + join + 'report_date=' + encodeURIComponent(dateInput.value);
                }
                var periodInput = document.querySelector('input[name="period"]');
                if (loader && periodInput && periodInput.value) {
                    var joinP = loader.uploadUrl.indexOf('?') >= 0 ? '&' : '?';
                    loader.uploadUrl = loader.uploadUrl + joinP + 'period=' + encodeURIComponent(periodInput.value);
                }
            });

            ev.editor.on('fileUploadResponse', function (evt) {
                var loader = evt.data.fileLoader;
                var xhr = loader && loader.xhr;
                if (!xhr) {
                    evt.cancel();
                    evt.data.message = 'Phản hồi upload không hợp lệ.';
                    return;
                }
                if (xhr.status >= 400) {
                    evt.cancel();
                    var message = 'Lỗi tải ảnh lên (HTTP ' + xhr.status + ').';
                    try {
                        var parsedErr = parseCkUploadResponse(xhr, evt.data.response);
                        if (parsedErr && parsedErr.error && parsedErr.error.message) {
                            message = parsedErr.error.message;
                        }
                    } catch (err) {}
                    evt.data.message = message;
                    return;
                }
                try {
                    var data = parseCkUploadResponse(xhr, evt.data.response);
                    if (!data) {
                        evt.cancel();
                        evt.data.message = 'Phản hồi upload trống.';
                        return;
                    }
                    if (data.error && data.error.message) {
                        evt.cancel();
                        evt.data.message = data.error.message;
                        return;
                    }
                    if (data.url) {
                        evt.data.url = data.url;
                        if (data.fileName) {
                            evt.data.fileName = data.fileName;
                        }
                        return;
                    }
                    evt.cancel();
                    evt.data.message = 'Phản hồi upload thiếu URL ảnh.';
                } catch (err) {
                    evt.cancel();
                    evt.data.message = 'Phản hồi upload không hợp lệ.';
                }
            });
        });
    }

    window.JP_WORD_EDITOR_CFG = window.JP_WORD_EDITOR_CFG || {
        versionCheck: false,
        toolbar: [
            { name: 'document', items: ['Maximize', 'ShowBlocks', 'Source'] },
            { name: 'clipboard', items: ['Undo', 'Redo'] },
            { name: 'editing', items: ['Cut', 'Copy', 'Paste', 'PasteText', 'PasteFromWord', 'CopyFormatting'] },
            { name: 'find', items: ['Find', 'Replace', '-', 'SelectAll'] },
            '/',
            { name: 'basicstyles', items: ['Bold', 'Italic', 'Underline', 'Strike', 'Subscript', 'Superscript', '-', 'RemoveFormat'] },
            { name: 'paragraph', items: ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', 'Blockquote'] },
            { name: 'align', items: ['JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock'] },
            { name: 'links', items: ['Link', 'Unlink', 'Anchor'] },
            { name: 'insert', items: ['Image', 'Table', 'HorizontalRule', 'SpecialChar'] },
            '/',
            { name: 'styles', items: ['Format', 'Styles'] },
        ],
        stylesSet: [
            { name: 'Đoạn văn', element: 'p' },
            { name: 'Tiêu đề 1', element: 'h1' },
            { name: 'Tiêu đề 2', element: 'h2' },
            { name: 'Tiêu đề 3', element: 'h3' },
            { name: 'Tiêu đề 4', element: 'h4' },
            { name: 'Trích dẫn', element: 'blockquote' },
            { name: 'Mã nguồn', element: 'pre' },
        ],
        format_tags: 'p;h1;h2;h3;h4;h5;h6;pre;address',
        width: '100%',
        height: 580,
        language: 'vi',
        extraPlugins: 'widget,uploadwidget,uploadimage,image2,tableresize,tabletools,tableselection,liststyle,pastefromword,copyformatting,stylescombo,autogrow',
        removePlugins: 'exportpdf,image',
        image2_disableResizer: false,
        image2_prefillDimensions: true,
        clipboard_handleImages: true,
        allowedContent: true,
        forcePasteAsPlainText: false,
        contentsCss: ['/static/css/reports-office-contents.css?v=20260628b'],
    };

    function initImageWidgets(editor) {
        if (!editor || !editor.widgets) {
            return;
        }
        try {
            editor.widgets.checkWidgets({ initOnlyNew: true });
        } catch (err) {
            console.warn('JP image widgets:', err);
        }
    }

    function bindImageWidgetHooks(editor) {
        if (!editor || editor._.jpImageWidgetsBound) {
            return;
        }
        editor._.jpImageWidgetsBound = true;

        editor.on('change', function () {
            window.setTimeout(function () {
                initImageWidgets(editor);
            }, 0);
        });

        editor.on('fileUploadResponse', function () {
            window.setTimeout(function () {
                initImageWidgets(editor);
            }, 30);
        });

        editor.on('afterPaste', function () {
            window.setTimeout(function () {
                initImageWidgets(editor);
            }, 30);
        });
    }

    function isVanbanViewportEditor(editor) {
        if (!editor || !editor.element) {
            return false;
        }
        const el = editor.element.$;
        return !!(el && el.closest && el.closest('.jp-vanban-viewport'));
    }

    function applyWordPageLayout(editor) {
        if (!editor || !editor.editable) return;
        try {
            const doc = editor.document;
            if (!doc || !doc.$) return;
            const $ = doc.$;
            const $html = $('html');
            const $body = $('body');
            const inVanban = isVanbanViewportEditor(editor);
            if ($html.length) {
                $html.css({
                    background: '#ffffff',
                    minHeight: inVanban ? '100%' : '100%',
                    height: inVanban ? '100%' : 'auto',
                    overflow: inVanban ? 'hidden' : 'visible',
                });
            }
            if ($body.length) {
                const bodyStyles = {
                    width: '100%',
                    maxWidth: '21cm',
                    margin: '0 auto',
                    padding: '2.54cm 2cm 2.54cm 2.5cm',
                    background: '#ffffff',
                    boxShadow: 'none',
                    border: '1px solid #e5e7eb',
                    fontFamily: "'Times New Roman', Times, serif",
                    fontSize: '14pt',
                    lineHeight: '1.5',
                    color: '#000000',
                    boxSizing: 'border-box',
                };
                if (inVanban) {
                    Object.assign(bodyStyles, {
                        minHeight: '100%',
                        height: 'auto',
                        overflowY: 'auto',
                        overflowX: 'hidden',
                        WebkitOverflowScrolling: 'touch',
                    });
                } else {
                    Object.assign(bodyStyles, {
                        minHeight: '29.7cm',
                        height: 'auto',
                        margin: '16px auto 24px',
                    });
                }
                $body.css(bodyStyles);
            }
        } catch (err) {
            console.warn('JP Word layout:', err);
        }
    }

    function bindVanbanIframeScroll(editor) {
        if (!isVanbanViewportEditor(editor) || editor._.jpVanbanScrollBound) {
            return;
        }
        editor._.jpVanbanScrollBound = true;

        const viewport = document.querySelector('.jp-vanban-viewport');
        const iframe = editor.container.$.querySelector('iframe.cke_wysiwyg_frame');
        if (!iframe || !iframe.contentWindow) {
            return;
        }

        function scrollEditable(deltaY) {
            const body = iframe.contentDocument && iframe.contentDocument.body;
            if (!body) {
                return false;
            }
            const maxScroll = body.scrollHeight - body.clientHeight;
            if (maxScroll <= 0) {
                return false;
            }
            const next = Math.max(0, Math.min(maxScroll, body.scrollTop + deltaY));
            if (next === body.scrollTop) {
                return false;
            }
            body.scrollTop = next;
            return true;
        }

        function onWheel(e) {
            if (scrollEditable(e.deltaY)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }

        let touchStartY = 0;

        function onTouchStart(e) {
            if (e.touches && e.touches.length) {
                touchStartY = e.touches[0].clientY;
            }
        }

        function onTouchMove(e) {
            if (!e.touches || !e.touches.length) {
                return;
            }
            const deltaY = touchStartY - e.touches[0].clientY;
            touchStartY = e.touches[0].clientY;
            if (scrollEditable(deltaY)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }

        iframe.contentWindow.addEventListener('wheel', onWheel, { passive: false });

        const iframeDoc = iframe.contentDocument;
        if (iframeDoc) {
            iframeDoc.addEventListener('touchstart', onTouchStart, { passive: true });
            iframeDoc.addEventListener('touchmove', onTouchMove, { passive: false });
        }

        if (viewport && !viewport.dataset.jpVanbanWheelBound) {
            viewport.dataset.jpVanbanWheelBound = '1';
            viewport.addEventListener('wheel', onWheel, { passive: false });
            viewport.addEventListener('touchstart', onTouchStart, { passive: true });
            viewport.addEventListener('touchmove', onTouchMove, { passive: false });
        }
    }

    function resizeEditor(editor) {
        if (!editor || !editor.resize) return;
        const viewport = document.querySelector('.jp-vanban-viewport');
        if (viewport && isVanbanViewportEditor(editor)) {
            const topBar = editor.container.$.querySelector('.cke_top');
            const topH = topBar ? topBar.offsetHeight : 0;
            const contentH = Math.max(240, viewport.clientHeight - topH - 4);
            editor.resize('100%', contentH);
        } else {
            editor.resize('100%', 580);
        }
        applyWordPageLayout(editor);
        bindVanbanIframeScroll(editor);
    }

    function resolveUploadUrl() {
        if (window.JP_REPORTS_CK_UPLOAD_URL) {
            return window.JP_REPORTS_CK_UPLOAD_URL;
        }
        const uploadEl = document.querySelector('[data-ck-upload-url]');
        return uploadEl && uploadEl.dataset.ckUploadUrl ? uploadEl.dataset.ckUploadUrl : '';
    }

    function appendReportDateToUploadUrl(uploadUrl) {
        if (!uploadUrl) {
            return '';
        }
        const dateInput = document.getElementById('id_report_date')
            || document.querySelector('input[name="report_date"]');
        let result = uploadUrl;
        if (dateInput && dateInput.value) {
            const join = result.indexOf('?') >= 0 ? '&' : '?';
            result = result + join + 'report_date=' + encodeURIComponent(dateInput.value);
        }
        const periodInput = document.querySelector('input[name="period"]');
        if (periodInput && periodInput.value) {
            const joinP = result.indexOf('?') >= 0 ? '&' : '?';
            result = result + joinP + 'period=' + encodeURIComponent(periodInput.value);
        }
        return result;
    }

    function dataUrlToBlob(dataUrl) {
        const parts = dataUrl.split(',');
        if (parts.length < 2) {
            throw new Error('Ảnh dán không hợp lệ');
        }
        const meta = parts[0];
        const raw = atob(parts[1]);
        const mime = (meta.match(/data:([^;]+)/i) || [])[1] || 'image/png';
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i += 1) {
            bytes[i] = raw.charCodeAt(i);
        }
        return new Blob([bytes], { type: mime });
    }

    function uploadImageBlob(blob, fileName) {
        const uploadUrl = appendReportDateToUploadUrl(resolveUploadUrl());
        if (!uploadUrl) {
            return Promise.reject(new Error('Chưa cấu hình upload ảnh báo cáo.'));
        }
        const formData = new FormData();
        formData.append('upload', blob, fileName || 'paste.png');
        return fetch(uploadUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: formData,
        }).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok || !data.url) {
                    const msg = (data.error && data.error.message) || ('HTTP ' + resp.status);
                    throw new Error(msg);
                }
                return data.url;
            });
        });
    }

    function editorHasDataUrlImages(editor) {
        return /<img\b[^>]*\bsrc=["']data:image\//i.test(editor.getData() || '');
    }

    function uploadDataUrlImagesInEditor(editor) {
        const html = editor.getData() || '';
        const pattern = /<img\b([^>]*?)\bsrc=["'](data:image\/[^"']+)["']([^>]*)>/gi;
        const tasks = [];
        const replacements = [];
        let match;
        while ((match = pattern.exec(html)) !== null) {
            const fullTag = match[0];
            const dataUrl = match[2];
            const ext = (dataUrl.match(/^data:image\/([a-z0-9+.-]+)/i) || [])[1] || 'png';
            const fileName = 'paste.' + ext.replace('jpeg', 'jpg').replace('x-ms-bmp', 'bmp');
            tasks.push(
                uploadImageBlob(dataUrlToBlob(dataUrl), fileName).then(function (url) {
                    replacements.push({ from: fullTag, to: fullTag.replace(dataUrl, url) });
                }),
            );
        }
        if (!tasks.length) {
            return Promise.resolve();
        }
        return Promise.all(tasks).then(function () {
            let next = html;
            replacements.forEach(function (item) {
                next = next.split(item.from).join(item.to);
            });
            editor.setData(next);
            editor.updateElement();
        });
    }

    function syncAllEditorsToTextarea() {
        Object.keys(CKEDITOR.instances || {}).forEach(function (key) {
            CKEDITOR.instances[key].updateElement();
        });
    }

    function bindReportFormImageUpload() {
        const form = document.getElementById('office-report-form');
        if (!form || form.dataset.jpCkImageSubmitBound === '1') {
            return;
        }
        form.dataset.jpCkImageSubmitBound = '1';
        form.addEventListener('submit', function (evt) {
            syncAllEditorsToTextarea();
            const editor = Object.keys(CKEDITOR.instances || {})
                .map(function (key) { return CKEDITOR.instances[key]; })
                .find(function (inst) { return inst && inst.element; });
            if (!editor || !editorHasDataUrlImages(editor)) {
                return;
            }
            evt.preventDefault();
            uploadDataUrlImagesInEditor(editor).then(function () {
                syncAllEditorsToTextarea();
                form.submit();
            }).catch(function (err) {
                window.alert('Không tải được ảnh dán trong văn bản: ' + (err.message || err));
            });
        });
    }

    function isMobileViewport() {
        return window.matchMedia('(max-width: 767.98px)').matches;
    }

    function getRibbonToggleButton() {
        return document.getElementById('jpCkRibbonToggle');
    }

    function getWordStudio() {
        return document.querySelector('.jp-vanban-viewport .jp-word-studio');
    }

    function setRibbonCollapsed(collapsed) {
        const studio = getWordStudio();
        const toggle = getRibbonToggleButton();
        if (!studio || !toggle) {
            return;
        }
        studio.classList.toggle('is-ck-ribbon-collapsed', collapsed);
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        const label = toggle.querySelector('.jp-ck-ribbon-toggle-label');
        if (label) {
            label.textContent = collapsed ? 'Mở thanh công cụ' : 'Thu gọn công cụ';
        }
        const icon = toggle.querySelector('i');
        if (icon) {
            icon.className = collapsed
                ? 'bi bi-arrows-angle-expand'
                : 'bi bi-arrows-angle-contract';
        }
        Object.keys(CKEDITOR.instances || {}).forEach(function (key) {
            resizeEditor(CKEDITOR.instances[key]);
        });
    }

    function syncRibbonToggleVisibility() {
        const toggle = getRibbonToggleButton();
        const studio = getWordStudio();
        if (!toggle || !studio) {
            return;
        }
        const mobile = isMobileViewport();
        toggle.hidden = !mobile;
        if (!mobile) {
            studio.classList.remove('is-ck-ribbon-collapsed');
            toggle.setAttribute('aria-expanded', 'true');
            return;
        }
        if (!toggle.dataset.jpRibbonBound) {
            return;
        }
        const collapsed = studio.classList.contains('is-ck-ribbon-collapsed');
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    function bindMobileRibbonToggle() {
        const toggle = getRibbonToggleButton();
        const studio = getWordStudio();
        if (!toggle || !studio || toggle.dataset.jpRibbonBound === '1') {
            return;
        }
        toggle.dataset.jpRibbonBound = '1';
        if (isMobileViewport()) {
            studio.classList.add('is-ck-ribbon-collapsed');
            toggle.setAttribute('aria-expanded', 'false');
            const label = toggle.querySelector('.jp-ck-ribbon-toggle-label');
            if (label) {
                label.textContent = 'Mở thanh công cụ';
            }
        }
        toggle.hidden = !isMobileViewport();
        toggle.addEventListener('click', function () {
            const collapsed = studio.classList.contains('is-ck-ribbon-collapsed');
            setRibbonCollapsed(!collapsed);
        });
    }

    function buildConfig() {
        const cfg = Object.assign({}, window.JP_WORD_EDITOR_CFG);
        const inVanban = !!document.querySelector('.jp-vanban-viewport');
        if (inVanban) {
            cfg.extraPlugins = (cfg.extraPlugins || '')
                .split(',')
                .map(function (p) { return p.trim(); })
                .filter(function (p) { return p && p !== 'autogrow'; })
                .join(',');
            cfg.height = 320;
        }
        const ltsKey = window.JP_CKEDITOR_LTS_LICENSE || '';
        if (ltsKey) {
            cfg.licenseKey = ltsKey;
        }
        const uploadUrl = resolveUploadUrl();
        if (uploadUrl) {
            cfg.filebrowserUploadUrl = uploadUrl;
            cfg.filebrowserBrowseUrl = '';
            cfg.filebrowserImageUploadUrl = uploadUrl;
            cfg.imageUploadUrl = uploadUrl;
        }
        return cfg;
    }

    function initWordEditor() {
        const studio = document.querySelector('.jp-word-studio[data-word-textarea]');
        if (!studio || !window.CKEDITOR) {
            return;
        }
        const fieldId = studio.dataset.wordTextarea;
        const textarea = document.getElementById(fieldId);
        if (!textarea) {
            return;
        }

        if (CKEDITOR.instances[fieldId]) {
            const existing = CKEDITOR.instances[fieldId];
            if (document.getElementById('office-report-form')?.dataset.reportLocked) {
                existing.setReadOnly(true);
            }
            bindMobileRibbonToggle();
            syncRibbonToggleVisibility();
            resizeEditor(existing);
            bindImageWidgetHooks(existing);
            initImageWidgets(existing);
            window.JP_WORD_EDITOR_READY = true;
            return;
        }

        if (window.JP_WORD_EDITOR_READY) {
            return;
        }

        studio.classList.add('is-loading');
        const editor = CKEDITOR.replace(fieldId, buildConfig());

        editor.on('change', function () {
            window.setTimeout(function () {
                applyWordPageLayout(editor);
                initImageWidgets(editor);
            }, 0);
        });

        editor.on('contentDom', function () {
            applyWordPageLayout(editor);
            bindVanbanIframeScroll(editor);
            initImageWidgets(editor);
        });

        editor.on('instanceReady', function () {
            studio.classList.remove('is-loading');
            studio.classList.add('is-ready');
            window.JP_WORD_EDITOR_READY = true;
            bindImageWidgetHooks(editor);
            bindMobileRibbonToggle();
            syncRibbonToggleVisibility();
            resizeEditor(editor);
            initImageWidgets(editor);
            if (document.getElementById('office-report-form')?.dataset.reportLocked) {
                editor.setReadOnly(true);
            }
        });
    }

    function boot() {
        bindReportFormImageUpload();
        const wordTab = document.getElementById('vanban-tab');
        const wordPane = document.getElementById('vanban-pane');
        const vanbanViewport = document.querySelector('.jp-vanban-viewport');

        function bootWordEditor() {
            window.setTimeout(function () {
                initWordEditor();
                Object.keys(CKEDITOR.instances || {}).forEach(function (key) {
                    resizeEditor(CKEDITOR.instances[key]);
                });
            }, 60);
        }

        if (wordTab) {
            wordTab.addEventListener('shown.bs.tab', bootWordEditor);
        }
        if (wordPane && wordPane.classList.contains('show') && wordPane.classList.contains('active')) {
            bootWordEditor();
        } else if (vanbanViewport) {
            bootWordEditor();
        }

        window.addEventListener('resize', function () {
            syncRibbonToggleVisibility();
            Object.keys(CKEDITOR.instances || {}).forEach(function (key) {
                resizeEditor(CKEDITOR.instances[key]);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
