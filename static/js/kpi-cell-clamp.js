/**
 * KPI chi tiết: giới hạn mỗi ô nội dung cao 3 dòng, hiện nút mở rộng khi tràn.
 * Chạy cho cả chế độ chỉ đọc và chế độ chấm điểm.
 */
(function () {
  'use strict';

  var SELECTOR = '[data-kpi-clamp]';
  var OVERFLOW_SLACK = 2; // px — bỏ qua sai số làm tròn của trình duyệt

  function parts(root) {
    return {
      body: root.querySelector('[data-kpi-clamp-body]'),
      toggle: root.querySelector('[data-kpi-clamp-toggle]'),
    };
  }

  /** Cập nhật hiển thị nút mở rộng theo trạng thái tràn nội dung thực tế. */
  function refresh(root) {
    var el = parts(root);
    if (!el.body || !el.toggle) return;
    if (root.classList.contains('is-expanded')) {
      el.toggle.hidden = false;
      return;
    }
    var overflowing = el.body.scrollHeight - el.body.clientHeight > OVERFLOW_SLACK;
    el.toggle.hidden = !overflowing;
    root.classList.toggle('is-clamped', overflowing);
  }

  function setExpanded(root, expanded) {
    var el = parts(root);
    root.classList.toggle('is-expanded', expanded);
    if (el.toggle) {
      el.toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      el.toggle.title = expanded ? 'Thu gọn' : 'Mở rộng';
      el.toggle.setAttribute('aria-label', el.toggle.title);
    }
    if (!expanded) refresh(root);
  }

  function init() {
    var roots = Array.prototype.slice.call(document.querySelectorAll(SELECTOR));
    if (!roots.length) return;

    roots.forEach(function (root) {
      var el = parts(root);
      if (!el.body || !el.toggle) return;

      el.toggle.addEventListener('click', function (e) {
        e.preventDefault();
        setExpanded(root, !root.classList.contains('is-expanded'));
      });

      // Nội dung ô có thể thay đổi (nhập liệu, dán ảnh) → đo lại.
      if (typeof ResizeObserver === 'function') {
        new ResizeObserver(function () { refresh(root); }).observe(el.body);
      }
      el.body.addEventListener('input', function () { refresh(root); });
      // Ô rich text giãn ra khi focus (CSS) → đo lại sau khi rời khỏi ô.
      root.addEventListener('focusout', function () {
        window.setTimeout(function () { refresh(root); }, 0);
      });

      refresh(root);
    });

    // Ảnh tải xong làm chiều cao đổi → đo lại toàn bộ.
    function refreshAll() { roots.forEach(refresh); }
    window.addEventListener('load', refreshAll);
    window.addEventListener('resize', refreshAll);
    document.querySelectorAll('.jp-kpi-table img').forEach(function (img) {
      if (!img.complete) img.addEventListener('load', refreshAll, { once: true });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
