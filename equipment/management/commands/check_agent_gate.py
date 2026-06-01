from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Kiểm tra cấu hình agent gate (deploy / debug).'

    def handle(self, *args, **options):
        middleware_ok = 'equipment.middleware.AgentInstallGateMiddleware' in settings.MIDDLEWARE
        self.stdout.write(f'EQUIPMENT_REQUIRE_AGENT_INSTALL={settings.EQUIPMENT_REQUIRE_AGENT_INSTALL}')
        self.stdout.write(f'EQUIPMENT_AGENT_SECRET_SET={bool(settings.EQUIPMENT_AGENT_SECRET)}')
        self.stdout.write(f'EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES={settings.EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES}')
        self.stdout.write(f'PORTAL_PUBLIC_BASE_URL={settings.PORTAL_PUBLIC_BASE_URL}')
        self.stdout.write(f'AGENT_GATE_MIDDLEWARE={middleware_ok}')
        if not settings.EQUIPMENT_REQUIRE_AGENT_INSTALL:
            self.stderr.write(self.style.ERROR('Gate TAT — dat EQUIPMENT_REQUIRE_AGENT_INSTALL=1 trong .env'))
            raise SystemExit(1)
        if not middleware_ok:
            self.stderr.write(self.style.ERROR('Middleware agent gate chua duoc dang ky'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('Agent gate san sang.'))
