from django.db import migrations


def seed_department_permission_groups(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    Department = apps.get_model('hrm', 'Department')
    Profile = apps.get_model('hrm', 'Profile')

    from hrm.department_permission_templates import (
        DEPARTMENT_PERMISSION_TEMPLATES,
        department_group_slug,
        default_group_slug_for_profile,
    )

    obsolete_slugs = ('nhan-vien-san-xuat', 'nhan-vien-hcns')
    obsolete_ids = list(
        PermissionGroup.objects.filter(slug__in=obsolete_slugs).values_list('pk', flat=True)
    )
    if obsolete_ids:
        Profile.objects.filter(permission_group_id__in=obsolete_ids).update(permission_group_id=None)
        PermissionGroup.objects.filter(pk__in=obsolete_ids).delete()

    dept_sort = {
        'Tổng giám đốc': 0,
        'ĐẢM BẢO CHẤT LƯỢNG': 1,
        'HÀNH CHÍNH NHÂN SỰ': 2,
        'KẾ HOẠCH SẢN XUẤT': 3,
        'KINH DOANH - MARKETING': 4,
        'R&D': 5,
        'SẢN XUẤT': 6,
        'TÀI CHÍNH KẾ TOÁN': 7,
        'IT': 8,
    }

    for item in DEPARTMENT_PERMISSION_TEMPLATES:
        primary_dept = item['department_names'][0]
        sort = dept_sort.get(primary_dept, 100)
        Department.objects.get_or_create(
            name=primary_dept,
            defaults={'sort_order': sort, 'is_active': True},
        )
        for alias in item['department_names'][1:]:
            Department.objects.get_or_create(
                name=alias,
                defaults={'sort_order': sort, 'is_active': True},
            )

        pairs = (
            ('nhan-vien', item['employee_name'], item['employee']),
            ('truong-phong', item['manager_name'], item['manager']),
        )
        for level, name, perms in pairs:
            PermissionGroup.objects.update_or_create(
                slug=department_group_slug(item['code'], level),
                defaults={
                    'name': name,
                    'description': f'Nhóm quyền mặc định — {name}',
                    'is_system': True,
                    'module_permissions': perms,
                },
            )

    slug_to_id = dict(PermissionGroup.objects.values_list('slug', 'id'))
    for profile in Profile.objects.select_related('department').iterator():
        dept_name = profile.department.name if profile.department_id else ''
        slug = default_group_slug_for_profile(dept_name, profile.role)
        if not slug:
            continue
        group_id = slug_to_id.get(slug)
        if group_id:
            profile.permission_group_id = group_id
            profile.save(update_fields=['permission_group_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0023_permission_groups'),
    ]

    operations = [
        migrations.RunPython(seed_department_permission_groups, noop),
    ]
