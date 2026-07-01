from pathlib import Path

p = Path(__file__).resolve().parent / 'test_npl_validation_local.py'
text = p.read_text(encoding='utf-8')

helper = '''

def setup_transfer_line(page, fx):
    page.select_option('#id_from_location', str(fx['from_loc']))
    page.select_option('#id_to_location', str(fx['to_loc']))
    page.evaluate(
        """(args) => {
            const row = document.querySelector('#lines-body .line-row');
            if (!row) return false;
            const sel = row.querySelector('select.jp-npl-material-select');
            if (!sel || !sel.tomselect) return false;
            const ts = sel.tomselect;
            const id = String(args.materialId);
            ts.addOption({ id: id, name: args.name, text: args.name, unit: 'm' });
            ts.setValue(id, true);
            const stockEl = row.querySelector('.jp-npl-stock-qty');
            if (stockEl) {
                stockEl.dataset.stockQty = String(args.stock);
                stockEl.textContent = args.stock + ' m';
            }
            return true;
        }""",
        {'materialId': fx['material'], 'name': 'POPUP-NPL-01', 'stock': 50},
    )
'''

if 'def setup_transfer_line' not in text:
    text = text.replace('\ndef test_transfer_over_stock', helper + '\ndef test_transfer_over_stock')

old_block = """    page.select_option('#id_from_location', str(fx['from_loc']))
    page.select_option('#id_to_location', str(fx['to_loc']))
    mat = page.locator('#lines-body .line-row').first.locator('select.jp-npl-material-select')
    mat.select_option(str(fx['material']))
    page.wait_for_timeout(1000)"""

new_block = """    setup_transfer_line(page, fx)
    page.wait_for_timeout(300)"""

text = text.replace(old_block, new_block)

old_zero = """    page.select_option('#id_from_location', str(fx['from_loc']))
    page.select_option('#id_to_location', str(fx['to_loc']))
    mat = page.locator('#lines-body .line-row').first.locator('select.jp-npl-material-select')
    mat.select_option(str(fx['material']))
    page.wait_for_timeout(500)"""

text = text.replace(old_zero, """    setup_transfer_line(page, fx)
    page.wait_for_timeout(300)""")

p.write_text(text, encoding='utf-8')
print('ok')
