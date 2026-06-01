#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
echo "=== .env (equipment) ==="
grep -E 'EQUIPMENT|PORTAL_PUBLIC' .env || echo "(missing)"
echo "=== container settings ==="
docker compose exec -T web python manage.py shell <<'PY'
from django.conf import settings
print("REQUIRE_AGENT_INSTALL:", settings.EQUIPMENT_REQUIRE_AGENT_INSTALL)
print("AGENT_SECRET_SET:", bool(settings.EQUIPMENT_AGENT_SECRET))
print("EXEMPT_USERNAMES:", settings.EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES)
print("MIDDLEWARE:", "equipment.middleware.AgentInstallGateMiddleware" in settings.MIDDLEWARE)
PY
