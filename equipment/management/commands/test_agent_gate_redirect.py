from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client

from equipment.services.agent_install import is_agent_install_required, user_is_in_equipment_registry


class Command(BaseCommand):
    help = 'Test redirect agent gate (production smoke test).'

    def handle(self, *args, **options):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username='gate_test_user')
        client = Client()
        client.force_login(user)
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120'
        resp = client.get(
            '/',
            HTTP_USER_AGENT=ua,
            HTTP_HOST='portal.justplay.vn',
            secure=True,
            follow=True,
        )
        chain = getattr(resp, 'redirect_chain', [])
        req = client.request().wsgi_request
        req.user = user
        req.META['HTTP_USER_AGENT'] = ua

        self.stdout.write(f'in_registry={user_is_in_equipment_registry(user)}')
        self.stdout.write(f'install_required={is_agent_install_required(req)}')
        self.stdout.write(f'status={resp.status_code} chain={chain} path={resp.request.get("PATH_INFO", "")}')

        if 'yeu-cau-cai' in resp.request.get('PATH_INFO', '') or any(
            'yeu-cau-cai' in loc for loc, _ in chain
        ):
            self.stdout.write(self.style.SUCCESS('PASS: redirect to gate'))
            return
        if resp.status_code == 302 and 'yeu-cau-cai' in (resp.get('Location') or ''):
            self.stdout.write(self.style.SUCCESS('PASS: redirect to gate'))
            return
        self.stderr.write(self.style.ERROR('FAIL: no gate redirect'))
        raise SystemExit(1)
