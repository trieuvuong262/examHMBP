(function () {
    function normalizeText(value) {
        return (value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    function getRoot(fieldName) {
        return document.querySelector('.jp-user-picker[data-field-name="' + fieldName + '"]');
    }

    function isOptionVisible(opt) {
        return !opt.hidden && !opt.classList.contains('jp-user-picker-option--hidden');
    }

    function setOptionVisible(opt, visible) {
        opt.hidden = !visible;
        opt.classList.toggle('jp-user-picker-option--hidden', !visible);
    }

    function initPicker(root) {
        const mode = root.dataset.mode || 'multiple';
        const toggle = root.querySelector('.jp-user-picker-toggle');
        const menu = root.querySelector('.jp-user-picker-menu');
        const search = root.querySelector('.jp-user-picker-search');
        const label = root.querySelector('.jp-user-picker-label');
        const chips = root.querySelector('.jp-user-picker-chips');
        const placeholder = label.textContent.trim();

        function getOptions() {
            return Array.from(root.querySelectorAll('.jp-user-picker-option'));
        }

        let options = getOptions();

        function visibleInputs() {
            return getOptions()
                .filter(isOptionVisible)
                .map(function (opt) { return opt.querySelector('input'); });
        }

        function selectedInputs() {
            return getOptions()
                .map(function (opt) { return opt.querySelector('input'); })
                .filter(function (input) { return input && input.checked; });
        }

        function updateLabel() {
            const selected = selectedInputs();
            if (!selected.length) {
                label.textContent = placeholder;
                label.classList.add('text-muted');
            } else if (mode === 'single' || selected.length === 1) {
                const text = selected[0].closest('.jp-user-picker-option').querySelector('strong').textContent;
                label.textContent = text;
                label.classList.remove('text-muted');
            } else {
                label.textContent = 'Đã chọn ' + selected.length + ' nhân viên';
                label.classList.remove('text-muted');
            }

            if (!chips) return;
            chips.innerHTML = '';
            if (mode === 'single') return;
            selected.forEach(function (input) {
                const opt = input.closest('.jp-user-picker-option');
                const name = opt.querySelector('strong').textContent;
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'badge bg-hm-subtle text-hm border jp-user-picker-chip';
                chip.title = 'Bỏ chọn';
                chip.textContent = name + ' ×';
                chip.addEventListener('click', function () {
                    input.checked = false;
                    updateLabel();
                });
                chips.appendChild(chip);
            });
            syncListMeta();
        }

        const filterEmptyEl = root.querySelector('.jp-user-picker-filter-empty');
        const footerEl = root.querySelector('.jp-user-picker-footer');

        function syncListMeta() {
            options = getOptions();
            const visible = options.filter(isOptionVisible);
            if (filterEmptyEl) {
                filterEmptyEl.hidden = visible.length > 0 || options.length === 0;
            }
            if (footerEl) {
                if (!options.length) {
                    footerEl.hidden = true;
                } else {
                    footerEl.hidden = false;
                    const selected = selectedInputs().length;
                    footerEl.textContent = 'Hiển thị ' + visible.length + '/' + options.length
                        + (selected ? ' · Đã chọn ' + selected : '');
                }
            }
        }

        function matchesSearch(haystack, query) {
            const tokens = normalizeText(query).split(/\s+/).filter(Boolean);
            if (!tokens.length) return true;
            return tokens.every(function (token) {
                return haystack.indexOf(token) !== -1;
            });
        }

        function filterOptions(query) {
            options = getOptions();
            const q = (query || '').trim();
            options.forEach(function (opt) {
                const hay = normalizeText(opt.getAttribute('data-search') || '');
                setOptionVisible(opt, matchesSearch(hay, q));
            });
            syncListMeta();
        }

        function openMenu() {
            menu.hidden = false;
            toggle.setAttribute('aria-expanded', 'true');
            if (search) {
                search.value = '';
                filterOptions('');
                search.focus();
            }
        }

        function closeMenu() {
            menu.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
        }

        if (toggle.dataset.jpPickerToggleBound !== '1') {
            toggle.dataset.jpPickerToggleBound = '1';
            toggle.addEventListener('click', function () {
                if (menu.hidden) openMenu();
                else closeMenu();
            });
        }

        if (root.dataset.jpPickerDocBound !== '1') {
            root.dataset.jpPickerDocBound = '1';
            document.addEventListener('click', function (e) {
                if (!root.contains(e.target)) closeMenu();
            });
        }

        function bindOptionInputs() {
            getOptions().forEach(function (opt) {
                const input = opt.querySelector('input');
                if (!input || input.dataset.jpPickerBound) return;
                input.dataset.jpPickerBound = '1';
                input.addEventListener('change', function () {
                    if (mode === 'single' && input.checked) closeMenu();
                    updateLabel();
                });
            });
        }

        if (search) {
            if (search.dataset.jpPickerSearchBound !== '1') {
                search.dataset.jpPickerSearchBound = '1';
                search.addEventListener('input', function () {
                    filterOptions(search.value);
                });
                search.addEventListener('keydown', function (e) {
                    e.stopPropagation();
                });
                search.addEventListener('click', function (e) {
                    e.stopPropagation();
                });
            }
        }

        bindOptionInputs();

        const btnAll = root.querySelector('.jp-user-picker-all');
        const btnNone = root.querySelector('.jp-user-picker-none');
        if (btnAll && btnAll.dataset.jpPickerBtnBound !== '1') {
            btnAll.dataset.jpPickerBtnBound = '1';
            btnAll.addEventListener('click', function () {
                visibleInputs().forEach(function (input) { input.checked = true; });
                updateLabel();
            });
        }
        if (btnNone && btnNone.dataset.jpPickerBtnBound !== '1') {
            btnNone.dataset.jpPickerBtnBound = '1';
            btnNone.addEventListener('click', function () {
                visibleInputs().forEach(function (input) { input.checked = false; });
                updateLabel();
            });
        }

        root._jpUserPickerRefresh = updateLabel;
        root._jpUserPickerFilter = filterOptions;
        root._jpUserPickerRebind = bindOptionInputs;
        updateLabel();
        syncListMeta();
    }

    function initPickerFresh(root) {
        delete root.dataset.jpPickerReady;
        root.querySelectorAll('input[data-jp-picker-bound]').forEach(function (input) {
            delete input.dataset.jpPickerBound;
        });
        const search = root.querySelector('.jp-user-picker-search');
        if (search) delete search.dataset.jpPickerSearchBound;
        initPicker(root);
        root.dataset.jpPickerReady = '1';
    }

    function refresh(fieldName) {
        const root = getRoot(fieldName);
        if (root && typeof root._jpUserPickerRefresh === 'function') {
            root._jpUserPickerRefresh();
        }
    }

    function setSelected(fieldName, userIds, append) {
        const root = getRoot(fieldName);
        if (!root) return 0;
        const mode = root.dataset.mode || 'multiple';
        const idSet = new Set((userIds || []).map(String));
        let added = 0;

        root.querySelectorAll('.jp-user-picker-option').forEach(function (opt) {
            const input = opt.querySelector('input');
            if (!input) return;
            const uid = String(opt.dataset.userId || input.value);
            if (!idSet.has(uid)) return;
            if (mode === 'single') {
                input.checked = true;
                added = 1;
            } else if (!input.checked) {
                input.checked = true;
                added += 1;
            } else if (append) {
                added += 1;
            }
        });

        refresh(fieldName);
        return added;
    }

    function selectByDataAttr(fieldName, attr, value, append) {
        const target = String(value || '');
        return selectByFilter(fieldName, function (opt) {
            return String(opt.getAttribute(attr) || '') === target;
        }, append);
    }

    function selectByFilter(fieldName, filterFn, append) {
        const root = getRoot(fieldName);
        if (!root) return 0;
        const mode = root.dataset.mode || 'multiple';
        let added = 0;

        root.querySelectorAll('.jp-user-picker-option').forEach(function (opt) {
            if (!filterFn(opt)) return;
            const input = opt.querySelector('input');
            if (!input) return;
            if (mode === 'single') {
                input.checked = true;
                added = 1;
            } else if (!input.checked || append) {
                if (!input.checked) added += 1;
                input.checked = true;
            }
        });

        refresh(fieldName);
        return added;
    }

    function clear(fieldName) {
        const root = getRoot(fieldName);
        if (!root) return;
        root.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(function (input) {
            input.checked = false;
        });
        refresh(fieldName);
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function rebuildOptions(fieldName, users, options) {
        const root = getRoot(fieldName);
        if (!root) return;
        const opts = options || {};
        const mode = root.dataset.mode || 'multiple';
        const htmlName = root.dataset.fieldName || fieldName;
        const showOrgMeta = opts.showOrgMeta !== false;
        const selected = new Set((opts.selectedIds || []).map(String));

        root.querySelectorAll('.jp-user-picker-option input:checked').forEach(function (input) {
            selected.add(String(input.value));
        });

        const list = root.querySelector('.jp-user-picker-list');
        if (!list) return;

        let html = '';
        (users || []).forEach(function (user) {
            const userId = String(user.id);
            const checked = selected.has(userId) ? ' checked' : '';
            const metaAttrs = showOrgMeta
                ? ' data-department-id="' + escapeHtml(user.department_id) + '"'
                    + ' data-division-id="' + escapeHtml(user.division_id) + '"'
                : '';
            const orgLine = showOrgMeta && user.department_name
                ? '<span class="d-block">'
                    + (user.division_name ? escapeHtml(user.division_name) + ' · ' : '')
                    + escapeHtml(user.department_name)
                    + '</span>'
                : '';
            const positionPart = user.job_position
                ? ' · ' + escapeHtml(user.job_position)
                : '';
            const inputType = mode === 'single' ? 'radio' : 'checkbox';

            html += '<label class="jp-user-picker-option d-flex align-items-start gap-2"'
                + ' data-user-id="' + escapeHtml(userId) + '"'
                + ' data-role="' + escapeHtml(user.role) + '"'
                + ' data-position="' + escapeHtml(user.job_position) + '"'
                + metaAttrs
                + ' data-search="' + escapeHtml(user.search) + '">'
                + '<input type="' + inputType + '"'
                + ' class="form-check-input mt-1 flex-shrink-0"'
                + ' name="' + escapeHtml(htmlName) + '"'
                + ' value="' + escapeHtml(userId) + '"' + checked + '>'
                + '<span class="flex-grow-1 min-w-0">'
                + '<strong class="jp-text-clamp-1">' + escapeHtml(user.full_name) + '</strong>'
                + '<span class="d-block small text-muted jp-text-clamp-2">'
                + escapeHtml(user.employee_code || '—') + ' · ' + escapeHtml(user.username)
                + positionPart
                + orgLine
                + '</span></span></label>';
        });

        if (!users || !users.length) {
            html += '<p class="text-muted small mb-0 p-3 jp-user-picker-empty">Không có nhân viên nào để chọn.</p>';
        }
        html += '<p class="text-muted small mb-0 p-3 jp-user-picker-filter-empty" hidden>Không có kết quả phù hợp.</p>';
        list.innerHTML = html;
        initPickerFresh(root);
    }

    window.JpUserPicker = {
        getRoot: getRoot,
        refresh: refresh,
        setSelected: setSelected,
        selectByFilter: selectByFilter,
        selectByDataAttr: selectByDataAttr,
        clear: clear,
        rebuildOptions: rebuildOptions,
        initAll: function (force) {
            document.querySelectorAll('.jp-user-picker').forEach(function (root) {
                if (force || !root.dataset.jpPickerReady) {
                    if (force) {
                        initPickerFresh(root);
                    } else {
                        root.dataset.jpPickerReady = '1';
                        initPicker(root);
                    }
                }
            });
        },
        filter: function (fieldName, query) {
            const root = getRoot(fieldName);
            if (root && typeof root._jpUserPickerFilter === 'function') {
                root._jpUserPickerFilter(query);
            }
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.JpUserPicker.initAll);
    } else {
        window.JpUserPicker.initAll();
    }
})();
