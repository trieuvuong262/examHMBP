/**
 * KPI chi tiết: tính Điểm TP (NV → QL), autosave draft localStorage.
 */
(function () {
  'use strict';

  var form = document.getElementById('kpi-detail-form');
  var table = document.querySelector('[data-kpi-table]');
  if (!form || !table) return;

  var kpiId = form.getAttribute('data-kpi-id') || '';
  var STORAGE_KEY = 'jp_kpi_draft_' + kpiId;
  var SAVE_MS = 1200;
  var saveTimer = null;

  function num(v) {
    if (v === null || v === undefined || String(v).trim() === '') return null;
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function resultOf(total) {
    if (total === null) return { code: 'pending', label: 'Chưa chấm' };
    if (total < 90) return { code: 'fail', label: 'Không đạt' };
    if (total <= 100) return { code: 'pass', label: 'Đạt' };
    return { code: 'exceed', label: 'Vượt' };
  }

  function paintResult(el, code, label) {
    if (!el) return;
    el.textContent = label;
    el.className = el.className
      .split(/\s+/)
      .filter(function (c) {
        return c && !c.startsWith('jp-kpi-badge--') && !c.startsWith('jp-kpi-result-');
      })
      .join(' ');
    if (el.classList.contains('jp-kpi-badge') || el.hasAttribute('data-kpi-result')) {
      el.classList.add('jp-kpi-badge', 'jp-kpi-badge--' + code);
    } else {
      el.classList.add('jp-kpi-result-' + code);
    }
  }

  /** Điểm hiệu lực: có QL thì dùng QL, chưa có thì dùng NV. */
  function effectiveScore(selfScore, mgrScore) {
    if (mgrScore !== null) return mgrScore;
    if (selfScore !== null) return selfScore;
    return null;
  }

  function recalc() {
    var total = 0;
    var has = false;
    table.querySelectorAll('tbody tr[data-weight]').forEach(function (row) {
      var weight = num(row.getAttribute('data-weight')) || 0;
      var selfEl = row.querySelector('[data-kpi-self-score]');
      var mgrEl = row.querySelector('[data-kpi-mgr-score]');
      var selfScore = selfEl ? num(selfEl.value) : null;
      var mgrScore = mgrEl ? num(mgrEl.value) : null;
      var score = effectiveScore(selfScore, mgrScore);
      var tpEl = row.querySelector('[data-kpi-tp]');
      if (score === null) {
        if (tpEl) tpEl.textContent = '—';
        return;
      }
      var part = (score / 10) * weight;
      has = true;
      total += part;
      if (tpEl) tpEl.textContent = part.toFixed(2);
    });
    var display = has ? Math.round(total * 100) / 100 : null;
    var res = resultOf(display);
    var totalText = display === null ? '—' : String(display);
    document.querySelectorAll('[data-kpi-total], [data-kpi-total-foot]').forEach(function (el) {
      el.textContent = totalText;
    });
    paintResult(document.querySelector('[data-kpi-result]'), res.code, res.label);
    var foot = document.querySelector('[data-kpi-result-foot]');
    if (foot) {
      foot.textContent = res.label;
      foot.className = 'fw-semibold jp-kpi-result-' + res.code;
    }
  }

  function syncRichEditors() {
    form.querySelectorAll('[data-kpi-rich]').forEach(function (root) {
      var editor = root.querySelector('[data-kpi-rich-editor]');
      var input = root.querySelector('[data-kpi-rich-input]');
      if (!editor || !input) return;
      var html = (editor.innerHTML || '').trim();
      if (html === '<br>' || html === '<div><br></div>') html = '';
      input.value = html;
    });
  }

  function collectDraft() {
    syncRichEditors();
    var fields = {};
    form.querySelectorAll('input[name^="item_"], textarea[name^="item_"]').forEach(function (el) {
      if (!el.name) return;
      fields[el.name] = el.value;
    });
    return { fields: fields, ts: Date.now() };
  }

  function draftHasContent(draft) {
    if (!draft || !draft.fields) return false;
    var keys = Object.keys(draft.fields);
    for (var i = 0; i < keys.length; i += 1) {
      if (String(draft.fields[keys[i]] || '').trim()) return true;
    }
    return false;
  }

  function saveDraft() {
    if (!kpiId) return;
    var draft = collectDraft();
    try {
      if (draftHasContent(draft)) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch (e) { /* quota / private mode */ }
  }

  function loadDraft() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var draft = JSON.parse(raw);
      if (draft.ts && (Date.now() - draft.ts) > 14 * 24 * 60 * 60 * 1000) {
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
      return draft;
    } catch (e) {
      return null;
    }
  }

  function clearDraft() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
  }

  function restoreDraft(draft) {
    if (!draft || !draft.fields) return false;
    var changed = false;
    Object.keys(draft.fields).forEach(function (name) {
      var el = form.elements.namedItem(name);
      if (!el) return;
      if (typeof el.length === 'number' && el.tagName !== 'SELECT') {
        el = el[0];
        if (!el) return;
      }
      var val = draft.fields[name];
      if (String(el.value) === String(val)) return;
      el.value = val;
      changed = true;
      if (el.getAttribute && el.getAttribute('data-kpi-rich-input') !== null) {
        var root = el.closest('[data-kpi-rich]');
        var editor = root && root.querySelector('[data-kpi-rich-editor]');
        if (editor) editor.innerHTML = val || '';
      }
    });
    return changed;
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, SAVE_MS);
  }

  function initHScroll() {
    var wrap = document.querySelector('[data-kpi-table-wrap]');
    var topScroll = document.querySelector('[data-kpi-hscroll-top]');
    var spacer = document.querySelector('[data-kpi-hscroll-spacer]');
    if (!wrap || !topScroll || !spacer) return;
    var syncing = false;
    function syncSpacer() {
      var tableEl = wrap.querySelector('[data-kpi-table]');
      spacer.style.width = (tableEl ? tableEl.scrollWidth : wrap.scrollWidth) + 'px';
    }
    topScroll.addEventListener('scroll', function () {
      if (syncing) return;
      syncing = true;
      wrap.scrollLeft = topScroll.scrollLeft;
      syncing = false;
    });
    wrap.addEventListener('scroll', function () {
      if (syncing) return;
      syncing = true;
      topScroll.scrollLeft = wrap.scrollLeft;
      syncing = false;
    });
    syncSpacer();
    window.addEventListener('resize', syncSpacer);
  }

  // Restore draft trước khi tính TP (tiếp tục nhập dở).
  var draft = loadDraft();
  if (draft && draftHasContent(draft)) {
    restoreDraft(draft);
  }

  recalc();
  initHScroll();

  table.addEventListener('input', function (e) {
    if (e.target.matches('[data-kpi-self-score], [data-kpi-mgr-score]')) {
      recalc();
    }
    scheduleSave();
  });
  form.addEventListener('input', scheduleSave);
  form.addEventListener('change', scheduleSave);

  form.addEventListener('submit', function () {
    syncRichEditors();
    clearDraft();
  });

  window.addEventListener('beforeunload', function () {
    saveDraft();
  });
})();
