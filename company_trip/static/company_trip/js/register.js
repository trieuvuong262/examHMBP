(function () {
  const cfg = window.JP_TRIP_REGISTER || {};
  const profileId = cfg.profileId;
  const searchUrl = cfg.searchUrl;
  const roomSelect = document.getElementById(cfg.roomSelectId);
  const wrap = document.getElementById('roommates-wrap');
  const wrap1 = document.getElementById('companion1-wrap');
  const wrap2 = document.getElementById('companion2-wrap');
  const hint = document.getElementById('roommates-hint');
  const hidden1 = document.getElementById('id_companion1_id');
  const hidden2 = document.getElementById('id_companion2_id');
  const input1 = document.getElementById('companion1-search');
  const input2 = document.getElementById('companion2-search');

  if (!roomSelect || !wrap) return;

  function clearCompanion(hidden, input) {
    if (hidden) hidden.value = '';
    if (input) {
      input.value = '';
      input.dataset.selected = '';
    }
  }

  function toggleCompanions() {
    const v = (roomSelect.value || '').trim();
    const is2 = v === 'Phòng 2';
    const is3 = v === 'Phòng 3';
    wrap.classList.toggle('d-none', !is2 && !is3);
    if (wrap1) wrap1.classList.toggle('d-none', !is2 && !is3);
    if (wrap2) wrap2.classList.toggle('d-none', !is3);
    if (hint) {
      if (is2) hint.textContent = 'Phòng 2: chọn thêm 1 người cùng phòng (gõ tên rồi chọn từ danh sách).';
      else if (is3) hint.textContent = 'Phòng 3: chọn thêm 2 người cùng phòng (gõ tên rồi chọn từ danh sách).';
      else hint.textContent = '';
    }
    if (!is2 && !is3) {
      clearCompanion(hidden1, input1);
      clearCompanion(hidden2, input2);
    }
    if (is2) clearCompanion(hidden2, input2);
  }

  roomSelect.addEventListener('change', toggleCompanions);
  toggleCompanions();

  function excludeIds(otherHidden) {
    const ids = [];
    if (profileId) ids.push(profileId);
    if (otherHidden && otherHidden.value) ids.push(otherHidden.value);
    return ids.join(',');
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bindSearch(input, results, hidden, otherHidden) {
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
      const url = searchUrl + '?q=' + encodeURIComponent(query) + '&exclude=' + encodeURIComponent(excludeIds(otherHidden));
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
        const meta = [item.code, item.position, item.department].filter(Boolean).join(' · ');
        a.innerHTML = '<strong>' + escapeHtml(item.name) + '</strong>'
          + (meta ? '<div class="small text-muted">' + escapeHtml(meta) + '</div>' : '');
        a.addEventListener('mousedown', function (e) {
          e.preventDefault();
          if (otherHidden && String(otherHidden.value) === String(item.id)) {
            alert('Hai người cùng phòng không được trùng nhau.');
            return;
          }
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
        showHint('Gõ tên / mã NV để chọn người cùng phòng.');
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

  bindSearch(input1, document.getElementById('companion1-results'), hidden1, hidden2);
  bindSearch(input2, document.getElementById('companion2-results'), hidden2, hidden1);
})();
