#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker cp /tmp/check_category_tree.py portaljustplay-web-1:/tmp/check_category_tree.py
docker compose exec -T web python manage.py shell -c "exec(open('/tmp/check_category_tree.py', encoding='utf-8').read())"
