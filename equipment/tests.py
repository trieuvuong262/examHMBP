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
    def test_agent_report_username_fallback_registers_user(self):
        from django.contrib.auth import get_user_model

        from equipment.models import UserAgentRegistration
        from equipment.services.agent_install import user_is_in_equipment_registry

        User = get_user_model()
        user = User.objects.create_user(username='adia', password='x')

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'SN-USER-ONLY',
            'hostname': 'PC-ADIA',
            'username': 'adia',
            'machine_type': 'company',
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(user_is_in_equipment_registry(user))

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_reconcile_registration_by_hostname_cookie(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory
        from django.utils import timezone

        from equipment.models import Device, UserAgentRegistration
        from equipment.services.agent_install import try_reconcile_agent_registration

        User = get_user_model()
        user = User.objects.create_user(username='gate1', password='x')
        other = User.objects.create_user(username='other', password='x')
        device = Device.objects.create(
            serial_number='SN-RECON',
            name='PC',
            hostname='DESKTOP-RECON',
            last_scan_date=timezone.now(),
        )
        UserAgentRegistration.objects.create(
            user=other,
            serial_number='SN-RECON',
            device=device,
        )

        factory = RequestFactory()
        request = factory.get('/thiet-bi/agent/trang-thai/')
        request.user = user
        request.COOKIES = {'jp_hostname': 'DESKTOP-RECON'}

        self.assertTrue(try_reconcile_agent_registration(request))
        self.assertTrue(
            UserAgentRegistration.objects.filter(user=user, serial_number='SN-RECON').exists(),
        )

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_agent_report_with_used_token_still_registers_user(self):
        from django.contrib.auth import get_user_model

        from equipment.models import UserAgentRegistration
        from equipment.services.agent_install import create_install_token

        User = get_user_model()
        user = User.objects.create_user(username='reuse', password='x')
        tok = create_install_token(user)
        tok.mark_used()

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'SN-REUSE-01',
            'hostname': 'PC-REUSE',
            'install_token': tok.token,
            'portal_user_id': user.pk,
            'machine_type': 'company',
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(UserAgentRegistration.objects.filter(user=user, serial_number='SN-REUSE-01').exists())

    @override_settings(EQUIPMENT_AGENT_SECRET='sec')
    def test_personal_agent_report_no_device(self):
        from django.contrib.auth import get_user_model

        from equipment.models import AgentInstallToken, Device, UserAgentRegistration
        from equipment.services.agent_install import (
            MACHINE_TYPE_PERSONAL,
            create_install_token,
            user_is_in_equipment_registry,
        )

        User = get_user_model()
        user = User.objects.create_user(username='homepc', password='x')
        tok = create_install_token(user, machine_type=MACHINE_TYPE_PERSONAL)

        client = __import__('django.test', fromlist=['Client']).Client()
        payload = {
            'api_secret': 'sec',
            'serial': 'PERS-SN-001',
            'hostname': 'HOME-LAPTOP',
            'install_token': tok.token,
            'portal_user_id': user.pk,
            'machine_type': MACHINE_TYPE_PERSONAL,
        }
        resp = client.post(
            '/thiet-bi/api/agent-report/',
            data=__import__('json').dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('personal'))
        self.assertFalse(Device.objects.filter(serial_number='PERS-SN-001').exists())
        reg = UserAgentRegistration.objects.get(user=user, serial_number='PERS-SN-001')
        self.assertIsNone(reg.device_id)
        self.assertTrue(user_is_in_equipment_registry(user))

    @override_settings(
        EQUIPMENT_AGENT_SECRET='sec',
        PORTAL_PUBLIC_BASE_URL='https://portal.example.com',
    )
    def test_installer_cmd_writes_ini_via_base64(self):
        from django.contrib.auth import get_user_model

        from equipment.services.agent_install import (
            MACHINE_TYPE_COMPANY,
            build_agent_ini_content,
            build_installer_cmd,
            create_install_token,
        )

        User = get_user_model()
        user = User.objects.create_user(username='ini_test', password='x')
        profile = getattr(user, 'profile', None)
        if profile:
            profile.job_position = 'Công nhân (may'
            profile.save()
        tok = create_install_token(user, machine_type=MACHINE_TYPE_COMPANY)
        cmd = build_installer_cmd(user=user, token=tok.token, machine_type=MACHINE_TYPE_COMPANY)
        self.assertIn('FromBase64String', cmd)
        self.assertNotIn('; ^', cmd)
        self.assertIn('findstr /C:"install_token="', cmd)

    @override_settings(
        EQUIPMENT_AGENT_SECRET='sec',
        PORTAL_PUBLIC_BASE_URL='https://portal.example.com',
    )
    def test_installer_cmd_includes_machine_type(self):
        from django.contrib.auth import get_user_model

        from equipment.services.agent_install import (
            MACHINE_TYPE_PERSONAL,
            build_installer_cmd,
            create_install_token,
        )

        User = get_user_model()
        user = User.objects.create_user(username='nv02', password='x')
        tok = create_install_token(user, machine_type=MACHINE_TYPE_PERSONAL)
        cmd = build_installer_cmd(user=user, token=tok.token, machine_type=MACHINE_TYPE_PERSONAL)
        self.assertIn('FromBase64String', cmd)
        import base64
        import re

        match = re.search(r"FromBase64String\('([^']+)'\)", cmd)
        self.assertIsNotNone(match)
        ini_text = base64.b64decode(match.group(1)).decode('utf-8')
        self.assertIn('machine_type=personal', ini_text)
        self.assertEqual(tok.machine_type, MACHINE_TYPE_PERSONAL)

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
        self.assertContains(resp, 'dùng chung')
        self.assertContains(resp, 'Xác nhận')
        self.assertContains(resp, 'Máy cá nhân')
        self.assertContains(resp, 'Tải file cài')


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
        self.assertIn('Trạng thái mạng', df_it.columns)
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
