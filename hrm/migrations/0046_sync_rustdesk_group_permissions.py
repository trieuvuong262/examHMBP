"""Đồng bộ quyền RustDesk sau khi tách menu Cấu hình / Quản lý."""

from django.db import migrations


def _perm(view=False, create=False, update=False, delete=False, export=False):
    if any((create, update, delete, export)):
        view = True
    return {
        'view': bool(view),
        'create': bool(create),
        'update': bool(update),
        'delete': bool(delete),
        'export': bool(export),
    }


IT_EMPLOYEE_AUDIT_MENUS = {
    'login_security': _perm(view=True),
    'logs': _perm(view=True),
    'rustdesk': _perm(view=True, create=True, update=True, export=True),
    'backup': _perm(view=True),
    'kiotviet_sync': _perm(view=True),
    'nas_links': _perm(view=True),
    'qa_assistant': _perm(view=True),
}

IT_MANAGER_AUDIT_MENUS = {
    'login_security': _perm(view=True, create=True, update=True, delete=True, export=True),
    'logs': _perm(view=True, export=True),
    'rustdesk': _perm(view=True, create=True, update=True, delete=True, export=True),
    'backup': _perm(view=True, create=True, update=True, delete=True, export=True),
    'kiotviet_sync': _perm(view=True, create=True, update=True, delete=True, export=True),
    'nas_links': _perm(view=True, create=True, update=True, delete=True, export=True),
    'qa_assistant': _perm(view=True, create=True, update=True, delete=True, export=True),
}

IT_EMPLOYEE_DOCUMENTS_MENUS = {
    'browse': _perm(view=True),
    'qa': _perm(view=True),
    'rustdesk_config': _perm(view=True, create=True, update=True, export=True),
}

IT_MANAGER_DOCUMENTS_MENUS = {
    'browse': _perm(view=True, create=True, update=True, delete=True),
    'qa': _perm(view=True, create=True, update=True, delete=True),
    'rustdesk_config': _perm(view=True, create=True, update=True, export=True),
}


def sync_rustdesk_group_permissions(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        slug = (group.slug or '').strip()
        changed = False

        if slug == 'it-nhan-vien':
            audit = dict(perms.get('audit') or {})
            audit['view'] = True
            audit['menus'] = {k: dict(v) for k, v in IT_EMPLOYEE_AUDIT_MENUS.items()}
            perms['audit'] = audit
            documents = dict(perms.get('documents') or {})
            documents['view'] = True
            documents['menus'] = {k: dict(v) for k, v in IT_EMPLOYEE_DOCUMENTS_MENUS.items()}
            perms['documents'] = documents
            changed = True
        elif slug == 'it-truong-phong':
            audit = dict(perms.get('audit') or {})
            audit.update(_perm(view=True, export=True))
            audit['menus'] = {k: dict(v) for k, v in IT_MANAGER_AUDIT_MENUS.items()}
            perms['audit'] = audit
            documents = dict(perms.get('documents') or {})
            documents.update(_perm(view=True, create=True, update=True, delete=True))
            documents['menus'] = {k: dict(v) for k, v in IT_MANAGER_DOCUMENTS_MENUS.items()}
            perms['documents'] = documents
            changed = True
        else:
            audit = dict(perms.get('audit') or {})
            audit_menus = dict(audit.get('menus') or {})
            rustdesk = audit_menus.get('rustdesk')
            if rustdesk:
                documents = dict(perms.get('documents') or {})
                documents_menus = dict(documents.get('menus') or {})
                if 'rustdesk_config' not in documents_menus:
                    documents_menus['rustdesk_config'] = dict(rustdesk)
                    documents['menus'] = documents_menus
                    if not documents.get('view'):
                        documents['view'] = bool(rustdesk.get('view'))
                    perms['documents'] = documents
                    changed = True

        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0045_rustdesk_config_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_rustdesk_group_permissions, migrations.RunPython.noop),
    ]
