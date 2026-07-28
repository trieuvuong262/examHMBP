"""Gộp bộ phận IN NHIỆT + ÉP LOGO → IN ÉP (phòng SẢN XUẤT)."""

from django.db import migrations
from django.db.models import Q

KEEP_NAME = 'IN ÉP'
SOURCE_NAMES = ('IN NHIỆT', 'IN NHIET', 'In nhiệt', 'In nhiet')
MERGE_NAMES = ('ÉP LOGO', 'EP LOGO', 'Ép logo', 'Ep logo', 'Ép Logo')

# job_position + DivisionPosition → tên chung
POSITION_MAP = {
    'Tổ trưởng (in nhiệt)': 'Tổ trưởng (in ép)',
    'Công nhân (in nhiệt)': 'Công nhân (in ép)',
    'Công nhân (TT in nhiệt)': 'Công nhân (TT in ép)',
    'Tổ trưởng (ép logo)': 'Tổ trưởng (in ép)',
    'Công nhân (ép logo)': 'Công nhân (in ép)',
    'Công nhân (TT ép logo)': 'Công nhân (TT in ép)',
    'Tổ trưởng (in nhiet)': 'Tổ trưởng (in ép)',
    'Công nhân (in nhiet)': 'Công nhân (in ép)',
    'Công nhân (TT in nhiet)': 'Công nhân (TT in ép)',
    'Tổ trưởng (ep logo)': 'Tổ trưởng (in ép)',
    'Công nhân (ep logo)': 'Công nhân (in ép)',
    'Công nhân (TT ep logo)': 'Công nhân (TT in ép)',
}

TARGET_POSITIONS = (
    ('Tổ trưởng (in ép)', 0),
    ('Công nhân (TT in ép)', 1),
    ('Công nhân (in ép)', 2),
)


def _find_sx_department(Department):
    dept = Department.objects.filter(name__iexact='SẢN XUẤT').first()
    if dept:
        return dept
    return Department.objects.filter(name__icontains='SẢN XUẤT').first()


def _find_division(Division, department, names):
    q = Q()
    for name in names:
        q |= Q(name__iexact=name)
    qs = Division.objects.filter(q)
    if department is not None:
        hit = qs.filter(department=department).order_by('pk').first()
        if hit:
            return hit
    return qs.order_by('pk').first()


def _rename_job_positions(Profile, ProfileConcurrentPosition, division_ids):
    for old, new in POSITION_MAP.items():
        Profile.objects.filter(
            division_id__in=division_ids,
            job_position__iexact=old,
        ).update(job_position=new)
        ProfileConcurrentPosition.objects.filter(
            division_id__in=division_ids,
            job_position__iexact=old,
        ).update(job_position=new)


def _ensure_target_positions(DivisionPosition, keep, department):
    existing = {
        (p.name or '').strip().casefold(): p
        for p in DivisionPosition.objects.filter(division=keep)
    }
    for name, sort_order in TARGET_POSITIONS:
        key = name.casefold()
        pos = existing.get(key)
        if pos:
            updates = []
            if pos.sort_order != sort_order:
                pos.sort_order = sort_order
                updates.append('sort_order')
            if not pos.is_active:
                pos.is_active = True
                updates.append('is_active')
            if department and pos.department_id != department.id:
                pos.department_id = department.id
                updates.append('department_id')
            if updates:
                pos.save(update_fields=updates)
        else:
            DivisionPosition.objects.create(
                division=keep,
                department=department,
                name=name,
                sort_order=sort_order,
                is_active=True,
            )


def merge_in_ep(apps, schema_editor):
    Department = apps.get_model('hrm', 'Department')
    Division = apps.get_model('hrm', 'Division')
    DivisionPosition = apps.get_model('hrm', 'DivisionPosition')
    Profile = apps.get_model('hrm', 'Profile')
    ProfileConcurrentPosition = apps.get_model('hrm', 'ProfileConcurrentPosition')

    sx = _find_sx_department(Department)
    keep = _find_division(Division, sx, SOURCE_NAMES + (KEEP_NAME,))
    merge = _find_division(Division, sx, MERGE_NAMES)

    if keep is None and merge is None:
        return

    if keep is None:
        keep = merge
        merge = None

    if keep is None:
        return

    # Không gộp chính nó nếu tên nguồn đã là IN ÉP và không còn ÉP LOGO
    if merge is not None and merge.pk == keep.pk:
        merge = None

    division_ids = [keep.pk]
    if merge is not None:
        division_ids.append(merge.pk)

    _rename_job_positions(Profile, ProfileConcurrentPosition, division_ids)

    if merge is not None:
        Profile.objects.filter(division_id=merge.pk).update(
            division_id=keep.pk,
            department_id=keep.department_id or (sx.id if sx else None),
        )
        ProfileConcurrentPosition.objects.filter(division_id=merge.pk).update(
            division_id=keep.pk,
            department_id=keep.department_id or (sx.id if sx else None),
        )
        DivisionPosition.objects.filter(division_id=merge.pk).delete()

    # Đổi tên vị trí còn sót trên bộ phận giữ lại (trước khi tạo target)
    for old, new in POSITION_MAP.items():
        for pos in DivisionPosition.objects.filter(division=keep, name__iexact=old):
            conflict = DivisionPosition.objects.filter(
                division=keep,
                name__iexact=new,
            ).exclude(pk=pos.pk).first()
            if conflict:
                pos.delete()
            else:
                pos.name = new
                pos.save(update_fields=['name'])

    keep.name = KEEP_NAME
    keep.is_active = True
    if sx and keep.department_id is None:
        keep.department_id = sx.id
    keep.save()

    _ensure_target_positions(DivisionPosition, keep, sx or keep.department)

    # Dọn vị trí cũ không còn trong TARGET
    target_keys = {n.casefold() for n, _ in TARGET_POSITIONS}
    for pos in DivisionPosition.objects.filter(division=keep):
        if (pos.name or '').strip().casefold() not in target_keys:
            # Chỉ xóa nếu khớp map cũ; giữ vị trí lạ (nếu có)
            old_keys = {k.casefold() for k in POSITION_MAP}
            if (pos.name or '').strip().casefold() in old_keys:
                pos.delete()

    merge_pk = merge.pk if merge is not None else None
    if merge is not None:
        merge.delete()

    # Đồng bộ nhãn work center / HR map nếu bảng đã có
    try:
        SxWorkCenter = apps.get_model('san_xuat', 'SxWorkCenter')
        SxTeamHrMap = apps.get_model('san_xuat', 'SxTeamHrMap')
    except LookupError:
        return

    try:
        code = f'HRD-{keep.pk}'
        for center in SxWorkCenter.objects.filter(code__iexact=code):
            center.name = KEEP_NAME
            center.team_label = KEEP_NAME
            center.save(update_fields=['name', 'team_label'])

        if merge_pk is not None:
            SxWorkCenter.objects.filter(code__iexact=f'HRD-{merge_pk}').update(is_active=False)

        for label in list(SOURCE_NAMES) + list(MERGE_NAMES):
            for row in SxTeamHrMap.objects.filter(team_label__iexact=label):
                row.team_label = KEEP_NAME
                row.save(update_fields=['team_label'])
    except Exception:
        # Bảng SX chưa migrate / không có trên môi trường này — bỏ qua.
        return


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0081_kho_sp_code_settings_menu'),
    ]

    operations = [
        migrations.RunPython(merge_in_ep, noop),
    ]
