(function () {
    'use strict';

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function syncEditorToTextarea(editor, textarea) {
        textarea.value = editor.getData();
    }

    async function initEditor(wrapper) {
        if (!window.CKEDITOR || !CKEDITOR.DecoupledEditor) {
            console.warn('CKEditor 5 chưa tải xong.');
            return;
        }
        const textareaId = wrapper.dataset.ck5Textarea;
        const textarea = document.getElementById(textareaId);
        if (!textarea || wrapper.dataset.ck5Ready === '1') return;

        const toolbarHost = wrapper.querySelector('.jp-ck5-toolbar-host');
        const editableHost = wrapper.querySelector('.jp-ck5-editable-host');
        const uploadUrl = wrapper.dataset.uploadUrl || '';
        if (!toolbarHost || !editableHost) return;

        const config = {
            language: 'vi',
            placeholder: 'Soạn báo cáo: tiêu đề, nội dung, bảng biểu, danh sách công việc…',
            toolbar: {
                items: [
                    'heading', '|',
                    'fontSize', 'fontFamily', '|',
                    'bold', 'italic', 'underline', 'strikethrough', 'subscript', 'superscript', '|',
                    'fontColor', 'fontBackgroundColor', '|',
                    'alignment', '|',
                    'numberedList', 'bulletedList', '|',
                    'outdent', 'indent', '|',
                    'link', 'blockQuote', 'insertTable', 'horizontalLine', 'specialCharacters', '|',
                    'uploadImage', 'mediaEmbed', '|',
                    'removeFormat', '|',
                    'undo', 'redo',
                ],
                shouldNotGroupWhenFull: false,
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
                options: [10, 11, 12, 13, 'default', 15, 16, 18, 20, 24, 28, 32],
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
                    'imageStyle:inline', 'imageStyle:block', 'imageStyle:side', '|',
                    'toggleImageCaption', 'linkImage',
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

        try {
            const editor = await CKEDITOR.DecoupledEditor.create(editableHost, config);
            toolbarHost.appendChild(editor.ui.view.toolbar.element);
            editor.setData(textarea.value || '');
            wrapper.dataset.ck5Ready = '1';

            editor.model.document.on('change:data', function () {
                syncEditorToTextarea(editor, textarea);
            });

            const form = wrapper.closest('form');
            if (form) {
                form.addEventListener('submit', function () {
                    syncEditorToTextarea(editor, textarea);
                });
            }

            const wordTab = document.getElementById('vanban-tab');
            if (wordTab) {
                wordTab.addEventListener('shown.bs.tab', function () {
                    editor.editing.view.focus();
                });
            }
        } catch (err) {
            console.error('CKEditor 5 init failed:', err);
            textarea.classList.remove('d-none');
            editableHost.style.display = 'none';
            toolbarHost.style.display = 'none';
        }
    }

    function boot() {
        document.querySelectorAll('.jp-ck5-editor').forEach(function (wrapper) {
            initEditor(wrapper);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
