import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django

django.setup()

from django.conf import settings
from django.db import connection

print("DJANGO_ENV:", os.getenv("DJANGO_ENV"))
print("DB NAME:", settings.DATABASES["default"]["NAME"])
print("DB HOST:", settings.DATABASES["default"]["HOST"])

with connection.cursor() as cursor:
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'announcements%'"
    )
    print("announcement tables:", cursor.fetchall())
