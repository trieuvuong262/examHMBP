(function () {
    'use strict';

    if (window.CKEDITOR) {
        CKEDITOR.config.versionCheck = false;

        function getCsrfToken() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }

        CKEDITOR.on('instanceCreated', function (ev) {
            ev.editor.on('fileUploadRequest', function (evt) {
                var xhr = evt.data.fileLoader.xhr;
                var token = getCsrfToken();
                if (token) {
                    xhr.setRequestHeader('X-CSRFToken', token);
                }
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                var loader = evt.data.fileLoader;
                var dateInput = document.getElementById('id_report_date');
                if (loader && dateInput && dateInput.value) {
                    var join = loader.uploadUrl.indexOf('?') >= 0 ? '&' : '?';
                    loader.uploadUrl = loader.uploadUrl + join + 'report_date=' + encodeURIComponent(dateInput.value);
                }
            });

            ev.editor.on('fileUploadResponse', function (evt) {
                var xhr = evt.data.fileLoader.xhr;
                var response = evt.data.response;
                if (xhr.status >= 400) {
                    evt.cancel();
                    var message = 'Lỗi tải ảnh lên (HTTP ' + xhr.status + ').';
                    try {
                        var parsed = JSON.parse(response);
                        if (parsed.error && parsed.error.message) {
                            message = parsed.error.message;
                        }
                    } catch (err) {}
                    evt.data.message = message;
                    return;
                }
                try {
                    var data = JSON.parse(response);
                    if (!data.uploaded && data.url) {
                        data.uploaded = 1;
                        data.fileName = data.fileName || 'image';
                        evt.data.response = JSON.stringify(data);
                    }
                } catch (err) {}
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

        iframe.contentWindow.addEventListener('wheel', onWheel, { passive: false });

        iframe.contentWindow.addEventListener('touchmove', function (e) {
            const body = iframe.contentDocument && iframe.contentDocument.body;
            if (!body) {
                return;
            }
            const maxScroll = body.scrollHeight - body.clientHeight;
            if (maxScroll > 0) {
                e.stopPropagation();
            }
        }, { passive: true });

        if (viewport && !viewport.dataset.jpVanbanWheelBound) {
            viewport.dataset.jpVanbanWheelBound = '1';
            viewport.addEventListener('wheel', onWheel, { passive: false });
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
            resizeEditor(editor);
            initImageWidgets(editor);
            if (document.getElementById('office-report-form')?.dataset.reportLocked) {
                editor.setReadOnly(true);
            }
        });
    }

    function boot() {
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
