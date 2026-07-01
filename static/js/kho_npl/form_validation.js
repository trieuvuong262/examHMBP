(function () {
    'use strict';

    var MODAL_ID = 'jpNplValidationModal';
    var FORM_SELECTOR = 'form.jp-npl-validated-form, form.jp-npl-doc-form';
    var DEFAULT_TITLE = 'Thiếu thông tin bắt buộc';
    var DEFAULT_HINT = 'Vui lòng bổ sung các trường sau trước khi lưu.';

    function cleanLabel(text) {
        return (text || '').replace(/\*/g, '').replace(/\s+/g, ' ').trim();
    }

    function findControl(container) {
        if (!container) return null;
        return container.querySelector(
            'select.jp-npl-material-select, select.form-select, select, '
            + 'textarea, input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])'
        );
    }

    function findControlForError(errorEl, form) {
        if (!errorEl) return null;
        var listEl = errorEl.querySelector('.errorlist[id], [id$="_error"]');
        if (!listEl && errorEl.id && errorEl.id.indexOf('_error') === errorEl.id.length - 6) {
            listEl = errorEl;
        }
        if (listEl && listEl.id && listEl.id.slice(-6) === '_error') {
            var fieldId = listEl.id.slice(0, -6);
            var scope = form || errorEl.closest('form');
            if (scope && fieldId) {
                var byId = scope.querySelector('#' + CSS.escape(fieldId));
                if (byId) return byId;
            }
        }
        var container = errorEl.parentElement;
        var control = findControl(container);
        if (control) return control;
        if (container && container.parentElement) {
            control = findControl(container.parentElement);
            if (control) return control;
        }
        return null;
    }

    function resolveLabel(control, errorEl) {
        if (control && control.id) {
            var byFor = document.querySelector('label[for="' + CSS.escape(control.id) + '"]');
            if (byFor) return cleanLabel(byFor.textContent);
        }
        var td = errorEl.closest('td');
        if (td) {
            var tr = td.closest('tr');
            var table = td.closest('table');
            if (tr && table && table.tHead && table.tHead.rows.length) {
                var idx = Array.prototype.indexOf.call(tr.cells, td);
                var th = table.tHead.rows[0].cells[idx];
                if (th) {
                    var label = cleanLabel(th.textContent);
                    var tbody = table.tBodies[0];
                    if (tbody && tbody.rows.length > 1) {
                        var rowIdx = Array.prototype.indexOf.call(tbody.rows, tr) + 1;
                        label += ' (dòng ' + rowIdx + ')';
                    }
                    return label;
                }
            }
        }
        var col = errorEl.closest('[class*="col-"]');
        if (col) {
            var colLabel = col.querySelector('label.form-label, label.form-check-label, label');
            if (colLabel) return cleanLabel(colLabel.textContent);
        }
        if (control && control.name) {
            return control.name.replace(/^.*-/, '').replace(/_/g, ' ');
        }
        return 'Trường';
    }

    function markTableCellInvalid(control) {
        if (!control) return;
        var td = control.closest('td');
        if (!td) return;
        td.classList.add('jp-npl-cell-invalid');
        var tr = td.closest('tr');
        var table = td.closest('table');
        if (tr && table && table.tHead && table.tHead.rows.length) {
            var idx = Array.prototype.indexOf.call(tr.cells, td);
            var th = table.tHead.rows[0].cells[idx];
            if (th) th.classList.add('jp-npl-label-invalid');
        }
    }

    function clearTableCellInvalid(control) {
        if (!control) return;
        var td = control.closest('td');
        if (!td) return;
        td.classList.remove('jp-npl-cell-invalid');
        var tr = td.closest('tr');
        var table = td.closest('table');
        if (tr && table && table.tHead && table.tHead.rows.length) {
            var idx = Array.prototype.indexOf.call(tr.cells, td);
            var th = table.tHead.rows[0].cells[idx];
            if (th) th.classList.remove('jp-npl-label-invalid');
        }
    }

    function findTomSelectWrapper(control) {
        if (!control) return null;
        var wrapper = control.closest('.ts-wrapper');
        if (wrapper) return wrapper;
        if (control.tomselect && control.tomselect.wrapper) {
            return control.tomselect.wrapper;
        }
        var sibling = control.previousElementSibling;
        if (sibling && sibling.classList && sibling.classList.contains('ts-wrapper')) {
            return sibling;
        }
        sibling = control.nextElementSibling;
        if (sibling && sibling.classList && sibling.classList.contains('ts-wrapper')) {
            return sibling;
        }
        var parent = control.parentElement;
        if (parent) {
            wrapper = parent.querySelector('.ts-wrapper');
            if (wrapper) return wrapper;
        }
        return null;
    }

    function markInvalid(control, errorEl) {
        if (control) {
            control.classList.add('is-invalid');
            control.setAttribute('aria-invalid', 'true');
            var wrapper = findTomSelectWrapper(control);
            if (wrapper) {
                wrapper.classList.add('is-invalid');
                var tsControl = wrapper.querySelector('.ts-control');
                if (tsControl) tsControl.classList.add('is-invalid');
            }
            if (control.id) {
                var label = document.querySelector('label[for="' + CSS.escape(control.id) + '"]');
                if (label) label.classList.add('jp-npl-label-invalid');
            }
            markTableCellInvalid(control);
        }
        var td = errorEl && errorEl.closest('td');
        if (td) {
            var tr = td.closest('tr');
            var table = td.closest('table');
            if (tr && table && table.tHead && table.tHead.rows.length) {
                var idx = Array.prototype.indexOf.call(tr.cells, td);
                var th = table.tHead.rows[0].cells[idx];
                if (th) th.classList.add('jp-npl-label-invalid');
            }
            td.classList.add('jp-npl-cell-invalid');
        }
        var col = errorEl && errorEl.closest('[class*="col-"]');
        if (col) {
            var colLabel = col.querySelector('label');
            if (colLabel) colLabel.classList.add('jp-npl-label-invalid');
        }
    }

    function collectFormErrors(form) {
        var items = [];
        var seen = Object.create(null);

        form.querySelectorAll('.alert.alert-danger').forEach(function (alert) {
            if (alert.closest('.modal') || alert.closest('#' + MODAL_ID)) return;
            var text = cleanLabel(alert.textContent);
            if (!text || seen['__alert__' + text]) return;
            seen['__alert__' + text] = true;
            items.push({ label: text, errorEl: alert, isAlert: true });
        });

        form.querySelectorAll('.text-danger.small').forEach(function (errorEl) {
            if (errorEl.closest('.modal') || errorEl.closest('#' + MODAL_ID)) return;
            if (errorEl.classList.contains('jp-npl-inline-error-hidden')) return;
            var msg = cleanLabel(errorEl.textContent);
            if (!msg) return;
            var control = findControlForError(errorEl, form);
            var label = resolveLabel(control, errorEl);
            var key = label + '|' + msg;
            if (seen[key]) return;
            seen[key] = true;
            items.push({ label: label, errorEl: errorEl, control: control, isAlert: false });
        });

        return items;
    }

    function hideInlineErrors(items) {
        items.forEach(function (item) {
            if (item.errorEl) item.errorEl.classList.add('jp-npl-inline-error-hidden');
        });
    }

    function showValidationPopup(options) {
        options = options || {};
        var items = options.items || [];
        if (!items.length) return;

        var modalEl = document.getElementById(MODAL_ID);
        if (!modalEl) return;

        var titleEl = modalEl.querySelector('.jp-npl-validation-title-text');
        if (titleEl) {
            titleEl.textContent = options.title || DEFAULT_TITLE;
        }

        var hintEl = modalEl.querySelector('.jp-npl-validation-hint');
        if (hintEl) {
            var hint = options.hint;
            if (hint === false || hint === null || hint === '') {
                hintEl.classList.add('d-none');
            } else {
                hintEl.textContent = hint || DEFAULT_HINT;
                hintEl.classList.remove('d-none');
            }
        }

        var listEl = modalEl.querySelector('.jp-npl-validation-list');
        if (!listEl) return;
        listEl.innerHTML = '';
        items.forEach(function (label) {
            var li = document.createElement('li');
            li.className = 'jp-npl-validation-list-item';
            li.textContent = cleanLabel(label);
            listEl.appendChild(li);
        });

        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        } else {
            modalEl.classList.add('show');
            modalEl.style.display = 'block';
        }
    }

    function bindValidationModal() {
        var modalEl = document.getElementById(MODAL_ID);
        if (!modalEl || modalEl.dataset.jpNplModalBound === '1') return;
        modalEl.dataset.jpNplModalBound = '1';
        modalEl.addEventListener('hidden.bs.modal', function () {
            document.querySelectorAll(FORM_SELECTOR).forEach(function (form) {
                if (form.classList.contains('d-inline') || form.closest('.jp-npl-transfer-row-actions')) return;
                refreshFormInvalidMarks(form);
            });
            document.dispatchEvent(new CustomEvent('jp-npl-validation-modal-hidden'));
        });
    }

    function refreshFormInvalidMarks(form) {
        if (!form) return;
        form.querySelectorAll('.text-danger.small.jp-npl-inline-error-hidden').forEach(function (errorEl) {
            var control = findControlForError(errorEl, form);
            if (control) markInvalid(control, errorEl);
        });
    }

    function processForm(form) {
        var items = collectFormErrors(form);
        if (!items.length) return;
        hideInlineErrors(items);
        items.forEach(function (item) {
            if (!item.isAlert) markInvalid(item.control, item.errorEl);
        });
        showValidationPopup({
            items: items.map(function (item) { return item.label; }),
            title: DEFAULT_TITLE,
            hint: DEFAULT_HINT,
        });
        var firstControl = items.find(function (item) { return item.control; });
        if (firstControl && firstControl.control) {
            try { firstControl.control.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
        }
    }

    function init() {
        if (!document.getElementById(MODAL_ID)) return;
        bindValidationModal();
        window.setTimeout(function () {
            document.querySelectorAll(FORM_SELECTOR).forEach(function (form) {
                if (form.classList.contains('d-inline') || form.closest('.jp-npl-transfer-row-actions')) return;
                processForm(form);
            });
        }, 0);
    }

    window.jpNplValidationPopup = {
        show: showValidationPopup,
        refreshFormMarks: refreshFormInvalidMarks,
        markQtyInvalid: function (input) {
            if (!input) return;
            input.classList.add('is-invalid', 'jp-npl-qty-invalid');
            input.setAttribute('aria-invalid', 'true');
            markTableCellInvalid(input);
        },
        clearQtyInvalid: function (input) {
            if (!input) return;
            input.classList.remove('is-invalid', 'jp-npl-qty-invalid');
            input.removeAttribute('aria-invalid');
            clearTableCellInvalid(input);
        },
        qtyColumnLabel: function (input) {
            if (!input) return 'Số lượng';
            var td = input.closest('td');
            if (!td) return 'Số lượng';
            var tr = td.closest('tr');
            var table = td.closest('table');
            if (tr && table && table.tHead && table.tHead.rows.length) {
                var idx = Array.prototype.indexOf.call(tr.cells, td);
                var th = table.tHead.rows[0].cells[idx];
                var label = th ? cleanLabel(th.textContent) : 'Số lượng';
                var tbody = table.tBodies[0];
                if (tbody && tbody.rows.length > 1) {
                    var rowIdx = Array.prototype.indexOf.call(tbody.rows, tr) + 1;
                    label += ' (dòng ' + rowIdx + ')';
                }
                return label;
            }
            return 'Số lượng';
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
