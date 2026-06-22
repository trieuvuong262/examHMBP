from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from equipment.services.email_notify import get_it_notify_emails


class ChassisCategoryTests(SimpleTestCase):
    def test_infer_laptop_from_notebook_chassis(self):
        from equipment.services.chassis_category import infer_it_category_from_chassis

        self.assertEqual(infer_it_category_from_chassis([10]), 'Laptop')
        self.assertEqual(infer_it_category_from_chassis([9]), 'Laptop')

    def test_infer_pc_from_desktop_chassis(self):
        from equipment.services.chassis_category import infer_it_category_from_chassis

        self.assertEqual(infer_it_category_from_chassis([3]), 'PC')
        self.assertEqual(infer_it_category_from_chassis([13]), 'PC')

    def test_laptop_wins_when_mixed_with_docking(self):
        from equipment.services.chassis_category import infer_it_category_from_chassis

        self.assertEqual(infer_it_category_from_chassis([12, 3]), 'Laptop')

    def test_parse_chassis_types_string(self):
        from equipment.services.chassis_category import parse_chassis_types

        self.assertEqual(parse_chassis_types('9,10'), [9, 10])


class EmailNotifyTests(SimpleTestCase):
    @override_settings(EQUIPMENT_NOTIFY_EMAILS='a@test.com,b@test.com')
    def test_get_it_notify_emails_from_env(self):
        with patch('service_requests.workflow_it.get_it_department', return_value=None):
            emails = get_it_notify_emails()
        self.assertEqual(emails, ['a@test.com', 'b@test.com'])


class DeviceCategoryTests(SimpleTestCase):
    def test_category_count_excludes_utilities_and_hr(self):
        from equipment.categories import CATEGORY_CHOICES, CATEGORY_GROUP_LABELS

        codes = {c for c, _l, _g in CATEGORY_CHOICES}
        self.assertIn('SEW_LOCKSTITCH', codes)
        self.assertIn('PC', codes)
        self.assertNotIn('utilities', CATEGORY_GROUP_LABELS)
        self.assertNotIn('hr', CATEGORY_GROUP_LABELS)

    def test_normalize_category_alias(self):
        from equipment.categories import normalize_category

        self.assertEqual(normalize_category('Máy tính bàn'), 'PC')
        self.assertEqual(normalize_category('SEW_LOCKSTITCH'), 'SEW_LOCKSTITCH')

    def test_categories_by_group_fallback_without_db_table(self):
        from unittest.mock import patch

        from django.db.utils import ProgrammingError

        from equipment.services import device_categories as svc

        def _fail(*args, **kwargs):
            raise ProgrammingError('relation equipment_devicecategory does not exist')

        with patch.object(
            __import__('equipment.models', fromlist=['DeviceCategory']).DeviceCategory.objects,
            'exists',
            side_effect=_fail,
        ):
            groups = svc.categories_by_group()
        self.assertTrue(groups)
        codes = {code for _g, _l, items in groups for code, _name in items}
        self.assertIn('PC', codes)
        self.assertIn('SEW_LOCKSTITCH', codes)


class ScopeCategoryFilterTests(TestCase):
    def test_it_scope_shows_it_types_when_db_only_has_machine_rows(self):
        """VPS/DB chỉ seed máy xưởng — tab IT vẫn phải có PC, Laptop…"""
        from equipment.models import DeviceCategory
        from equipment.scope import SCOPE_IT
        from equipment.services.scope_ui import categories_by_group_for_scope

        DeviceCategory.objects.all().delete()
        DeviceCategory.objects.create(
            code='SEW_LOCKSTITCH',
            name='Máy may 1 kim',
            group='sewing',
            import_profile='machine',
            is_active=True,
        )
        groups = categories_by_group_for_scope(SCOPE_IT)
        codes = {code for _g, _l, items in groups for code, _name in items}
        self.assertIn('PC', codes)
        self.assertNotIn('SEW_LOCKSTITCH', codes)

    def test_production_scope_uses_machine_types_from_static_when_db_skewed(self):
        from equipment.models import DeviceCategory
        from equipment.scope import SCOPE_PRODUCTION
        from equipment.services.scope_ui import categories_by_group_for_scope

        DeviceCategory.objects.all().delete()
        DeviceCategory.objects.create(
            code='PC',
            name='PC',
            group='it',
            import_profile='it',
            is_active=True,
        )
        groups = categories_by_group_for_scope(SCOPE_PRODUCTION)
        codes = {code for _g, _l, items in groups for code, _name in items}
        self.assertIn('SEW_LOCKSTITCH', codes)
        self.assertNotIn('PC', codes)


