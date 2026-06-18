from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sinh cặp khóa VAPID cho web push — copy vào .env (WEBPUSH_VAPID_*).'

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives import serialization
            from py_vapid import Vapid
            from py_vapid.utils import b64urlencode
        except ImportError as exc:
            self.stderr.write(self.style.ERROR('Cần cài pywebpush: pip install pywebpush'))
            raise SystemExit(1) from exc

        vapid = Vapid()
        vapid.generate_keys()
        raw_public = vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_key = b64urlencode(raw_public)
        private_pem = vapid.private_pem().decode('utf-8')
        private_env = private_pem.replace('\n', '\\n')

        self.stdout.write('Thêm vào .env / .env trên VPS:')
        self.stdout.write(f'WEBPUSH_VAPID_PUBLIC_KEY={public_key}')
        self.stdout.write(f'WEBPUSH_VAPID_PRIVATE_KEY={private_env}')
        self.stdout.write('WEBPUSH_VAPID_CLAIMS_EMAIL=mailto:it@justplay.vn')
