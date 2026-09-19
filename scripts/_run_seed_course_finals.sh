#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
mkdir -p /opt/portaljustplay/scripts
cp -f /tmp/seed_lesson_exams.py /tmp/seed_course_final_exams.py /opt/portaljustplay/scripts/
docker compose exec -T web python manage.py shell < /opt/portaljustplay/scripts/seed_course_final_exams.py
