(function () {
    const fileInput = document.getElementById('ocr-file');
    const langSelect = document.getElementById('ocr-lang');
    const runBtn = document.getElementById('ocr-run');
    const statusEl = document.getElementById('ocr-status');
    const previewWrap = document.getElementById('ocr-preview-wrap');
    const previewImg = document.getElementById('ocr-preview');
    const resultEl = document.getElementById('ocr-result');
    const copyBtn = document.getElementById('ocr-copy');
    const downloadBtn = document.getElementById('ocr-download');
    const loading = window.JpToolLoading;

    if (!fileInput || typeof Tesseract === 'undefined') {
        return;
    }

    function statusLabel(m) {
        if (!m || !m.status) return 'Đang nhận dạng…';
        const map = {
            'loading tesseract core': 'Đang tải OCR…',
            'initializing tesseract': 'Đang khởi tạo…',
            'loading language traineddata': 'Đang tải ngôn ngữ…',
            'initializing api': 'Đang sẵn sàng…',
            'recognizing text': 'Đang nhận dạng chữ…',
        };
        return map[m.status] || 'Đang xử lý…';
    }

    fileInput.addEventListener('change', function () {
        runBtn.disabled = !fileInput.files || !fileInput.files.length;
        if (fileInput.files && fileInput.files[0]) {
            previewImg.src = URL.createObjectURL(fileInput.files[0]);
            previewWrap.classList.remove('d-none');
        }
    });

    runBtn.addEventListener('click', async function () {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
            return;
        }

        runBtn.disabled = true;
        copyBtn.disabled = true;
        downloadBtn.disabled = true;
        resultEl.value = '';
        if (loading) {
            loading.show('Đang tải OCR…', 2);
        } else if (statusEl) {
            statusEl.textContent = 'Đang nhận dạng…';
        }

        try {
            const result = await Tesseract.recognize(file, langSelect.value, {
                logger: function (m) {
                    if (!loading) {
                        if (m.status === 'recognizing text' && m.progress && statusEl) {
                            statusEl.textContent = 'Đang nhận dạng… ' + Math.round(m.progress * 100) + '%';
                        }
                        return;
                    }
                    let pct = 0;
                    if (typeof m.progress === 'number') {
                        pct = Math.round(m.progress * 100);
                    }
                    loading.setProgress(pct, statusLabel(m));
                },
            });
            resultEl.value = (result.data.text || '').trim();
            if (loading) {
                loading.setProgress(100, resultEl.value ? 'Hoàn tất.' : 'Không tìm thấy chữ trong ảnh.');
                window.setTimeout(() => loading.hide(), 450);
            } else if (statusEl) {
                statusEl.textContent = resultEl.value ? 'Hoàn tất.' : 'Không tìm thấy chữ trong ảnh.';
            }
            copyBtn.disabled = !resultEl.value;
            downloadBtn.disabled = !resultEl.value;
        } catch (err) {
            if (loading) loading.hide();
            const msg = 'Lỗi: ' + (err.message || 'không xử lý được ảnh.');
            if (statusEl) statusEl.textContent = msg;
        } finally {
            runBtn.disabled = false;
        }
    });

    copyBtn.addEventListener('click', async function () {
        if (!resultEl.value) {
            return;
        }
        try {
            await navigator.clipboard.writeText(resultEl.value);
            if (statusEl) statusEl.textContent = 'Đã sao chép.';
        } catch (err) {
            if (statusEl) statusEl.textContent = 'Không sao chép được — hãy chọn và copy thủ công.';
        }
    });

    downloadBtn.addEventListener('click', function () {
        if (!resultEl.value) {
            return;
        }
        const blob = new Blob([resultEl.value], { type: 'text/plain;charset=utf-8' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'ocr-ket-qua.txt';
        link.click();
        URL.revokeObjectURL(link.href);
    });
})();
