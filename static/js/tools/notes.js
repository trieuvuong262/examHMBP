(function () {
    const grid = document.getElementById('notes-grid');
    if (!grid) {
        return;
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

    function headers(json) {
        const base = { 'X-CSRFToken': csrfToken };
        if (json) {
            base['Content-Type'] = 'application/json';
        }
        return base;
    }

    function cardColorClass(color) {
        return 'jp-note-card--' + color;
    }

    function updateCardColor(card, color) {
        card.classList.remove('jp-note-card--yellow', 'jp-note-card--blue', 'jp-note-card--green', 'jp-note-card--pink', 'jp-note-card--gray');
        card.classList.add(cardColorClass(color));
    }

    function showSaved(card, text) {
        const el = card.querySelector('.jp-note-saved');
        if (el) {
            el.textContent = text;
            window.setTimeout(function () {
                if (el.textContent === text) {
                    el.textContent = '';
                }
            }, 2000);
        }
    }

    async function saveNote(card) {
        const id = card.dataset.noteId;
        const payload = {
            title: card.querySelector('.jp-note-title')?.value || '',
            content: card.querySelector('.jp-note-content')?.value || '',
            color: card.querySelector('.jp-note-color')?.value || 'yellow',
        };

        const response = await fetch('/cong-cu/api/ghi-chu/' + id + '/', {
            method: 'PATCH',
            headers: headers(true),
            body: JSON.stringify(payload),
            credentials: 'same-origin',
        });

        if (!response.ok) {
            showSaved(card, 'Lỗi lưu');
            return;
        }

        const data = await response.json();
        updateCardColor(card, data.note.color);
        showSaved(card, 'Đã lưu');
    }

    function debounce(fn, delay) {
        let timer;
        return function () {
            const args = arguments;
            const ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(ctx, args);
            }, delay);
        };
    }

    grid.querySelectorAll('.jp-note-card').forEach(function (card) {
        const debouncedSave = debounce(function () {
            saveNote(card);
        }, 600);

        card.querySelector('.jp-note-title')?.addEventListener('input', debouncedSave);
        card.querySelector('.jp-note-content')?.addEventListener('input', debouncedSave);
        card.querySelector('.jp-note-color')?.addEventListener('change', function () {
            updateCardColor(card, this.value);
            saveNote(card);
        });

        card.querySelector('.jp-note-delete')?.addEventListener('click', async function () {
            if (!window.confirm('Xóa ghi chú này?')) {
                return;
            }
            const id = card.dataset.noteId;
            const response = await fetch('/cong-cu/api/ghi-chu/' + id + '/', {
                method: 'DELETE',
                headers: headers(false),
                credentials: 'same-origin',
            });
            if (response.ok) {
                card.remove();
            }
        });
    });
})();
