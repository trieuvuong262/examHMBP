#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py smoke_kho_npl_features
docker compose exec -T web python manage.py shell -c "from kho_npl.models import Material; t=Material.objects.filter(is_active=True).count(); p=Material.objects.filter(is_active=True, category__parent__isnull=False).count(); print('MATERIALS active', t, 'with parent category', p)"
