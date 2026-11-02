"""Gộp Tổ gia công (SxWorkCenter.is_subcontract) vào Đối tác gia công (GcPartner).

- Mỗi SxWorkCenter đang đánh dấu thuê gia công → tạo GcPartner tương ứng (nếu chưa có).
- Phiếu GC cũ có work_center là tổ GC nhưng chưa gắn partner → gán partner vừa chuyển.
- Bỏ cờ is_subcontract trên work center đã chuyển (ngừng dùng trong luồng GC).
Giữ nguyên cột is_subcontract và work_center để không phá bảng lớn.
"""

from django.db import migrations


def _slug_for_center(code: str, name: str) -> str:
    wc_map = {'CAT': 'cat', 'IN-EP': 'inep', 'THEU': 'theu', 'MAY': 'may', 'HT': 'ht', 'GH': 'gh'}
    c = (code or '').strip().upper()
    if c in wc_map:
        return wc_map[c]
    folded = f'{code} {name}'.lower()
    for key, slug in (
        ('cat', 'cat'), ('cắt', 'cat'), ('in', 'inep'), ('ép', 'inep'), ('ep', 'inep'),
        ('thêu', 'theu'), ('theu', 'theu'), ('may', 'may'), ('ủi', 'ht'), ('gấp', 'ht'),
        ('hoàn', 'ht'), ('giao', 'gh'),
    ):
        if key in folded:
            return slug
    return ''


def forward(apps, schema_editor):
    SxWorkCenter = apps.get_model('san_xuat', 'SxWorkCenter')
    GcPartner = apps.get_model('san_xuat', 'GcPartner')
    SxSubcontractOrder = apps.get_model('san_xuat', 'SxSubcontractOrder')

    existing = {(p.name or '').strip().casefold(): p for p in GcPartner.objects.all()}
    existing_codes = {(p.code or '').strip().upper() for p in GcPartner.objects.all()}
    by_center: dict[int, object] = {}
    seq = 1

    for wc in SxWorkCenter.objects.filter(is_demo=False, is_subcontract=True).order_by('pk'):
        key = (wc.name or '').strip().casefold()
        partner = existing.get(key)
        if partner is None:
            code = (wc.code or '').strip().upper()
            if not code or code in existing_codes:
                while True:
                    code = f'GC{seq:04d}'
                    seq += 1
                    if code not in existing_codes:
                        break
            slug = _slug_for_center(wc.code, wc.name)
            partner = GcPartner.objects.create(
                code=code,
                name=(wc.name or code).strip(),
                team_slugs=[slug] if slug else [],
                work_center_id=wc.pk,
                capacity_per_day=wc.capacity_per_day or 0,
                notes=wc.notes or '',
                is_active=wc.is_active,
            )
            existing[key] = partner
            existing_codes.add(code)
        by_center[wc.pk] = partner

    # Phiếu cũ chưa gắn partner nhưng có work_center là tổ GC, hoặc vendor_name trùng tên tổ.
    partner_by_name = {(p.name or '').strip().casefold(): p for p in GcPartner.objects.all()}
    for order in SxSubcontractOrder.objects.filter(partner__isnull=True):
        partner = by_center.get(order.work_center_id) if order.work_center_id else None
        if partner is None:
            partner = partner_by_name.get((order.vendor_name or '').strip().casefold())
        if partner is not None:
            order.partner = partner
            if not (order.vendor_name or '').strip():
                order.vendor_name = partner.name
            order.save(update_fields=['partner', 'vendor_name'])

    # Ngừng dùng cờ is_subcontract trên các tổ đã chuyển.
    SxWorkCenter.objects.filter(is_demo=False, is_subcontract=True).update(is_subcontract=False)


def backward(apps, schema_editor):
    # Bật lại cờ cho work center còn được GcPartner trỏ tới (đảo gần đúng).
    SxWorkCenter = apps.get_model('san_xuat', 'SxWorkCenter')
    GcPartner = apps.get_model('san_xuat', 'GcPartner')
    ids = GcPartner.objects.filter(work_center__isnull=False).values_list('work_center_id', flat=True)
    SxWorkCenter.objects.filter(pk__in=list(ids)).update(is_subcontract=True)


class Migration(migrations.Migration):
    dependencies = [('san_xuat', '0154_gc_partner_send_kpi')]
    operations = [migrations.RunPython(forward, backward)]
