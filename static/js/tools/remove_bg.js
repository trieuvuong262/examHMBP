import { removeBackground } from 'https://cdn.jsdelivr.net/npm/@imgly/background-removal@1.4.5/+esm';

const fileInput = document.getElementById('rmbg-file');
const runBtn = document.getElementById('rmbg-run');
const statusEl = document.getElementById('rmbg-status');
const beforeImg = document.getElementById('rmbg-before');
const afterImg = document.getElementById('rmbg-after');
const beforeEmpty = document.getElementById('rmbg-before-empty');
const afterEmpty = document.getElementById('rmbg-after-empty');
const downloadBtn = document.getElementById('rmbg-download');

let resultBlob = null;

if (fileInput) {
    fileInput.addEventListener('change', function () {
        resultBlob = null;
        downloadBtn.disabled = true;
        afterImg.classList.add('d-none');
        afterEmpty.classList.remove('d-none');

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
        statusEl.textContent = 'Đang tải mô hình & xử lý…';

        try {
            const blob = await removeBackground(file);
            resultBlob = blob;
            afterImg.src = URL.createObjectURL(blob);
            afterImg.classList.remove('d-none');
            afterEmpty.classList.add('d-none');
            downloadBtn.disabled = false;
            statusEl.textContent = 'Hoàn tất.';
        } catch (err) {
            statusEl.textContent = 'Lỗi: ' + (err.message || 'không xóa được nền.');
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
