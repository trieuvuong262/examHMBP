from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from equipment.services.email_notify import get_it_notify_emails


class AgentCoreTests(SimpleTestCase):
    def test_is_bad_serial(self):
        from equipment.agent.core import is_bad_serial

        self.assertTrue(is_bad_serial('Default string'))
        self.assertTrue(is_bad_serial(None))
        self.assertFalse(is_bad_serial('ABC123456'))


class EmailNotifyTests(SimpleTestCase):
    @override_settings(EQUIPMENT_NOTIFY_EMAILS='a@test.com,b@test.com')
    def test_get_it_notify_emails_from_env(self):
        with patch('service_requests.workflow_it.get_it_department', return_value=None):
            emails = get_it_notify_emails()
        self.assertEqual(emails, ['a@test.com', 'b@test.com'])


class AgentInstallFlowTests(TestCase):
    @override_settings(
        EQUIPMENT_AGENT_SECRET='sec',
        PORTAL_PUBLIC_BASE_URL='https://portal.example.com',
    )
    def test_agent_report_links_user_and_registration(self):
        from django.contrib.auth import get_user_model

        from equipment.models import AgentInstallToken, Device, UserAgentRegistration
        from equipment.services.agent_install import create_install_token

        User = get_user_model()
        user = User.objects.create_user(username='nv01', password='x')
        tok = create_install_token(user)

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'SN123456',
            'hostname': 'PC-NV01',
            'ip': '192.168.1.50',
            'model': 'Dell',
            'cpu': 'i5',
            'ram': '16',
            'disk': '512',
            'install_token': tok.token,
            'portal_user_id': user.pk,
            'full_name': 'Nguyen Van A',
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        device = Device.objects.get(serial_number='SN123456')
        self.assertEqual(device.assigned_user_id, user.pk)
        self.assertTrue(UserAgentRegistration.objects.filter(user=user, serial_number='SN123456').exists())
        tok.refresh_from_db()
        self.assertIsNotNone(tok.used_at)

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_install_status_when_user_in_registry(self):
        from django.contrib.auth import get_user_model

        from equipment.models import Device
        from equipment.services.agent_install import user_is_in_equipment_registry

        User = get_user_model()
        user = User.objects.create_user(username='u2', password='x')
        Device.objects.create(
            serial_number='SN99',
            name='PC',
            assigned_user=user,
            assigned_user_text='u2',
        )
        self.assertTrue(user_is_in_equipment_registry(user))

        client = __import__('django.test', fromlist=['Client']).Client()
        client.force_login(user)
        resp = client.get('/thiet-bi/agent/trang-thai/')
        self.assertTrue(resp.json()['ready'])

    @override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='sec')
    def test_middleware_blocks_superuser_not_admin(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        User = get_user_model()
        user = User.objects.create_superuser(username='itboss', password='x', email='it@test.com')
        client = Client()
        client.force_login(user)
        resp = client.get('/', HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/thiet-bi/agent/yeu-cau-cai', resp.url)

    @override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='sec')
    def test_middleware_skips_admin_username(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        User = get_user_model()
        user = User.objects.create_superuser(username='admin', password='x', email='a@test.com')
        client = Client()
        client.force_login(user)
        resp = client.get('/', HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0')
        self.assertEqual(resp.status_code, 200)

    @override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='sec')
    def test_middleware_redirects_to_gate(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        User = get_user_model()
        user = User.objects.create_user(username='gate_user', password='x')
        client = Client()
        client.force_login(user)
        resp = client.get('/', HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/thiet-bi/agent/yeu-cau-cai', resp.url)

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_middleware_skips_when_user_assigned(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        from equipment.models import Device

        User = get_user_model()
        user = User.objects.create_user(username='assigned', password='x')
        Device.objects.create(serial_number='SN1', name='PC', assigned_user=user)
        client = Client()
        client.force_login(user)
        resp = client.get('/', HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0')
        self.assertEqual(resp.status_code, 200)

    @override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='')
    def test_gate_enabled_without_secret(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory

        from equipment.services.agent_install import is_agent_install_required

        User = get_user_model()
        user = User.objects.create_user(username='gate_only', password='x')
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Windows NT 10.0'
        self.assertTrue(is_agent_install_required(request))

    def test_resolve_serial_fallback_host(self):
        from equipment.agent.core import is_bad_serial, resolve_serial

        with patch('equipment.agent.core.run_powershell', return_value='Default string'):
            with patch('equipment.agent.core.platform.node', return_value='PC-TEST'):
                serial = resolve_serial()
        self.assertEqual(serial, 'HOST-PC-TEST')
        self.assertFalse(is_bad_serial(serial))

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_agent_report_applies_hrm_profile(self):
        from django.contrib.auth import get_user_model

        from equipment.models import Device
        from hrm.models import Department, Profile

        User = get_user_model()
        dept = Department.objects.create(name='Phong IT')
        user = User.objects.create_user(username='vuong', password='x', email='vuong@test.com')
        Profile.objects.filter(user=user).update(
            full_name='Le Nguyen Trieu Vuong',
            department=dept,
            job_title='IT Developer',
            employee_code='NV001',
        )

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'SN-PROFILE-1',
            'hostname': 'DESKTOP-TEST',
            'ip': '192.168.1.29',
            'model': 'H610M',
            'cpu': 'Intel i5',
            'ram': '16',
            'disk': '512',
            'portal_user_id': user.pk,
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        device = Device.objects.get(serial_number='SN-PROFILE-1')
        self.assertEqual(device.usage_department_id, dept.pk)
        self.assertEqual(device.usage_room, 'IT Developer')
        self.assertEqual(device.contact_email, 'vuong@test.com')
        self.assertEqual(device.assigned_user_id, user.pk)

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_agent_poll_api(self):
        from django.test import Client

        client = Client()
        resp = client.get('/thiet-bi/api/agent-poll/?api_secret=wrong')
        self.assertEqual(resp.status_code, 403)
        resp = client.get('/thiet-bi/api/agent-poll/?api_secret=sec')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    @override_settings(
        EQUIPMENT_REQUIRE_AGENT_INSTALL=True,
        EQUIPMENT_AGENT_SECRET='sec',
    )
    def test_confirm_shared_pc_registers_second_user(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        from equipment.models import Device, UserAgentRegistration
        from equipment.services.agent_install import user_is_in_equipment_registry

        User = get_user_model()
        user_a = User.objects.create_user(username='user_a', password='x')
        user_b = User.objects.create_user(username='user_b', password='x')
        device = Device.objects.create(
            serial_number='SN-SHARED-1',
            name='PC-SHARED',
            hostname='DESKTOP-SHARED',
            ip_address='192.168.1.100',
            assigned_user=user_a,
            assigned_user_text='User A',
        )
        UserAgentRegistration.objects.create(
            user=user_a,
            serial_number='SN-SHARED-1',
            device=device,
        )

        client = Client()
        client.force_login(user_b)
        client.cookies['jp_hostname'] = 'DESKTOP-SHARED'
        client.cookies['jp_local_ip'] = '192.168.1.100'
        resp = client.post(
            '/thiet-bi/agent/xac-nhan-chung/',
            HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/')

        device.refresh_from_db()
        self.assertEqual(device.assigned_user_id, user_a.pk)
        self.assertTrue(
            UserAgentRegistration.objects.filter(user=user_b, serial_number='SN-SHARED-1').exists(),
        )
        self.assertTrue(user_is_in_equipment_registry(user_b))
        self.assertEqual(resp.cookies.get('jp_agent_serial').value, 'SN-SHARED-1')

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_agent_report_second_user_keeps_primary_assigned(self):
        from django.contrib.auth import get_user_model

        from equipment.models import Device, UserAgentRegistration

        User = get_user_model()
        user_a = User.objects.create_user(username='primary', password='x')
        user_b = User.objects.create_user(username='secondary', password='x')
        device = Device.objects.create(
            serial_number='SN-SHARED-2',
            name='PC-2',
            assigned_user=user_a,
            assigned_user_text='Primary User',
        )
        UserAgentRegistration.objects.create(
            user=user_a,
            serial_number='SN-SHARED-2',
            device=device,
        )

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'SN-SHARED-2',
            'hostname': 'PC-2',
            'ip': '192.168.1.101',
            'portal_user_id': user_b.pk,
            'full_name': 'Secondary User',
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        device.refresh_from_db()
        self.assertEqual(device.assigned_user_id, user_a.pk)
        self.assertEqual(device.assigned_user_text, 'Primary User')
        self.assertTrue(
            UserAgentRegistration.objects.filter(user=user_b, serial_number='SN-SHARED-2').exists(),
        )

    @override_settings(
        EQUIPMENT_REQUIRE_AGENT_INSTALL=True,
        EQUIPMENT_AGENT_SECRET='sec',
    )
    def test_gate_context_detects_shared_pc(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory

        from equipment.models import Device, UserAgentRegistration
        from equipment.services.shared_pc import get_shared_pc_context_for_gate

        User = get_user_model()
        user_a = User.objects.create_user(username='owner', password='x')
        user_b = User.objects.create_user(username='guest', password='x')
        device = Device.objects.create(
            serial_number='SN-DETECT',
            name='PC-DETECT',
            hostname='DESKTOP-DETECT',
            ip_address='10.0.0.50',
            assigned_user=user_a,
        )
        UserAgentRegistration.objects.create(
            user=user_a,
            serial_number='SN-DETECT',
            device=device,
        )

        factory = RequestFactory()
        request = factory.get('/thiet-bi/agent/yeu-cau-cai/')
        request.user = user_b
        request.COOKIES = {'jp_hostname': 'DESKTOP-DETECT', 'jp_local_ip': '10.0.0.50'}

        ctx = get_shared_pc_context_for_gate(request, user_b)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx['device'].pk, device.pk)
        self.assertTrue(ctx['can_confirm_shared'])

        client = Client()
        client.force_login(user_b)
        client.cookies['jp_hostname'] = 'DESKTOP-DETECT'
        client.cookies['jp_local_ip'] = '10.0.0.50'
        resp = client.get(
            '/thiet-bi/agent/yeu-cau-cai/',
            HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'PC dùng chung')
        self.assertContains(resp, 'Xác nhận')
        self.assertNotContains(resp, 'Hướng dẫn cài (3 bước)')
        self.assertNotContains(resp, 'Tải file cài')


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


class DeviceFormCategoryTests(TestCase):
    def test_device_form_save_updates_device(self):
        from equipment.forms import DeviceForm
        from equipment.models import Device

        device = Device.objects.create(name='May test', category='SEW_LOCKSTITCH', status=Device.STATUS_ACTIVE)
        form = DeviceForm(
            {
                'device_code': device.device_code,
                'name': 'May test 2',
                'managed_by': Device.MANAGED_MAINTENANCE,
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
        self.assertEqual(device.managed_by, Device.MANAGED_MAINTENANCE)

    def test_build_sample_dataframe_for_sample_room_category(self):
        from equipment.services.import_export import build_sample_dataframe

        df = build_sample_dataframe('SAMPLE_SEW')
        self.assertEqual(len(df), 1)
        self.assertIn('Tên thiết bị', df.columns)
        self.assertIn('Máy may mẫu', str(df.iloc[0]['Tên thiết bị']))

    def test_export_respects_category_filter(self):
        from equipment.models import Device
        from equipment.services.import_export import devices_to_dataframe

        Device.objects.create(name='PC A', category='PC', status=Device.STATUS_ACTIVE)
        Device.objects.create(name='May B', category='SEW_LOCKSTITCH', status=Device.STATUS_ACTIVE)
        qs = Device.objects.filter(category='SEW_LOCKSTITCH')
        df = devices_to_dataframe(qs)
        self.assertEqual(len(df), 1)
        self.assertIn('Máy may 1 kim', df.iloc[0]['Loại thiết bị'])


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

    def test_device_list_scoped_by_managed_by(self):
        from equipment.models import Device

        Device.objects.create(name='PC A', category='PC', managed_by=Device.MANAGED_IT, status=Device.STATUS_ACTIVE)
        Device.objects.create(
            name='May A',
            category='SEW_LOCKSTITCH',
            managed_by=Device.MANAGED_MAINTENANCE,
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
