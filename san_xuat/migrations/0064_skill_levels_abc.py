# Generated manually for skill levels A/B/C

from django.db import migrations


def forwards(apps, schema_editor):
    SxSkillLevel = apps.get_model('san_xuat', 'SxSkillLevel')
    SxOperation = apps.get_model('san_xuat', 'SxOperation')
    SxRoutingLine = apps.get_model('san_xuat', 'SxRoutingLine')
    SxTimeStudy = apps.get_model('san_xuat', 'SxTimeStudy')

    abc = (
        ('A', 'A', 10),
        ('B', 'B', 20),
        ('C', 'C', 30),
    )
    by_code = {}
    for code, name, order in abc:
        obj, _ = SxSkillLevel.objects.update_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )
        by_code[code] = obj

    SxSkillLevel.objects.exclude(code__in=['A', 'B', 'C']).update(is_active=False)

    old_map = {
        'Bậc 1 - Cơ bản': 'A',
        'Bậc 2 - Trung bình': 'B',
        'Bậc 3 - Khá': 'B',
        'Bậc 4 - Cao': 'C',
        'Bậc 5 - Chuyên dùng': 'C',
        'Bậc 1': 'A',
        'Bậc 2': 'B',
        'Bậc 3': 'B',
        'Bậc 4': 'C',
        'Bậc 5': 'C',
        '1': 'A',
        '2': 'B',
        '3': 'B',
        '4': 'C',
        '5': 'C',
    }

    def to_abc(label: str) -> str:
        s = (label or '').strip()
        if not s:
            return ''
        if s.upper() in ('A', 'B', 'C'):
            return s.upper()
        if s in old_map:
            return old_map[s]
        u = s.upper()
        if u.startswith('A') or '1' in s:
            return 'A'
        if u.startswith('B') or '2' in s:
            return 'B'
        if u.startswith('C') or any(x in s for x in ('3', '4', '5')):
            return 'C'
        return s

    for op in SxOperation.objects.all().iterator():
        new_label = to_abc(op.skill_level_label)
        if not new_label and op.skill_level_id:
            # lấy từ FK cũ nếu còn
            try:
                old = SxSkillLevel.objects.filter(pk=op.skill_level_id).first()
                if old:
                    new_label = to_abc(old.code) or to_abc(old.name)
            except Exception:
                new_label = ''
        if new_label in by_code:
            if op.skill_level_label != new_label or op.skill_level_id != by_code[new_label].pk:
                op.skill_level_label = new_label
                op.skill_level_id = by_code[new_label].pk
                op.save(update_fields=['skill_level_label', 'skill_level_id'])
        elif op.skill_level_id and op.skill_level_id not in {o.pk for o in by_code.values()}:
            op.skill_level_id = None
            op.save(update_fields=['skill_level_id'])

    for line in SxRoutingLine.objects.all().iterator():
        new_label = to_abc(line.skill_level_label)
        if new_label != line.skill_level_label:
            line.skill_level_label = new_label
            line.save(update_fields=['skill_level_label'])

    if hasattr(SxTimeStudy, 'objects'):
        for ts in SxTimeStudy.objects.all().iterator():
            new_label = to_abc(getattr(ts, 'skill_level_label', '') or '')
            if new_label != (ts.skill_level_label or ''):
                ts.skill_level_label = new_label
                ts.save(update_fields=['skill_level_label'])


def backwards(apps, schema_editor):
    # Không khôi phục Bậc 1..5 — giữ A/B/C.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0063_operation_ie_owner_label'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
