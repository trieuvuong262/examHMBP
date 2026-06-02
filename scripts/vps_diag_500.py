"""Chẩn đoán 500 trên VPS — chạy: docker compose exec -T web python scripts/vps_diag_500.py"""
import os
import sys
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()
user = User.objects.filter(is_active=True).order_by("-is_superuser", "id").first()
print("user:", user.username if user else None)

paths = [
    "/",
    "/accounts/login/",
    "/yeu-cau/de-xuat/cua-toi/",
    "/yeu-cau/ho-tro/cua-toi/",
    "/thiet-bi/it/danh-sach/",
]

client = Client()
if user:
    client.force_login(user)

for path in paths:
    try:
        resp = client.get(path)
        print(f"{path} -> {resp.status_code}")
        if resp.status_code >= 500:
            print(resp.content[:2000].decode("utf-8", errors="replace"))
    except Exception:
        print(f"{path} -> EXCEPTION")
        traceback.print_exc()
