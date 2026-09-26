"""Thu hẹp quyền Duyệt giá / Bảng so giá đúng nghiệp vụ.

- Duyệt giá (sx_price_approve): chỉ nhóm TGĐ (Sếp Đức / Ductn) — Xem + Sửa.
  Ai có Sửa trên menu này thì chốt bảng / duyệt đơn được.
  admin và Ductn là superuser nên luôn bypass; seed TGĐ để ma trận quyền đúng.
- Bảng so giá (sx_price_quote): chỉ nhóm KHSX.
- Giữ hai bước tách riêng (chốt bảng + duyệt đơn).
- Giữ tên nhóm sidebar «Đặt hàng NPL».
"""

from django.db import migrations

APPROVE_KEY = 'sx_price_approve'
QUOTE_KEY = 'sx_price_quote'

_OFF = {
    'view': False,
    'create': False,
    'update': False,
    'delete': False,
    'export': False,
    'print': False,
}
_APPROVE_ON = {
    'view': True,
    'create': False,
    'update': True,
    'delete': False,
    'export': False,
    'print': False,
}
_QUOTE_ON = {
    'view': True,
    'create': True,
    'update': True,
    'delete': False,
    'export': False,
    'print': False,
}


def _is_khsx(name: str) -> bool:
    return 'khsx' in (name or '').casefold()


def _is_boss(name: str) -> bool:
    n = (name or '').casefold()
    return n == 'tgđ' or n == 'tgd' or 'tgđ' in n or n.startswith('tgđ')


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        changed = False
        name = group.name or ''

        if _is_boss(name):
            # Bật module SX tối thiểu + Duyệt giá đầy đủ cho Sếp
            if not sx.get('view'):
                sx['view'] = True
                changed = True
            if menus.get(APPROVE_KEY) != _APPROVE_ON:
                menus[APPROVE_KEY] = dict(_APPROVE_ON)
                changed = True
            # Sếp không cần so giá / đặt hàng mặc định
            if menus.get(QUOTE_KEY) != _OFF:
                menus[QUOTE_KEY] = dict(_OFF)
                changed = True
        else:
            if menus.get(APPROVE_KEY) != _OFF:
                menus[APPROVE_KEY] = dict(_OFF)
                changed = True

            if _is_khsx(name):
                if menus.get(QUOTE_KEY) != _QUOTE_ON:
                    menus[QUOTE_KEY] = dict(_QUOTE_ON)
                    changed = True
            else:
                if QUOTE_KEY in menus and menus.get(QUOTE_KEY) != _OFF:
                    menus[QUOTE_KEY] = dict(_OFF)
                    changed = True
                elif QUOTE_KEY not in menus and (sx.get('view') or menus):
                    # dọn seed tràn trước đó
                    menus[QUOTE_KEY] = dict(_OFF)
                    changed = True

        if changed:
            sx['menus'] = menus
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    # Không khôi phục seed tràn; chỉ tắt approve trên TGĐ nếu cần rollback mềm.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0115_seed_sx_price_quote_split_boss'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
