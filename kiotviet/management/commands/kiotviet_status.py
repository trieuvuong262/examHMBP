"""Kiểm tra cấu hình KiotViet trong container/VPS.

Usage:
    python manage.py kiotviet_status
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from kiotviet.access import kiotviet_is_live, user_can_use_kiotviet
from kiotviet.client import KiotVietClient
from kiotviet.mirror import mirror_enabled, mirror_summary, sync_states


class Command(BaseCommand):
    help = 'Hiển thị trạng thái cấu hình KiotViet (menu & API)'

    def handle(self, *args, **options):
        enabled = getattr(settings, 'KIOTVIET_ENABLED', False)
        retailer = (getattr(settings, 'KIOTVIET_RETAILER', '') or '').strip()
        client_id = (getattr(settings, 'KIOTVIET_CLIENT_ID', '') or '').strip()
        has_secret = bool((getattr(settings, 'KIOTVIET_CLIENT_SECRET', '') or '').strip())

        self.stdout.write('=== KiotViet portal ===')
        self.stdout.write(f'KIOTVIET_ENABLED     = {enabled}')
        self.stdout.write(f'KIOTVIET_RETAILER    = {retailer or "(trống)"}')
        self.stdout.write(f'KIOTVIET_CLIENT_ID   = {"(có)" if client_id else "(trống)"}')
        self.stdout.write(f'KIOTVIET_CLIENT_SECRET = {"(có)" if has_secret else "(trống)"}')
        self.stdout.write(f'kiotviet_is_live()   = {kiotviet_is_live()}')

        if not kiotviet_is_live():
            self.stdout.write(self.style.WARNING(
                '\nMenu KiotViet sẽ KHÔNG hiện. Thêm vào /opt/portaljustplay/.env trên VPS:'
            ))
            self.stdout.write(
                'KIOTVIET_ENABLED=1\n'
                'KIOTVIET_RETAILER=justsport\n'
                'KIOTVIET_CLIENT_ID=...\n'
                'KIOTVIET_CLIENT_SECRET=...\n'
                'Sau đó: docker compose restart web'
            )
            return

        from django.contrib.auth import get_user_model

        User = get_user_model()
        for username in ('admin',):
            try:
                user = User.objects.get(username=username)
                can = user_can_use_kiotviet(user)
                self.stdout.write(
                    f'user_can_use_kiotviet({username}) = {can} '
                    f'(superuser={user.is_superuser}, staff={user.is_staff})'
                )
            except User.DoesNotExist:
                self.stdout.write(f'User {username}: không tồn tại')

        use_mirror = mirror_enabled()
        self.stdout.write(f'KIOTVIET_USE_LOCAL_MIRROR = {use_mirror}')
        self.stdout.write('\n=== Mirror DB (kv_*) ===')
        counts = mirror_summary()
        for entity, count in counts.items():
            self.stdout.write(f'  {entity}: {count} bản ghi')
        states = sync_states()
        if states:
            self.stdout.write('\nSync state:')
            for st in states:
                cursor = st.last_modified_from.isoformat() if st.last_modified_from else '—'
                self.stdout.write(
                    f'  {st.entity_type}: records={st.records_total}, '
                    f'cursor={cursor}, error={st.last_error or "—"}'
                )
        elif use_mirror:
            self.stdout.write(self.style.WARNING(
                '\nChưa sync mirror. Chạy: python manage.py kiotviet_sync --full'
            ))

        self.stdout.write('\nThử lấy token...')
        try:
            KiotVietClient().get_access_token()
            self.stdout.write(self.style.SUCCESS('OAuth token: OK'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'OAuth token: FAIL — {exc}'))
