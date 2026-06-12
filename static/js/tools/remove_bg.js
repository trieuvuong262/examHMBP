(function () {
    const fileInput = document.getElementById('rmbg-file');
    const runBtn = document.getElementById('rmbg-run');
    const statusEl = document.getElementById('rmbg-status');
    const beforeImg = document.getElementById('rmbg-before');
    const afterImg = document.getElementById('rmbg-after');
    const beforeEmpty = document.getElementById('rmbg-before-empty');
    const afterEmpty = document.getElementById('rmbg-after-empty');
    const downloadBtn = document.getElementById('rmbg-download');
    const loading = window.JpToolLoading;
    const apiUrl = document.body.dataset.rmbgApi || '/cong-cu/api/xoa-nen/';

    let resultBlob = null;
    let simTimer = null;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function stopSim() {
        if (simTimer) {
            clearInterval(simTimer);
            simTimer = null;
        }
    }

    function startSimProgress(message, cap) {
        stopSim();
        if (!loading) return;
        let current = 12;
        loading.show(message, current);
        simTimer = setInterval(() => {
            if (current >= cap) return;
            current += 1;
            loading.setProgress(current, message);
        }, 700);
    }

    function sleep(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    async function postRemoveBackground(file) {
        const formData = new FormData();
        formData.append('image_file', file);
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken(),
            },
            body: formData,
            credentials: 'same-origin',
        });

        if (!response.ok) {
            let message = 'Không xóa được nền.';
            let retry = false;
            let warming = false;
            try {
                const payload = await response.json();
                if (payload && payload.error) {
                    message = payload.error;
                }
                retry = Boolean(payload && payload.retry);
                warming = Boolean(payload && payload.warming);
            } catch (err) {
                if (response.status === 502 || response.status === 504) {
                    message = 'Server đang tải mô hình AI lần đầu. Đang thử lại…';
                    retry = true;
                    warming = true;
                }
            }
            const error = new Error(message);
            error.retry = retry;
            error.warming = warming;
            throw error;
        }

        const blob = await response.blob();
        if (!blob || !blob.size) {
            throw new Error('Server không trả về ảnh kết quả.');
        }
        return blob;
    }

    if (fileInput) {
        fileInput.addEventListener('change', function () {
            resultBlob = null;
            downloadBtn.disabled = true;
            afterImg.classList.add('d-none');
            afterEmpty.classList.remove('d-none');
            if (statusEl) statusEl.textContent = '';

            const file = fileInput.files && fileInput.files[0];
            runBtn.disabled = !file;
            if (!file) {
                beforeImg.classList.add('d-none');
                beforeEmpty.classList.remove('d-none');
                return;
            }

            beforeImg.src = URL.createObjectURL(file);
            beforeImg.classList.remove('d-none');
            beforeEmpty.classList.add('d-none');
        });
    }

    if (runBtn) {
        runBtn.addEventListener('click', async function () {
            const file = fileInput.files && fileInput.files[0];
            if (!file) {
                return;
            }

            runBtn.disabled = true;
            downloadBtn.disabled = true;
            startSimProgress('Đang xóa nền trên server…', 92);

            try {
                let blob = null;
                let lastError = null;
                const maxAttempts = 3;

                for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
                    try {
                        if (attempt > 1) {
                            startSimProgress('Đang tải mô hình AI… thử lại (' + attempt + '/' + maxAttempts + ')', 92);
                            await sleep(attempt === 2 ? 8000 : 15000);
                        }
                        blob = await postRemoveBackground(file);
                        break;
                    } catch (err) {
                        lastError = err;
                        if (!err.retry || attempt === maxAttempts) {
                            throw err;
                        }
                    }
                }

                stopSim();
                resultBlob = blob;
                afterImg.src = URL.createObjectURL(blob);
                afterImg.classList.remove('d-none');
                afterEmpty.classList.add('d-none');
                downloadBtn.disabled = false;

                if (loading) {
                    loading.setProgress(100, 'Hoàn tất.');
                    window.setTimeout(() => loading.hide(), 450);
                } else if (statusEl) {
                    statusEl.textContent = 'Hoàn tất.';
                }
            } catch (err) {
                stopSim();
                if (loading) loading.hide();
                const msg = 'Lỗi: ' + (err.message || 'không xóa được nền.');
                if (statusEl) statusEl.textContent = msg;
            } finally {
                runBtn.disabled = false;
            }
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener('click', function () {
            if (!resultBlob) {
                return;
            }
            const link = document.createElement('a');
            link.href = URL.createObjectURL(resultBlob);
            link.download = 'khong-nen.png';
            link.click();
            URL.revokeObjectURL(link.href);
        });
    }
})();
