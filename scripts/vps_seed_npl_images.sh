#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
git pull origin main
bash deploy.sh
docker compose exec -T web python manage.py seed_kho_npl_material_images --active-only --delay 0.12
docker compose exec -T web python manage.py shell -c "from kho_npl.models import Material; t=Material.objects.filter(is_active=True).count(); w=Material.objects.filter(is_active=True).exclude(image='').exclude(image__isnull=True).count(); print('PROD active', t, 'with image', w)"
