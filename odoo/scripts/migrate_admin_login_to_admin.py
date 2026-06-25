#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chuyển quản trị chính Odoo: it@justplay.vn -> login admin (giữ user id=2).
Chạy trên VPS (có ADMIN_PASSWORD trong env hoặc file .portal_api_password):
  ADMIN_PASSWORD=$(cat /opt/odoo/.portal_api_password) \\
  docker compose -f /opt/odoo/docker-compose.yml exec -T -e ADMIN_PASSWORD odoo \\
    odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf \\
    < /opt/odoo/scripts/migrate_admin_login_to_admin.py
"""
# flake8: noqa

import os

OLD_LOGIN = "it@justplay.vn"
NEW_LOGIN = "admin"
BACKUP_LOGIN = "it@justplay.vn.disabled"


def migrate():
    User = env["res.users"].sudo()
    password = (os.environ.get("ADMIN_PASSWORD") or "").strip()

    old = User.search([("login", "=", OLD_LOGIN)], limit=1)
    if not old:
        current = User.search([("login", "=", NEW_LOGIN)], limit=1)
        if current and current._is_system():
            print(f"Đã dùng {NEW_LOGIN} (id={current.id}) — không cần migrate.")
            return True
        print(f"Không tìm thấy {OLD_LOGIN}")
        return False

    conflict = User.search([("login", "=", NEW_LOGIN), ("id", "!=", old.id)], limit=1)
    if conflict:
        legacy_login = f"admin.legacy.{conflict.id}"
        print(f"Đổi login xung đột id={conflict.id} -> {legacy_login}")
        conflict.write({"login": legacy_login, "active": False})

    print(f"Đổi login id={old.id}: {OLD_LOGIN} -> {NEW_LOGIN}")
    old.write({"login": NEW_LOGIN, "active": True})

    if password:
        old.write({"password": password})
        print("Đã đặt mật khẩu từ ADMIN_PASSWORD")

    # portal_sync — copy quyền từ admin mới
    sync = User.search([("login", "=", "portal_sync")], limit=1)
    if sync:
        sync.write({
            "groups_id": [(6, 0, old.groups_id.ids)],
            "active": True,
        })
        if password:
            sync.write({"password": password})
        print(f"portal_sync (id={sync.id}) đã đồng bộ quyền")

    env.cr.commit()
    print("--- Hoàn tất ---")
    print(f"  login={old.login} id={old.id} system={old._is_system()}")
    return True


migrate()
