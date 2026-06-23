"""Đồng bộ quyền menu Quét thiết bị IT (documents) cho nhóm IT và các nhóm có rustdesk_config."""

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


IT_EMPLOYEE_DOCUMENTS_MENUS = {
    'browse': _perm(view=True),
    'qa': _perm(view=True),
    'rustdesk_config': _perm(view=True, create=True, update=True, export=True),
    'equipment_scan': _perm(view=True, create=True, update=True, export=True),
}

IT_MANAGER_DOCUMENTS_MENUS = {
    'browse': _perm(view=True, create=True, update=True, delete=True),
    'qa': _perm(view=True, create=True, update=True, delete=True),
    'rustdesk_config': _perm(view=True, create=True, update=True, export=True),
    'equipment_scan': _perm(view=True, create=True, update=True, export=True),
}


def sync_equipment_scan_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        slug = (group.slug or '').strip()
        changed = False

        if slug == 'it-nhan-vien':
            documents = dict(perms.get('documents') or {})
            documents['view'] = True
            documents['menus'] = {k: dict(v) for k, v in IT_EMPLOYEE_DOCUMENTS_MENUS.items()}
            perms['documents'] = documents
            changed = True
        elif slug == 'it-truong-phong':
            documents = dict(perms.get('documents') or {})
            documents.update(_perm(view=True, create=True, update=True, delete=True))
            documents['menus'] = {k: dict(v) for k, v in IT_MANAGER_DOCUMENTS_MENUS.items()}
            perms['documents'] = documents
            changed = True
        else:
            documents = dict(perms.get('documents') or {})
            documents_menus = dict(documents.get('menus') or {})
            source = documents_menus.get('rustdesk_config') or documents_menus.get('equipment_scan')
            if source and 'equipment_scan' not in documents_menus:
                documents_menus['equipment_scan'] = dict(source)
                documents['menus'] = documents_menus
                if not documents.get('view'):
                    documents['view'] = bool(source.get('view'))
                perms['documents'] = documents
                changed = True
            elif source and 'rustdesk_config' not in documents_menus:
                documents_menus['rustdesk_config'] = dict(source)
                documents['menus'] = documents_menus
                perms['documents'] = documents
                changed = True

        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0047_equipment_scan_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_equipment_scan_menu_perms, migrations.RunPython.noop),
    ]
