(function () {
    'use strict';

    if (window.CKEDITOR) {
        CKEDITOR.config.versionCheck = false;
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
        extraPlugins: 'uploadimage,image2,tableresize,tabletools,tableselection,liststyle,pastefromword,copyformatting,stylescombo,autogrow',
        removePlugins: 'exportpdf,image',
        allowedContent: true,
        forcePasteAsPlainText: false,
        contentsCss: ['/static/css/reports-office-contents.css'],
    };

    function applyWordPageLayout(editor) {
        if (!editor || !editor.editable) return;
        try {
            const doc = editor.document;
            if (!doc || !doc.$) return;
            const $ = doc.$;
            const $html = $('html');
            const $body = $('body');
            if ($html.length) {
                $html.css({ background: '#ffffff', minHeight: '100%', height: 'auto' });
            }
            if ($body.length) {
                $body.css({
                    width: '100%',
                    maxWidth: '21cm',
                    minHeight: '29.7cm',
                    margin: '16px auto 24px',
                    padding: '2.54cm 2cm 2.54cm 2.5cm',
                    background: '#ffffff',
                    boxShadow: 'none',
                    border: '1px solid #e5e7eb',
                    fontFamily: "'Times New Roman', Times, serif",
                    fontSize: '14pt',
                    lineHeight: '1.5',
                    color: '#000000',
                    boxSizing: 'border-box',
                });
            }
        } catch (err) {
            console.warn('JP Word layout:', err);
        }
    }

    function resizeEditor(editor) {
        if (!editor || !editor.resize) return;
        editor.resize('100%', 580);
        applyWordPageLayout(editor);
    }

    function buildConfig() {
        const cfg = Object.assign({}, window.JP_WORD_EDITOR_CFG);
        const ltsKey = window.JP_CKEDITOR_LTS_LICENSE || '';
        if (ltsKey) {
            cfg.licenseKey = ltsKey;
        }
        const uploadEl = document.querySelector('[data-ck-upload-url]');
        if (uploadEl && uploadEl.dataset.ckUploadUrl) {
            cfg.filebrowserUploadUrl = uploadEl.dataset.ckUploadUrl;
            cfg.filebrowserBrowseUrl = uploadEl.dataset.ckBrowseUrl || '';
            cfg.filebrowserImageUploadUrl = uploadEl.dataset.ckUploadUrl;
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
            resizeEditor(CKEDITOR.instances[fieldId]);
            window.JP_WORD_EDITOR_READY = true;
            return;
        }

        if (window.JP_WORD_EDITOR_READY) {
            return;
        }

        studio.classList.add('is-loading');
        const editor = CKEDITOR.replace(fieldId, buildConfig());

        editor.on('contentDom', function () {
            applyWordPageLayout(editor);
        });

        editor.on('instanceReady', function () {
            studio.classList.remove('is-loading');
            studio.classList.add('is-ready');
            window.JP_WORD_EDITOR_READY = true;
            resizeEditor(editor);
        });
    }

    function boot() {
        const wordTab = document.getElementById('vanban-tab');
        const wordPane = document.getElementById('vanban-pane');

        if (wordTab) {
            wordTab.addEventListener('shown.bs.tab', function () {
                window.setTimeout(initWordEditor, 60);
            });
        }
        if (wordPane && wordPane.classList.contains('show') && wordPane.classList.contains('active')) {
            initWordEditor();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
