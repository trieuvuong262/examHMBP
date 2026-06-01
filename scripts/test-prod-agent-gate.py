"""Chạy trên VPS: docker compose exec -T web python scripts/test-prod-agent-gate.py"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

print("=== Config ===")
print("REQUIRE:", settings.EQUIPMENT_REQUIRE_AGENT_INSTALL)
print("SECRET:", bool(settings.EQUIPMENT_AGENT_SECRET))
print("MIDDLEWARE:", "equipment.middleware.AgentInstallGateMiddleware" in settings.MIDDLEWARE)

User = get_user_model()
username = "gate_test_user"
user, created = User.objects.get_or_create(username=username, defaults={"email": "gate@test.local"})
if created:
    user.set_password("gate-test-only")
    user.save()
    print(f"Created test user {username}")
else:
    print(f"Using existing test user {username}")

client = Client()
client.force_login(user)
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
resp = client.get("/", HTTP_USER_AGENT=ua, follow=False)
print("=== GET / (Windows UA) ===")
print("Status:", resp.status_code)
print("Location:", resp.get("Location", ""))

from equipment.services.agent_install import (
    is_agent_install_required,
    user_is_in_equipment_registry,
)

factory_client = Client()
request = factory_client.request().wsgi_request
request.user = user
request.META["HTTP_USER_AGENT"] = ua
print("=== Logic ===")
print("in_registry:", user_is_in_equipment_registry(user))
print("install_required:", is_agent_install_required(request))

if resp.status_code == 302 and "yeu-cau-cai" in (resp.get("Location") or ""):
    print("OK: Gate redirect works on production")
    sys.exit(0)

print("FAIL: Expected redirect to agent gate")
sys.exit(1)
