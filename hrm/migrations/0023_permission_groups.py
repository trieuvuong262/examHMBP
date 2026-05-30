from django.db import migrations, models
import django.db.models.deletion


def seed_permission_groups(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    Profile = apps.get_model('hrm', 'Profile')

    role_groups = [
        ('mac-dinh-nhan-vien', 'Mặc định — Nhân viên', 'EMPLOYEE', True),
        ('mac-dinh-to-truong', 'Mặc định — Tổ trưởng', 'TEAM_LEADER', True),
        ('mac-dinh-truong-bo-phan', 'Mặc định — Trưởng bộ phận', 'DIVISION_HEAD', True),
        ('mac-dinh-giam-doc', 'Mặc định — Giám đốc', 'DIRECTOR', True),
    ]

    def to_five_flags(entry):
        if not isinstance(entry, dict):
            entry = {}
        if any(k in entry for k in ('view', 'create', 'update', 'delete', 'export')):
            view = bool(entry.get('view', False))
            create = bool(entry.get('create', False))
            update = bool(entry.get('update', False))
            delete = bool(entry.get('delete', False))
            export = bool(entry.get('export', False))
        else:
            view = bool(entry.get('view', False))
            edit = bool(entry.get('edit', False))
            if edit:
                view = True
            create = update = delete = export = edit
        if any((create, update, delete, export)):
            view = True
        return {
            'view': view,
            'create': create,
            'update': update,
            'delete': delete,
            'export': export,
        }

    role_to_group_id = {}
    for slug, name, role, is_system in role_groups:
        legacy = {}
        try:
            row = RoleModulePermission.objects.get(role=role)
            legacy = row.module_permissions or {}
        except RoleModulePermission.DoesNotExist:
            pass

        module_permissions = {
            module_key: to_five_flags(legacy.get(module_key, {}))
            for module_key in (
                'announcements', 'recruitment', 'training', 'assessment', 'hrm', 'kpi',
                'reports', 'guide', 'documents', 'permissions', 'audit', 'tasks', 'service_requests',
            )
        }
        group, _ = PermissionGroup.objects.update_or_create(
            slug=slug,
            defaults={
                'name': name,
                'description': f'Mặc định cho vai trò {role}',
                'is_system': is_system,
                'module_permissions': module_permissions,
            },
        )
        role_to_group_id[role] = group.pk

    # Nhóm mẫu: NV sản xuất vs NV HCNS
    employee_legacy = {}
    try:
        employee_legacy = RoleModulePermission.objects.get(role='EMPLOYEE').module_permissions or {}
    except RoleModulePermission.DoesNotExist:
        pass

    sx_perms = {k: to_five_flags(v) for k, v in employee_legacy.items()}
    PermissionGroup.objects.update_or_create(
        slug='nhan-vien-san-xuat',
        defaults={
            'name': 'Nhân viên sản xuất',
            'description': 'Không truy cập Nhân sự, Tuyển dụng, Phân quyền.',
            'is_system': False,
            'module_permissions': sx_perms,
        },
    )

    hcns_perms = {k: to_five_flags(v) for k, v in employee_legacy.items()}
    hrm = hcns_perms.get('hrm', to_five_flags({}))
    hrm.update({'view': True, 'create': True, 'update': True, 'delete': True, 'export': True})
    hcns_perms['hrm'] = hrm
    rec = hcns_perms.get('recruitment', to_five_flags({}))
    rec.update({'view': True, 'create': True, 'update': True, 'delete': False, 'export': True})
    hcns_perms['recruitment'] = rec
    PermissionGroup.objects.update_or_create(
        slug='nhan-vien-hcns',
        defaults={
            'name': 'Nhân viên HCNS',
            'description': 'Quyền Nhân sự & Tuyển dụng — dành phòng HCNS.',
            'is_system': False,
            'module_permissions': hcns_perms,
        },
    )

    for profile in Profile.objects.all().iterator():
        if profile.permission_group_id:
            continue
        group_id = role_to_group_id.get(profile.role)
        if group_id:
            profile.permission_group_id = group_id
            profile.save(update_fields=['permission_group_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0022_add_service_requests_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissionGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='Tên nhóm')),
                ('slug', models.SlugField(max_length=120, unique=True, verbose_name='Mã nhóm')),
                ('description', models.TextField(blank=True, verbose_name='Mô tả')),
                ('is_system', models.BooleanField(default=False, help_text='Không xóa được — dùng làm mặc định theo vai trò.', verbose_name='Nhóm hệ thống')),
                ('module_permissions', models.JSONField(blank=True, default=dict, help_text='JSON: {module: {view, create, update, delete, export}}', verbose_name='Quyền theo module')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Nhóm quyền',
                'verbose_name_plural': 'Nhóm quyền',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='profile',
            name='permission_group',
            field=models.ForeignKey(blank=True, help_text='Quyền chi tiết theo module — ưu tiên hơn mặc định vai trò.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='profiles', to='hrm.permissiongroup', verbose_name='Nhóm quyền'),
        ),
        migrations.RunPython(seed_permission_groups, noop),
    ]
