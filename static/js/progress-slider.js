/**
 * Thanh kéo tiến độ — đồng bộ % hiển thị khi kéo.
 */
(function () {
    function initWrap(wrap) {
        var slider = wrap.querySelector('.jp-progress-slider');
        var valueEl = wrap.querySelector('.jp-progress-slider-value');
        if (!slider || !valueEl) return;

        function sync() {
            valueEl.textContent = slider.value + '%';
        }

        slider.addEventListener('input', sync);
        slider.addEventListener('change', sync);
        sync();
    }

    function initAll(root) {
        (root || document).querySelectorAll('.jp-progress-slider-wrap').forEach(initWrap);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initAll(); });
    } else {
        initAll();
    }

    window.jpInitProgressSliders = initAll;
})();
