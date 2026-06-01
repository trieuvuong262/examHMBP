(function () {
    function normalizeText(value) {
        return (value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    function getRoot(fieldName) {
        return document.querySelector('.jp-user-picker[data-field-name="' + fieldName + '"]');
    }

    function initPicker(root) {
        const mode = root.dataset.mode || 'multiple';
        const toggle = root.querySelector('.jp-user-picker-toggle');
        const menu = root.querySelector('.jp-user-picker-menu');
        const search = root.querySelector('.jp-user-picker-search');
        const label = root.querySelector('.jp-user-picker-label');
        const chips = root.querySelector('.jp-user-picker-chips');
        const placeholder = label.textContent.trim();
        const options = Array.from(root.querySelectorAll('.jp-user-picker-option'));
        const inputs = options.map(function (opt) { return opt.querySelector('input'); });

        function visibleInputs() {
            return options
                .filter(function (opt) { return !opt.hidden; })
                .map(function (opt) { return opt.querySelector('input'); });
        }

        function selectedInputs() {
            return inputs.filter(function (input) { return input && input.checked; });
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
                const chip = document.createElement('span');
                chip.className = 'badge bg-hm-subtle text-hm border jp-user-picker-chip';
                chip.textContent = name;
                chips.appendChild(chip);
            });
        }

        function filterOptions(query) {
            const q = normalizeText(query.trim());
            options.forEach(function (opt) {
                if (!q) {
                    opt.hidden = false;
                    return;
                }
                const hay = normalizeText(opt.getAttribute('data-search') || '');
                opt.hidden = hay.indexOf(q) === -1;
            });
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

        toggle.addEventListener('click', function () {
            if (menu.hidden) openMenu();
            else closeMenu();
        });

        document.addEventListener('click', function (e) {
            if (!root.contains(e.target)) closeMenu();
        });

        if (search) {
            search.addEventListener('input', function () {
                filterOptions(search.value);
            });
        }

        inputs.forEach(function (input) {
            if (!input) return;
            input.addEventListener('change', function () {
                if (mode === 'single' && input.checked) closeMenu();
                updateLabel();
            });
        });

        const btnAll = root.querySelector('.jp-user-picker-all');
        const btnNone = root.querySelector('.jp-user-picker-none');
        if (btnAll) {
            btnAll.addEventListener('click', function () {
                visibleInputs().forEach(function (input) { input.checked = true; });
                updateLabel();
            });
        }
        if (btnNone) {
            btnNone.addEventListener('click', function () {
                visibleInputs().forEach(function (input) { input.checked = false; });
                updateLabel();
            });
        }

        root._jpUserPickerRefresh = updateLabel;
        updateLabel();
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

    window.JpUserPicker = {
        getRoot: getRoot,
        refresh: refresh,
        setSelected: setSelected,
        selectByFilter: selectByFilter,
        clear: clear,
        initAll: function () {
            document.querySelectorAll('.jp-user-picker').forEach(function (root) {
                if (!root.dataset.jpPickerReady) {
                    root.dataset.jpPickerReady = '1';
                    initPicker(root);
                }
            });
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.JpUserPicker.initAll);
    } else {
        window.JpUserPicker.initAll();
    }
})();
