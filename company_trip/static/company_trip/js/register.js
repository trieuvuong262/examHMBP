(function () {
  const cfg = window.JP_TRIP_REGISTER || {};
  const form = document.getElementById('trip-register-form');
  if (form) {
    form.addEventListener('submit', function () {
      if (form.dataset.loading === '1') return;
      form.dataset.loading = '1';
      const overlay = document.createElement('div');
      overlay.id = 'jp-trip-submit-loading';
      overlay.className = 'jp-tool-loading';
      overlay.setAttribute('role', 'status');
      overlay.setAttribute('aria-live', 'polite');
      overlay.setAttribute('aria-busy', 'true');
      overlay.innerHTML = '<div class="jp-tool-loading-panel">'
        + '<div class="jp-tool-loading-spinner" aria-hidden="true"></div>'
        + '<p class="jp-tool-loading-msg mb-0">Đang gửi đăng ký…</p>'
        + '</div>';
      document.body.appendChild(overlay);
      document.body.classList.add('jp-tool-loading-active');
      const btn = form.querySelector('[type="submit"]');
      if (btn) btn.disabled = true;
    });
    window.addEventListener('pageshow', function () {
      const overlay = document.getElementById('jp-trip-submit-loading');
      if (overlay) overlay.remove();
      document.body.classList.remove('jp-tool-loading-active');
      form.dataset.loading = '';
      const btn = form.querySelector('[type="submit"]');
      if (btn) btn.disabled = false;
    });
  }

  const profileId = cfg.profileId;
  const searchUrl = cfg.searchUrl;
  const roomSelect = document.getElementById(cfg.roomSelectId);
  const colleagueWrap = document.getElementById('colleague-wrap');
  const relativeWrap = document.getElementById('relative-wrap');
  const hidden1 = document.getElementById('id_companion1_id');
  const input1 = document.getElementById('companion1-search');

  if (!roomSelect || !colleagueWrap || !relativeWrap) return;

  function clearCompanion() {
    if (hidden1) hidden1.value = '';
    if (input1) {
      input1.value = '';
      input1.dataset.selected = '';
    }
  }

  function refreshRelativeAdd() {
    const addBtn = document.getElementById('relative-add');
    if (!addBtn) return;
    const hidden = relativeWrap.querySelector('[data-relative-card].d-none');
    addBtn.classList.toggle('d-none', !hidden);
  }

  function clearRelative() {
    relativeWrap.querySelectorAll('[data-relative-card]').forEach(function (card, index) {
      card.querySelectorAll('input, select, textarea').forEach(function (el) {
        el.value = '';
      });
      card.classList.toggle('d-none', index > 0);
    });
    refreshRelativeAdd();
  }

  const relativeAdd = document.getElementById('relative-add');
  if (relativeAdd) {
    relativeAdd.addEventListener('click', function () {
      const next = relativeWrap.querySelector('[data-relative-card].d-none');
      if (!next) return;
      next.classList.remove('d-none');
      const first = next.querySelector('input, select');
      if (first) first.focus();
      refreshRelativeAdd();
    });
  }
  relativeWrap.querySelectorAll('[data-relative-remove]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const card = btn.closest('[data-relative-card]');
      if (!card) return;
      card.querySelectorAll('input, select, textarea').forEach(function (el) {
        el.value = '';
      });
      card.classList.add('d-none');
      refreshRelativeAdd();
    });
  });
  refreshRelativeAdd();

  function toggleRoom() {
    const v = (roomSelect.value || '').trim();
    const isColleague = v === cfg.roomColleague;
    const isRelative = v === cfg.roomRelative;
    colleagueWrap.classList.toggle('d-none', !isColleague);
    relativeWrap.classList.toggle('d-none', !isRelative);
    if (!isColleague) clearCompanion();
    if (!isRelative) clearRelative();
  }

  roomSelect.addEventListener('change', toggleRoom);
  toggleRoom();

  if (hidden1 && hidden1.value && input1 && input1.value.trim()) {
    input1.dataset.selected = 'true';
  }

  function excludeIds() {
    const ids = [];
    if (profileId) ids.push(profileId);
    return ids.join(',');
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bindSearch(input, results, hidden) {
    if (!input || !results || !hidden) return;
    let timer = null;
    let reqId = 0;

    function hide() {
      results.classList.add('d-none');
      results.innerHTML = '';
    }

    function showHint(msg) {
      results.innerHTML = '<div class="jp-trip-suggest-empty">' + escapeHtml(msg) + '</div>';
      results.classList.remove('d-none');
    }

    async function fetchList(query) {
      const url = searchUrl + '?q=' + encodeURIComponent(query) + '&exclude=' + encodeURIComponent(excludeIds());
      const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : (data.results || []);
    }

    function render(items, query) {
      results.innerHTML = '';
      if (!items.length) {
        showHint(query ? 'Không tìm thấy nhân viên phù hợp.' : 'Gõ ít nhất 1 ký tự để tìm.');
        return;
      }
      items.forEach(function (item) {
        const a = document.createElement('button');
        a.type = 'button';
        a.className = 'list-group-item list-group-item-action';
        if (item.unavailable) a.disabled = true;
        const meta = [item.code, item.position, item.department, item.reason].filter(Boolean).join(' · ');
        a.innerHTML = '<strong>' + escapeHtml(item.name) + '</strong>'
          + (meta ? '<div class="small text-muted">' + escapeHtml(meta) + '</div>' : '');
        a.addEventListener('mousedown', function (e) {
          e.preventDefault();
          if (item.unavailable) return;
          hidden.value = item.id;
          input.value = item.name;
          input.dataset.selected = 'true';
          hide();
        });
        results.appendChild(a);
      });
      results.classList.remove('d-none');
    }

    function runSearch(query) {
      const q = (query || '').trim();
      if (!q) {
        showHint('Gõ tên / mã NV để chọn đồng nghiệp.');
        return;
      }
      const myReq = ++reqId;
      fetchList(q).then(function (items) {
        if (myReq !== reqId) return;
        render(items, q);
      }).catch(function () {
        if (myReq !== reqId) return;
        showHint('Không tải được danh sách. Thử lại.');
      });
    }

    input.addEventListener('focus', function () {
      runSearch(input.value);
    });
    input.addEventListener('input', function () {
      input.dataset.selected = '';
      hidden.value = '';
      clearTimeout(timer);
      timer = setTimeout(function () {
        runSearch(input.value);
      }, 200);
    });
    input.addEventListener('blur', function () {
      setTimeout(function () {
        hide();
        if (input.value.trim() && input.dataset.selected !== 'true') {
          input.value = '';
          hidden.value = '';
        }
      }, 180);
    });
  }

  bindSearch(input1, document.getElementById('companion1-results'), hidden1);
})();
