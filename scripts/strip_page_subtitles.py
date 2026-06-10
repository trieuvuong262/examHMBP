"""Remove guide/warning subtitle lines under page headers."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Entire <p> with jp-hide-mobile-subtitle
P_HIDE = re.compile(r'\n[ \t]*<p[^>]*jp-hide-mobile-subtitle[^>]*>.*?</p>[ \t]*\n', re.DOTALL)

# kho_npl page_header include trailing page_subtitle
INC_SUB = re.compile(
    r"(include 'kho_npl/includes/page_header.html' with page_title='[^']+') page_subtitle='[^']*'"
)

# Instructional subtitle under jp-page-header in kho_npl list/hub pages (single-line <p>)
KHO_NPL_GUIDE = re.compile(
    r'\n[ \t]*<p class="text-muted mb-0(?: small)?">[^<{%][^<]*</p>[ \t]*\n'
)

KHO_NPL_FILES = [
    'kho_npl/templates/kho_npl/disposal_list.html',
    'kho_npl/templates/kho_npl/disposal_form.html',
    'kho_npl/templates/kho_npl/disposal_confirm_cancel.html',
    'kho_npl/templates/kho_npl/transfer_hub.html',
    'kho_npl/templates/kho_npl/transfer_form.html',
    'kho_npl/templates/kho_npl/transfer_confirm_cancel.html',
    'kho_npl/templates/kho_npl/receipt_list.html',
    'kho_npl/templates/kho_npl/receipt_form.html',
    'kho_npl/templates/kho_npl/issue_list.html',
    'kho_npl/templates/kho_npl/issue_form.html',
    'kho_npl/templates/kho_npl/adjustment_list.html',
    'kho_npl/templates/kho_npl/stocktake_list.html',
    'kho_npl/templates/kho_npl/material_list.html',
    'kho_npl/templates/kho_npl/material_form.html',
    'tasks/templates/tasks/recurring_list.html',
    'tasks/templates/tasks/cross_dept_pending.html',
    'tasks/templates/tasks/cross_dept_form.html',
    'tasks/templates/tasks/assign.html',
    'tasks/templates/tasks/project_form.html',
    'documents/templates/documents/admin/hub.html',
    'documents/templates/documents/admin/category_list.html',
    'documents/templates/documents/admin/document_list.html',
    'documents/templates/documents/admin/qa_settings.html',
    'service_requests/templates/service_requests/catalog_list.html',
    'service_requests/templates/service_requests/form.html',
    'equipment/templates/equipment/agent_guide.html',
    'equipment/templates/equipment/it_repair_list.html',
    'templates/training/admin/course_form.html',
]


def strip_file(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    orig = text
    text = P_HIDE.sub('\n', text)
    text = INC_SUB.sub(r'\1', text)
    if str(path.relative_to(ROOT)).replace('\\', '/') in KHO_NPL_FILES:
        text = KHO_NPL_GUIDE.sub('\n', text)
    if text != orig:
        path.write_text(text, encoding='utf-8')
        return True
    return False


def main():
    changed = []
    for path in sorted(ROOT.rglob('*.html')):
        if 'node_modules' in path.parts:
            continue
        if strip_file(path):
            changed.append(str(path.relative_to(ROOT)))
    print(f'Updated {len(changed)} files')
    for p in changed:
        print(f'  {p}')


if __name__ == '__main__':
    main()
