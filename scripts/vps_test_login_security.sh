#!/usr/bin/env bash
# Kiểm tra bảo mật đăng nhập trên VPS (sau deploy + migrate)
set -euo pipefail
cd /opt/portaljustplay

echo "==> migrate audit"
docker compose exec -T web python manage.py migrate audit --noinput

echo "==> unit tests LoginSecurityTests"
docker compose exec -T web python manage.py test audit.tests.LoginSecurityTests -v 1

echo "==> smoke: trang + logic IP"
docker compose exec -T -w /app web python <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from audit.login_security import record_failed_login, is_ip_blocked, get_security_config, save_login_security_config
from audit.models import LoginSecurityConfig

User = get_user_model()
admin = User.objects.filter(is_superuser=True, is_active=True).first()
if not admin:
    admin = User.objects.filter(is_active=True).first()
print("admin:", admin.username if admin else "NONE")

client = Client(HTTP_HOST="portal.justplay.vn", secure=True)
if admin:
    client.force_login(admin)
    for tab in ("accounts", "bots", "config"):
        r = client.get(reverse("audit:login_security") + f"?tab={tab}")
        ok = r.status_code == 200
        print(f"GET login_security?tab={tab} -> {r.status_code}", "OK" if ok else "FAIL")
        if tab == "config":
            has_tabs = b"jp-login-security-tabs" in r.content
            has_wan = "IP WAN công ty".encode() in r.content
            print("  css tabs class:", "OK" if has_tabs else "FAIL")
            print("  config form:", "OK" if has_wan else "FAIL")

cfg = get_security_config()
save_login_security_config(
    wan_whitelist_text="14.161.25.119",
    ip_blacklist_text="198.51.100.99",
    admin_user=admin,
)
cfg.refresh_from_db()
print("whitelist saved:", cfg.wan_whitelist_ips)
print("blacklist saved:", cfg.ip_blacklist)

for i in range(10):
    record_failed_login(username=f"vpsbot{i}", ip="198.51.100.88")
print("login failures no auto IP block:", not is_ip_blocked("198.51.100.88"))
for i in range(12):
    record_failed_login(username=f"vpsbot{i}", ip="14.161.25.119")
print("whitelist no block:", not is_ip_blocked("14.161.25.119"))
print("blacklist instant:", is_ip_blocked("198.51.100.99"))
PY

echo "==> done"
