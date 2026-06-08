(function () {
    'use strict';

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function editorConfig(uploadUrl) {
        const config = {
            language: 'vi',
            placeholder: 'Bắt đầu nhập nội dung báo cáo…',
            toolbar: {
                items: [
                    'undo', 'redo', '|',
                    'heading', '|',
                    'fontSize', 'fontFamily', '|',
                    'bold', 'italic', 'underline', 'strikethrough', '|',
                    'fontColor', 'fontBackgroundColor', '|',
                    'alignment', '|',
                    'numberedList', 'bulletedList', '|',
                    'outdent', 'indent', '|',
                    'link', 'blockQuote', 'insertTable', 'horizontalLine', 'specialCharacters', '|',
                    'uploadImage', '|',
                    'removeFormat',
                ],
                shouldNotGroupWhenFull: true,
            },
            heading: {
                options: [
                    { model: 'paragraph', title: 'Đoạn văn', class: 'ck-heading_paragraph' },
                    { model: 'heading1', view: 'h1', title: 'Tiêu đề 1', class: 'ck-heading_heading1' },
                    { model: 'heading2', view: 'h2', title: 'Tiêu đề 2', class: 'ck-heading_heading2' },
                    { model: 'heading3', view: 'h3', title: 'Tiêu đề 3', class: 'ck-heading_heading3' },
                    { model: 'heading4', view: 'h4', title: 'Tiêu đề 4', class: 'ck-heading_heading4' },
                ],
            },
            fontSize: {
                options: [9, 10, 11, 12, 13, 'default', 14, 16, 18, 20, 24, 28, 32],
            },
            fontFamily: {
                options: [
                    'default',
                    'Times New Roman, Times, serif',
                    'Arial, Helvetica, sans-serif',
                    'Calibri, Carlito, sans-serif',
                    'Georgia, serif',
                    'Verdana, Geneva, sans-serif',
                    'Courier New, Courier, monospace',
                ],
            },
            table: {
                contentToolbar: [
                    'tableColumn', 'tableRow', 'mergeTableCells',
                    'tableProperties', 'tableCellProperties',
                ],
            },
            image: {
                toolbar: [
                    'imageTextAlternative', '|',
                    'imageStyle:inline', 'imageStyle:block', 'imageStyle:side',
                ],
            },
        };

        if (uploadUrl) {
            config.simpleUpload = {
                uploadUrl: uploadUrl,
                withCredentials: true,
                headers: { 'X-CSRFToken': getCsrfToken() },
            };
        }
        return config;
    }

    function setLoading(wrapper, on) {
        const desk = wrapper.querySelector('.jp-word-desk');
        if (!desk) return;
        desk.classList.toggle('is-loading', on);
    }

    async function initEditor(wrapper) {
        if (wrapper.dataset.ck5Ready === '1') {
            return wrapper._jpCk5Editor || true;
        }

        const EditorClass = window.CKEDITOR && (CKEDITOR.DecoupledEditor || CKEDITOR.ClassicEditor);
        if (!EditorClass) {
            return false;
        }

        const textareaId = wrapper.dataset.ck5Textarea;
        const textarea = document.getElementById(textareaId);
        const toolbarHost = wrapper.querySelector('.jp-ck5-toolbar-host');
        const editableHost = wrapper.querySelector('.jp-ck5-editable-host');
        if (!textarea || !editableHost) return false;

        setLoading(wrapper, true);
        const uploadUrl = wrapper.dataset.uploadUrl || '';

        try {
            let editor;
            if (CKEDITOR.DecoupledEditor) {
                editor = await CKEDITOR.DecoupledEditor.create(editableHost, editorConfig(uploadUrl));
                if (toolbarHost) {
                    toolbarHost.appendChild(editor.ui.view.toolbar.element);
                }
                wrapper.classList.add('is-decoupled');
            } else {
                editor = await CKEDITOR.ClassicEditor.create(editableHost, editorConfig(uploadUrl));
                wrapper.classList.add('is-classic');
            }

            editor.setData(textarea.value || '');
            wrapper.dataset.ck5Ready = '1';
            wrapper._jpCk5Editor = editor;

            editor.model.document.on('change:data', function () {
                textarea.value = editor.getData();
            });

            const form = wrapper.closest('form');
            if (form) {
                form.addEventListener('submit', function () {
                    textarea.value = editor.getData();
                });
            }

            setLoading(wrapper, false);
            return editor;
        } catch (err) {
            console.error('CKEditor 5 init failed:', err);
            setLoading(wrapper, false);
            wrapper.classList.add('is-fallback');
            textarea.classList.remove('d-none');
            if (editableHost) editableHost.style.display = 'none';
            if (toolbarHost) toolbarHost.style.display = 'none';
            return false;
        }
    }

    function boot() {
        const wrappers = Array.from(document.querySelectorAll('.jp-ck5-editor'));
        if (!wrappers.length) return;

        const wordTab = document.getElementById('vanban-tab');
        const wordPane = document.getElementById('vanban-pane');

        function bindUploadUrl() {
            const el = document.querySelector('[data-ck5-upload-url]');
            const uploadUrl = el ? el.dataset.ck5UploadUrl : '';
            wrappers.forEach(function (w) {
                if (uploadUrl) w.dataset.uploadUrl = uploadUrl;
            });
        }

        async function ensureEditors() {
            bindUploadUrl();
            for (const wrapper of wrappers) {
                const editor = await initEditor(wrapper);
                if (editor && editor.editing) {
                    setTimeout(function () {
                        editor.editing.view.focus();
                    }, 80);
                }
            }
        }

        if (wordTab) {
            wordTab.addEventListener('shown.bs.tab', ensureEditors);
        }
        if (wordPane && wordPane.classList.contains('show') && wordPane.classList.contains('active')) {
            ensureEditors();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
