"""Smoke test trang Quản lý Folder — chạy trong container web."""
import os
import sys

# Khi chạy trực tiếp (không qua manage.py), cần /app trên PYTHONPATH.
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from nas_storage.folder_tree import build_folder_tree
from nas_storage.models import NasShareFolder


def count_expandable(nodes):
    n = sum(1 for x in nodes if x.has_children)
    for x in nodes:
        n += count_expandable(x.children)
    return n


def main():
    host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "localhost"
    url = reverse("nas_storage:folder_list")
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("FAIL: no superuser")
        return 1

    failed = []
    client = Client(HTTP_HOST=host)

    anon = client.get(url, HTTP_HOST=host)
    if anon.status_code not in (302, 301):
        failed.append(f"anonymous should redirect, got {anon.status_code}")
    else:
        print(f"Anonymous: {anon.status_code} -> {anon.url}")

    client.force_login(user)
    resp = client.get(url, HTTP_HOST=host)
    print(f"URL: {url}")
    print(f"User: {user.username}")
    print(f"HTTP: {resp.status_code} (host={host})")

    if resp.status_code != 200:
        print(resp.content[:800].decode("utf-8", errors="replace"))
        return 1

    html = resp.content.decode("utf-8", errors="replace")
    markers = [
        "jp-folder-tree-hit--expandable",
        "jp-folder-tree-display",
        "jp-folder-tree-path",
        "jp-folder-actions",
        "--hm-primary",
        "jp-folder-tree-inner",
        "bi-folder-plus",
        "bi-shield-lock",
        "bi-trash",
        'class="jp-folder-tree-kids d-none"',
        "Quản lý Folder",
        "Tên hiển thị",
        "jp-folder-tree-body",
        "data-folder-target=",
        "toggleFolderHit",
        'class="jp-folder-tree-kids d-none"',
        "Quét từ NAS",
        "Thêm thư mục gốc",
    ]
    failed.extend(m for m in markers if m not in html)

    if "collapse show jp-folder-tree-kids" in html:
        failed.append("BAD: auto-expanded collapse show")

    all_folders = list(
        NasShareFolder.objects.order_by("sort_order", "share_name", "sub_path")
    )
    tree = build_folder_tree(all_folders)
    exp = count_expandable(tree)
    html_exp = html.count('data-folder-target="#jp-folder-kids-')
    print(f"DB folders: {len(all_folders)}, roots: {len(tree)}, expandable: {exp}")
    print(f"HTML expandable markers: {html_exp}")

    if exp != html_exp:
        failed.append(f"expandable count mismatch db={exp} html={html_exp}")

    if all_folders:
        pk = all_folders[0].pk
        try:
            reverse("nas_storage:folder_child_create", kwargs={"parent_pk": pk})
            reverse("nas_storage:folder_permissions", kwargs={"pk": pk})
            reverse("nas_storage:folder_delete", kwargs={"pk": pk})
        except Exception as exc:
            failed.append(f"reverse URLs: {exc}")

    if failed:
        print("--- FAILURES ---")
        for item in failed:
            print(" -", item)
        return 1

    print("--- ALL CHECKS PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
