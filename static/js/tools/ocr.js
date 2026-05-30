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

    if (!fileInput || typeof Tesseract === 'undefined') {
        return;
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
        statusEl.textContent = 'Đang nhận dạng…';
        resultEl.value = '';

        try {
            const result = await Tesseract.recognize(file, langSelect.value, {
                logger: function (m) {
                    if (m.status === 'recognizing text' && m.progress) {
                        statusEl.textContent = 'Đang nhận dạng… ' + Math.round(m.progress * 100) + '%';
                    }
                },
            });
            resultEl.value = (result.data.text || '').trim();
            statusEl.textContent = resultEl.value ? 'Hoàn tất.' : 'Không tìm thấy chữ trong ảnh.';
            copyBtn.disabled = !resultEl.value;
            downloadBtn.disabled = !resultEl.value;
        } catch (err) {
            statusEl.textContent = 'Lỗi: ' + (err.message || 'không xử lý được ảnh.');
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
            statusEl.textContent = 'Đã sao chép.';
        } catch (err) {
            statusEl.textContent = 'Không sao chép được — hãy chọn và copy thủ công.';
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
