(function () {
    function normalizeText(value) {
        return (value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    function initPicker(root) {
        const toggle = root.querySelector('.jp-assignee-picker-toggle');
        const menu = root.querySelector('.jp-assignee-picker-menu');
        const search = root.querySelector('.jp-assignee-picker-search');
        const label = root.querySelector('.jp-assignee-picker-label');
        const chips = root.querySelector('.jp-assignee-picker-chips');
        const options = Array.from(root.querySelectorAll('.jp-assignee-picker-option'));
        const checkboxes = options.map(function (opt) { return opt.querySelector('input[type="checkbox"]'); });

        function visibleCheckboxes() {
            return options
                .filter(function (opt) { return !opt.hidden; })
                .map(function (opt) { return opt.querySelector('input[type="checkbox"]'); });
        }

        function updateLabel() {
            const selected = checkboxes.filter(function (cb) { return cb.checked; });
            if (!selected.length) {
                label.textContent = 'Chọn nhân viên...';
                label.classList.add('text-muted');
            } else if (selected.length === 1) {
                const text = selected[0].closest('.jp-assignee-picker-option').querySelector('strong').textContent;
                label.textContent = text;
                label.classList.remove('text-muted');
            } else {
                label.textContent = 'Đã chọn ' + selected.length + ' nhân viên';
                label.classList.remove('text-muted');
            }

            chips.innerHTML = '';
            selected.forEach(function (cb) {
                const opt = cb.closest('.jp-assignee-picker-option');
                const name = opt.querySelector('strong').textContent;
                const chip = document.createElement('span');
                chip.className = 'badge bg-hm-subtle text-hm border jp-assignee-chip';
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

        checkboxes.forEach(function (cb) {
            cb.addEventListener('change', updateLabel);
        });

        const btnAll = root.querySelector('.jp-assignee-picker-all');
        const btnNone = root.querySelector('.jp-assignee-picker-none');
        if (btnAll) {
            btnAll.addEventListener('click', function () {
                visibleCheckboxes().forEach(function (cb) { cb.checked = true; });
                updateLabel();
            });
        }
        if (btnNone) {
            btnNone.addEventListener('click', function () {
                visibleCheckboxes().forEach(function (cb) { cb.checked = false; });
                updateLabel();
            });
        }

        updateLabel();
    }

    document.querySelectorAll('.jp-assignee-picker').forEach(initPicker);
})();
