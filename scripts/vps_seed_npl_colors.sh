#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
git pull origin main
docker compose exec -T web python manage.py migrate kho_npl --noinput
docker compose exec -T web python manage.py seed_kho_npl_material_colors
docker compose exec -T web python manage.py shell -c "from kho_npl.models import Material, MaterialColor; print('PROD colors', MaterialColor.objects.filter(is_active=True).count()); t=Material.objects.filter(is_active=True).count(); w=Material.objects.filter(is_active=True, color__isnull=False).count(); print('PROD materials with color', w, '/', t)"
