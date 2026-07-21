"""Seed quyen In (print) cho module san_xuat tu quyen Xem hien co."""

from django.db import migrations


def _seed_entry(entry):
    """Gan print=True neu view=True va chua co print."""
    if not isinstance(entry, dict):
        return False, entry
    out = dict(entry)
    changed = False
    if "print" not in out:
        out["print"] = bool(out.get("view"))
        changed = True
    menus = out.get("menus")
    if isinstance(menus, dict) and menus:
        new_menus = {}
        for key, menu in menus.items():
            if not isinstance(menu, dict):
                new_menus[key] = menu
                continue
            m = dict(menu)
            if "print" not in m:
                m["print"] = bool(m.get("view"))
                changed = True
            new_menus[key] = m
        out["menus"] = new_menus
    return changed, out


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model("hrm", "PermissionGroup")
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = perms.get("san_xuat")
        if not sx:
            continue
        changed, new_sx = _seed_entry(sx)
        if changed:
            perms["san_xuat"] = new_sx
            group.module_permissions = perms
            group.save(update_fields=["module_permissions"])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model("hrm", "PermissionGroup")
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get("san_xuat") or {})
        if not sx:
            continue
        changed = False
        if "print" in sx:
            sx.pop("print")
            changed = True
        menus = dict(sx.get("menus") or {})
        if menus:
            new_menus = {}
            for key, menu in menus.items():
                if isinstance(menu, dict) and "print" in menu:
                    m = dict(menu)
                    m.pop("print", None)
                    new_menus[key] = m
                    changed = True
                else:
                    new_menus[key] = menu
            sx["menus"] = new_menus
        if changed:
            perms["san_xuat"] = sx
            group.module_permissions = perms
            group.save(update_fields=["module_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("hrm", "0076_seed_san_xuat_general_settings_menu"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]