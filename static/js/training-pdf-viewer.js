/**
 * PDF viewer for training lessons — scrollable on mobile (PDF.js).
 */
(function () {
    'use strict';

    var PDFJS_VERSION = '3.11.174';
    var PDFJS_BASE = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/' + PDFJS_VERSION + '/';

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]')) {
                resolve();
                return;
            }
            var s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    function ensurePdfJs() {
        if (window.pdfjsLib) {
            return Promise.resolve(window.pdfjsLib);
        }
        return loadScript(PDFJS_BASE + 'pdf.min.js').then(function () {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_BASE + 'pdf.worker.min.js';
            return window.pdfjsLib;
        });
    }

    function pageWrap(canvas, pageNum, total) {
        var wrap = document.createElement('div');
        wrap.className = 'jp-training-pdf-page';
        wrap.appendChild(canvas);
        var label = document.createElement('div');
        label.className = 'jp-training-pdf-page-label';
        label.textContent = 'Trang ' + pageNum + ' / ' + total;
        wrap.appendChild(label);
        return wrap;
    }

    function renderPdf(root) {
        var url = root.getAttribute('data-pdf-url');
        if (!url) return;

        var pagesEl = root.querySelector('.jp-training-pdf-pages');
        var statusEl = root.querySelector('.jp-training-pdf-status');
        var metaEl = root.querySelector('[data-pdf-meta]');
        if (!pagesEl) return;

        var dpr = Math.min(window.devicePixelRatio || 1, 2);

        function showError() {
            root.classList.add('is-error');
        }

        function setMeta(text) {
            if (metaEl) metaEl.textContent = text;
        }

        ensurePdfJs()
            .then(function (pdfjsLib) {
                return pdfjsLib.getDocument({ url: url, withCredentials: true }).promise;
            })
            .then(function (pdf) {
                setMeta(pdf.numPages + ' trang');
                if (statusEl) statusEl.classList.add('d-none');
                pagesEl.innerHTML = '';

                var renderChain = Promise.resolve();
                for (var i = 1; i <= pdf.numPages; i++) {
                    (function (pageNum) {
                        renderChain = renderChain.then(function () {
                            return pdf.getPage(pageNum).then(function (page) {
                                var containerWidth = pagesEl.clientWidth || root.clientWidth || 360;
                                var unscaled = page.getViewport({ scale: 1 });
                                var scale = (containerWidth - 16) / unscaled.width;
                                var viewport = page.getViewport({ scale: scale * dpr });

                                var canvas = document.createElement('canvas');
                                var ctx = canvas.getContext('2d', { alpha: false });
                                canvas.width = viewport.width;
                                canvas.height = viewport.height;
                                canvas.style.width = Math.floor(viewport.width / dpr) + 'px';
                                canvas.style.height = Math.floor(viewport.height / dpr) + 'px';

                                return page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function () {
                                    pagesEl.appendChild(pageWrap(canvas, pageNum, pdf.numPages));
                                });
                            });
                        });
                    })(i);
                }
                return renderChain;
            })
            .catch(function () {
                showError();
            });
    }

    function initAll() {
        document.querySelectorAll('[data-jp-pdf-viewer]').forEach(renderPdf);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
