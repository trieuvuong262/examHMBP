#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker exec -w /app portaljustplay-web-1 python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
from django.test import Client
from django.conf import settings
from equipment.services.agent_install import is_agent_install_required, user_is_in_equipment_registry

print("REQUIRE:", settings.EQUIPMENT_REQUIRE_AGENT_INSTALL)
print("SECRET:", bool(settings.EQUIPMENT_AGENT_SECRET))
print("MW:", "AgentInstallGateMiddleware" in str(settings.MIDDLEWARE))

User = get_user_model()
u, _ = User.objects.get_or_create(username="gate_test_user")
c = Client()
c.force_login(u)
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
r = c.get("/", HTTP_USER_AGENT=ua, follow=False)
print("in_registry:", user_is_in_equipment_registry(u))
req = c.request().wsgi_request
req.user = u
req.META["HTTP_USER_AGENT"] = ua
print("install_required:", is_agent_install_required(req))
print("GET / status:", r.status_code)
print("Location:", r.get("Location", ""))
if r.status_code == 302 and "yeu-cau-cai" in (r.get("Location") or ""):
    print("PASS: gate redirect OK")
else:
    print("FAIL: no gate redirect")
PY