class DeviceFormCategoryTests(TestCase):
    def test_it_form_has_no_remote_access_fields(self):
        from equipment.forms import DeviceForm
        from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION

        it_form = DeviceForm(equipment_scope=SCOPE_IT)
        prod_form = DeviceForm(equipment_scope=SCOPE_PRODUCTION)
        for field in (
            'ultraviewer_id', 'ultraviewer_password', 'rustdesk_id', 'rustdesk_password',
        ):
            self.assertNotIn(field, it_form.fields)
            self.assertNotIn(field, prod_form.fields)

    def test_device_form_template_renders_category_options(self):
        from django.template import Context, Template

        from equipment.forms import DeviceForm
        from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION

        snippet = (
            '{% for g, gl, items in form.category.field.grouped_choices %}'
            '{% for val, label in items %}{{ label }};{% endfor %}{% endfor %}'
        )
        tpl = Template(snippet)
        it_html = tpl.render(Context({'form': DeviceForm(equipment_scope=SCOPE_IT)}))
        prod_html = tpl.render(Context({'form': DeviceForm(equipment_scope=SCOPE_PRODUCTION)}))
        self.assertIn('Máy tính bàn (PC)', it_html)
        self.assertNotIn('Máy may 1 kim', it_html)
        self.assertIn('Máy may 1 kim', prod_html)
        self.assertNotIn('Máy tính bàn (PC)', prod_html)

    def test_device_form_save_updates_device(self):
        from equipment.forms import DeviceForm
        from equipment.models import Device
        from hrm.models import Department

        dept, _ = Department.objects.get_or_create(name='Bảo trì xưởng')
        device = Device.objects.create(name='May test', category='SEW_LOCKSTITCH', status=Device.STATUS_ACTIVE)
        form = DeviceForm(
            {
                'device_code': device.device_code,
                'name': 'May test 2',
                'managed_department': dept.pk,
                'category': 'SEW_LOCKSTITCH',
                'usage_department': '',
                'usage_department_text': 'Xưởng A',
                'usage_room': '',
                'assigned_user': '',
                'assigned_user_text': '',
                'handover_date': '',
                'model_number': '',
                'serial_number': 'SN-1',
                'configuration': '',
                'description': '',
                'contact_email': '',
                'status': Device.STATUS_ACTIVE,
                'photo': '',
                'quantity': 1,
                'unit_price': 0,
                'hostname': '',
                'ip_address': '',
            },
            instance=device,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        device.refresh_from_db()
        self.assertEqual(device.name, 'May test 2')
        self.assertTrue(device.qr_code)


class DeviceStatusCrudTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        User = get_user_model()
        self.user = User.objects.create_superuser(username='eq_status_admin', password='x', email='s@test.com')
        self.client = Client(HTTP_HOST='testserver')
        self.client.login(username='eq_status_admin', password='x')

    def test_status_list_and_seed_data(self):
        from django.urls import reverse

        from equipment.models import DeviceStatus

        self.assertGreaterEqual(DeviceStatus.objects.count(), 5)
        response = self.client.get(reverse('equipment:status_list_it'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Đang hoạt động')

    def test_status_form_save_and_delete(self):
        from equipment.forms import DeviceStatusForm
        from equipment.models import DeviceStatus

        form = DeviceStatusForm({
            'code': 'stored',
            'name': 'Lưu kho',
            'sort_order': 50,
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        row = form.save()
        self.assertEqual(row.name, 'Lưu kho')

        row.delete()
        self.assertFalse(DeviceStatus.objects.filter(code='stored').exists())

    def test_status_label_from_db(self):
        from equipment.models import Device, DeviceStatus
        from equipment.services.device_statuses import status_label

        DeviceStatus.objects.update_or_create(
            code='active',
            defaults={'name': 'Hoạt động OK', 'sort_order': 10, 'is_active': True},
        )
        device = Device.objects.create(name='PC', category='PC', status='active')
        self.assertEqual(status_label('active'), 'Hoạt động OK')
        self.assertEqual(device.get_status_display(), 'Hoạt động OK')


class DeviceFormAssigneeTests(TestCase):
    def test_assignee_queryset_prefers_subordinates(self):
        from django.contrib.auth import get_user_model

        from equipment.forms import DeviceForm
        from equipment.services.assignee_users import equipment_assignee_queryset

        User = get_user_model()
        manager = User.objects.create_user(username='mgr_eq', password='x')
        sub = User.objects.create_user(username='sub_eq', password='x')
        User.objects.create_user(username='other_eq', password='x')
        for u, name in ((manager, 'Quản lý'), (sub, 'Cấp dưới')):
            profile = u.profile
            profile.full_name = name
            profile.is_employed = True
            profile.save(update_fields=['full_name', 'is_employed'])
        manager.profile.subordinates.add(sub)

        qs = equipment_assignee_queryset(manager)
        self.assertEqual(list(qs.values_list('username', flat=True)), ['sub_eq'])

        form = DeviceForm(equipment_scope='it', editor_user=manager)
        self.assertEqual(
            list(form.fields['assigned_user'].queryset.values_list('username', flat=True)),
            ['sub_eq'],
        )


class DeviceCodeTests(TestCase):
    def test_auto_generate_device_code(self):
        from equipment.models import Device

        device = Device.objects.create(name='PC A', category='PC', status=Device.STATUS_ACTIVE)
        self.assertTrue(device.device_code.startswith('TB-'))
        second = Device.objects.create(name='PC B', category='PC', status=Device.STATUS_ACTIVE)
        self.assertNotEqual(device.device_code, second.device_code)

    def test_qr_public_by_device_code(self):
        from equipment.models import Device

        device = Device.objects.create(
            name='PC QR',
            device_code='TB-TEST01',
            category='PC',
            status=Device.STATUS_ACTIVE,
        )
        response = self.client.get(f'/thiet-bi/qr/{device.device_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TB-TEST01')


class DeviceImportExportTests(TestCase):
    def test_import_sewing_machine_from_sample(self):
        import io

        from equipment.models import Device
        from equipment.services.import_export import build_sample_dataframe, import_devices_from_excel

        df = build_sample_dataframe('SEW_LOCKSTITCH')
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        count, errors = import_devices_from_excel(buf, 'SEW_LOCKSTITCH')
        self.assertEqual(count, 1)
        self.assertEqual(errors, [])
        device = Device.objects.get()
        self.assertEqual(device.category, 'SEW_LOCKSTITCH')
        self.assertEqual(device.managed_department.name, 'Bảo trì xưởng')

    def test_build_sample_dataframe_for_sample_room_category(self):
        from equipment.services.import_export import build_sample_dataframe

        df = build_sample_dataframe('SAMPLE_SEW')
        self.assertEqual(len(df), 1)
        self.assertIn('Tên thiết bị', df.columns)
        self.assertIn('Máy may mẫu', str(df.iloc[0]['Tên thiết bị']))

    def test_export_respects_category_filter(self):
        from equipment.models import Device
        from equipment.scope import SCOPE_PRODUCTION
        from equipment.services.import_export import devices_to_dataframe

        Device.objects.create(name='PC A', category='PC', status=Device.STATUS_ACTIVE)
        Device.objects.create(name='May B', category='SEW_LOCKSTITCH', status=Device.STATUS_ACTIVE)
        qs = Device.objects.filter(category='SEW_LOCKSTITCH')
        df = devices_to_dataframe(qs, equipment_scope=SCOPE_PRODUCTION)
        self.assertEqual(len(df), 1)
        self.assertIn('Máy may 1 kim', df.iloc[0]['Loại thiết bị'])

    def test_export_columns_differ_by_scope(self):
        from equipment.models import Device
        from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION
        from equipment.services.import_export import devices_to_dataframe

        Device.objects.create(
            name='PC',
            category='PC',
            status=Device.STATUS_ACTIVE,
            hostname='pc-01',
            ip_address='10.0.0.1',
        )
        Device.objects.create(
            name='May',
            category='SEW_LOCKSTITCH',
            status=Device.STATUS_ACTIVE,
            quantity=2,
            unit_price=1000,
        )
        df_it = devices_to_dataframe(Device.objects.filter(category='PC'), equipment_scope=SCOPE_IT)
        df_prod = devices_to_dataframe(
            Device.objects.filter(category='SEW_LOCKSTITCH'),
            equipment_scope=SCOPE_PRODUCTION,
        )
        self.assertIn('Hostname', df_it.columns)
        self.assertIn('Địa chỉ IP', df_it.columns)
        self.assertNotIn('Hostname', df_prod.columns)
        self.assertNotIn('Thành tiền (VNĐ)', df_it.columns)
        self.assertIn('Thành tiền (VNĐ)', df_prod.columns)
        self.assertIn('Thông số kỹ thuật', df_prod.columns)


class ImportExportHubViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_superuser(username='admin', password='x', email='a@test.com')
        self.client = __import__('django.test', fromlist=['Client']).Client()
        self.client.login(username='admin', password='x')

    def test_import_export_hub_import_tab(self):
        resp = self.client.get('/thiet-bi/san-xuat/nhap-xuat/?category=SEW_LOCKSTITCH')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Tải file mẫu Excel')
        self.assertContains(resp, 'SEW_LOCKSTITCH')

    def test_download_sample_for_category_without_preset_row(self):
        resp = self.client.get('/thiet-bi/san-xuat/file-mau/?category=SAMPLE_SEW')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_export_from_device_list_filters(self):
        from equipment.models import Device

        Device.objects.create(name='Test PC', category='PC', status=Device.STATUS_ACTIVE)
        resp = self.client.get('/thiet-bi/it/xuat-excel/?category=PC')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_device_list_scoped_by_category(self):
        from equipment.models import Device

        Device.objects.create(name='PC A', category='PC', status=Device.STATUS_ACTIVE)
        Device.objects.create(
            name='May A',
            category='SEW_LOCKSTITCH',
            status=Device.STATUS_ACTIVE,
        )
        it_resp = self.client.get('/thiet-bi/it/danh-sach/')
        prod_resp = self.client.get('/thiet-bi/san-xuat/danh-sach/')
        self.assertEqual(it_resp.status_code, 200)
        self.assertEqual(prod_resp.status_code, 200)
        self.assertContains(it_resp, 'PC A')
        self.assertNotContains(it_resp, 'May A')
        self.assertContains(prod_resp, 'May A')
        self.assertNotContains(prod_resp, 'PC A')


class DeviceUpdateLogTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_superuser(username='admin', password='x', email='a@test.com')
        self.client = __import__('django.test', fromlist=['Client']).Client()
        self.client.login(username='admin', password='x')

    def test_create_logs_on_device_add(self):
        from equipment.models import Device, DeviceUpdateLog

        resp = self.client.post('/thiet-bi/it/them/', {
            'name': 'PC Test',
            'category': 'PC',
            'status': Device.STATUS_ACTIVE,
            'quantity': 1,
            'unit_price': 0,
        })
        self.assertEqual(resp.status_code, 302)
        device = Device.objects.get(name='PC Test')
        log = DeviceUpdateLog.objects.get(device=device)
        self.assertEqual(log.action, DeviceUpdateLog.ACTION_CREATE)
        self.assertEqual(log.changed_by_id, self.user.pk)

    def test_update_logs_on_device_edit(self):
        from equipment.models import Device, DeviceUpdateLog

        device = Device.objects.create(
            name='PC Old',
            category='PC',
            status=Device.STATUS_ACTIVE,
        )
        resp = self.client.post(f'/thiet-bi/{device.id}/', {
            'name': 'PC New',
            'category': 'PC',
            'status': Device.STATUS_BROKEN,
            'quantity': 1,
            'unit_price': 0,
        })
        self.assertEqual(resp.status_code, 302)
        log = DeviceUpdateLog.objects.filter(device=device, action=DeviceUpdateLog.ACTION_UPDATE).first()
        self.assertIsNotNone(log)
        self.assertIn('Tên', log.summary)
        self.assertIn('Trạng thái', log.summary)

    def test_update_history_page(self):
        from equipment.models import Device
        from equipment.services.device_update_log import log_device_created

        device = Device.objects.create(
            name='PC View',
            category='PC',
            status=Device.STATUS_ACTIVE,
        )
        log_device_created(device, self.user)
        resp = self.client.get(f'/thiet-bi/{device.id}/lich-su-cap-nhat/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Lịch sử cập nhật')
        self.assertContains(resp, 'Tạo thiết bị')


class EquipmentGranularPermissionTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client
        from django.urls import reverse

        from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
        from hrm.module_permissions import MODULE_EQUIPMENT
        from hrm.permissions import ROLE_EMPLOYEE
        from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role

        self.dept = Department.objects.create(name='Equipment Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['equipment'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_EQUIPMENT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-equipment-view',
            name='Equipment view only',
            module_permissions=view_only,
        )

        export_group = dict(base)
        export_group[MODULE_EQUIPMENT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': True,
        }
        self.group_export = PermissionGroup.objects.create(
            slug='test-equipment-export',
            name='Equipment export',
            module_permissions=export_group,
        )

        self.view_user = User.objects.create_user(username='eq_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.export_user = User.objects.create_user(username='eq_export', password='testpass123')
        Profile.objects.filter(user=self.export_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_export,
        )

        from equipment.models import Device

        Device.objects.create(
            name='Export Test PC',
            category='PC',
            status=Device.STATUS_ACTIVE,
        )

        self.client = Client(HTTP_HOST='testserver')
        self.reverse = reverse

    def test_view_only_can_open_device_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(self.reverse('equipment:device_list_it'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_export_devices(self):
        self.client.force_login(self.view_user)
        response = self.client.get(self.reverse('equipment:export_devices_it'))
        self.assertEqual(response.status_code, 302)

    def test_export_user_can_export_devices(self):
        self.client.force_login(self.export_user)
        response = self.client.get(self.reverse('equipment:export_devices_it'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_view_only_cannot_add_device(self):
        self.client.force_login(self.view_user)
        response = self.client.get(self.reverse('equipment:device_add_it'))
        self.assertEqual(response.status_code, 302)


class ProductionLocationTests(TestCase):
    def test_normalize_usage_room_variants(self):
        from equipment.production_locations import (
            LOCATION_6A,
            LOCATION_CHIEN_LUOC,
            normalize_usage_room,
        )

        self.assertEqual(normalize_usage_room('19 Chiến Lược'), LOCATION_CHIEN_LUOC)
        self.assertEqual(normalize_usage_room('19 chien luoc'), LOCATION_CHIEN_LUOC)
        self.assertEqual(normalize_usage_room('152A đường 6A'), LOCATION_6A)
        self.assertEqual(normalize_usage_room('152a duong 6a'), LOCATION_6A)
        self.assertEqual(normalize_usage_room('xyz lung tung'), '')

    def test_normalize_management_command(self):
        from io import StringIO

        from django.core.management import call_command
        from equipment.models import Device

        Device.objects.create(
            name='May 1',
            category='SEW_LOCKSTITCH',
            status=Device.STATUS_ACTIVE,
            usage_room='chien luoc',
        )
        Device.objects.create(
            name='May 2',
            category='SEW_LOCKSTITCH',
            status=Device.STATUS_ACTIVE,
            usage_room='152a',
        )
        call_command('normalize_production_usage_room', '--apply', stdout=StringIO())
        self.assertEqual(Device.objects.get(name='May 1').usage_room, '19 Chiến Lược')
        self.assertEqual(Device.objects.get(name='May 2').usage_room, '152A đường 6A')
