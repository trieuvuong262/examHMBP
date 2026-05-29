(function () {
    'use strict';

    document.querySelectorAll('[data-doc-tree-toggle]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var group = btn.closest('.jp-doc-tree-group');
            if (!group) return;
            var isOpen = group.classList.toggle('is-open');
            btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });
    });

    var activeItem = document.querySelector('.jp-doc-tree-item.is-active');
    if (activeItem) {
        var openGroup = activeItem.closest('.jp-doc-tree-group');
        if (openGroup) {
            openGroup.classList.add('is-open');
            var toggle = openGroup.querySelector('[data-doc-tree-toggle]');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }
        if (window.matchMedia('(max-width: 991.98px)').matches) {
            activeItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }
})();
