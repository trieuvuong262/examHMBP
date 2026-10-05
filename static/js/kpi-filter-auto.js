/**
 * KPI danh sách: tự động lọc khi đổi Tháng/Năm/Bộ phận hoặc gõ tìm kiếm.
 * Nút «Lọc» chỉ còn là phương án dự phòng khi JS tắt → ẩn khi JS chạy.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-kpi-filter]');
  if (!form) return;

  var SEARCH_DEBOUNCE_MS = 450;
  var searchTimer = null;

  function submit() {
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  // Ẩn nút Lọc (vẫn giữ trong DOM cho no-JS, nhưng không chiếm chỗ)
  var submitBtn = form.querySelector('[data-kpi-filter-submit]');
  if (submitBtn) submitBtn.classList.add('d-none');

  // Select: đổi là lọc ngay
  form.querySelectorAll('[data-kpi-filter-auto]').forEach(function (el) {
    el.addEventListener('change', submit);
  });

  // Tìm kiếm: debounce khi gõ, submit ngay khi nhấn Enter / xóa (search clear)
  var search = form.querySelector('[data-kpi-filter-search]');
  if (search) {
    search.addEventListener('input', function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(submit, SEARCH_DEBOUNCE_MS);
    });
    search.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        if (searchTimer) clearTimeout(searchTimer);
        // để form tự submit mặc định
      }
    });
    search.addEventListener('search', function () {
      // Bấm nút «x» của input[type=search]
      if (searchTimer) clearTimeout(searchTimer);
      submit();
    });
  }
})();
