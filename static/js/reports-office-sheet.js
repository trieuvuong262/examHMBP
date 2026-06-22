(function () {
    'use strict';
    const hiddenInput = document.getElementById('id_spreadsheet_data');
    const table = document.getElementById('jpOfficeSheet');
    const form = document.getElementById('office-report-form');
    if (!hiddenInput || !table) return;

    let sheet = { columns: ['', '', ''], rows: [['', '', ''], ['', '', ''], ['', '', ''], ['', '', ''], ['', '', '']] };

    function loadInitial() {
        try {
            const parsed = JSON.parse(hiddenInput.value || '{}');
            if (parsed && Array.isArray(parsed.columns) && Array.isArray(parsed.rows)) {
                sheet.columns = parsed.columns.map(String);
                sheet.rows = parsed.rows.map(function (row) {
                    const cells = Array.isArray(row) ? row.map(String) : [];
                    while (cells.length < sheet.columns.length) cells.push('');
                    return cells.slice(0, sheet.columns.length);
                });
            }
        } catch (e) {}
        if (!sheet.rows.length) {
            sheet.rows = [sheet.columns.map(function () { return ''; })];
        }
    }

    function syncHidden() {
        hiddenInput.value = JSON.stringify(sheet);
    }

    function makeCellInput(value, placeholder, extraClass, onInput) {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'jp-sheet-cell-input' + (extraClass ? ' ' + extraClass : '');
        input.value = value || '';
        if (placeholder) input.placeholder = placeholder;
        input.addEventListener('input', onInput);
        return input;
    }

    function render() {
        table.innerHTML = '';
        const thead = document.createElement('thead');

        const headerRow = document.createElement('tr');
        headerRow.className = 'jp-sheet-header-row';
        const cornerHeader = document.createElement('th');
        cornerHeader.className = 'jp-sheet-corner jp-office-sheet-axis';
        cornerHeader.innerHTML = '<span class="jp-sheet-axis-label">#</span>';
        headerRow.appendChild(cornerHeader);
        sheet.columns.forEach(function (col, colIdx) {
            const th = document.createElement('th');
            th.className = 'jp-sheet-header-cell';
            th.appendChild(makeCellInput(col, 'Tiêu đề cột ' + (colIdx + 1), 'jp-sheet-header-input', function (e) {
                sheet.columns[colIdx] = e.target.value;
                syncHidden();
            }));
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        sheet.rows.forEach(function (row, rowIdx) {
            const tr = document.createElement('tr');
            if (rowIdx % 2 === 1) tr.className = 'jp-sheet-row-alt';
            const rowHead = document.createElement('th');
            rowHead.className = 'jp-sheet-row-num jp-office-sheet-axis';
            rowHead.textContent = String(rowIdx + 1);
            tr.appendChild(rowHead);
            sheet.columns.forEach(function (_col, colIdx) {
                const td = document.createElement('td');
                td.className = 'jp-sheet-data-cell';
                td.appendChild(makeCellInput(row[colIdx], '', '', function (e) {
                    sheet.rows[rowIdx][colIdx] = e.target.value;
                    syncHidden();
                }));
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        syncHidden();
    }

    ['jpSheetAddRow', 'jpSheetRemoveRow', 'jpSheetAddCol', 'jpSheetRemoveCol'].forEach(function (id) {
        document.getElementById(id)?.addEventListener('click', function () {
            if (id === 'jpSheetAddRow') sheet.rows.push(sheet.columns.map(function () { return ''; }));
            if (id === 'jpSheetRemoveRow' && sheet.rows.length > 1) sheet.rows.pop();
            if (id === 'jpSheetAddCol') {
                sheet.columns.push('');
                sheet.rows = sheet.rows.map(function (row) { row.push(''); return row; });
            }
            if (id === 'jpSheetRemoveCol' && sheet.columns.length > 1) {
                sheet.columns.pop();
                sheet.rows = sheet.rows.map(function (row) { row.pop(); return row; });
            }
            render();
        });
    });

    form?.addEventListener('submit', function () { syncHidden(); });

    loadInitial();
    render();
})();
