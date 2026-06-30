import re

from django.db import migrations, models
import django.db.models.deletion

from kho_npl.choices import DEFAULT_MATERIAL_COLORS


def seed_material_colors(apps, schema_editor):
    MaterialColor = apps.get_model('kho_npl', 'MaterialColor')
    for code, name, hex_code, sort_order in DEFAULT_MATERIAL_COLORS:
        MaterialColor.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'hex_code': hex_code,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def unseed_material_colors(apps, schema_editor):
    MaterialColor = apps.get_model('kho_npl', 'MaterialColor')
    MaterialColor.objects.filter(
        code__in=[code for code, _, _, _ in DEFAULT_MATERIAL_COLORS],
    ).delete()


def _slug_code(text: str) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', text.lower().strip())
    return text.strip('-')[:40] or 'mau-khac'


def migrate_material_color_text(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    MaterialColor = apps.get_model('kho_npl', 'MaterialColor')

    by_name = {c.name.lower(): c for c in MaterialColor.objects.all()}
    by_code = {c.code.lower(): c for c in MaterialColor.objects.all()}

    for material in Material.objects.exclude(color_text='').iterator():
        text = (material.color_text or '').strip()
        if not text:
            continue
        key = text.lower()
        color = by_name.get(key) or by_code.get(key)
        if not color:
            code = _slug_code(text)
            base_code = code
            n = 2
            while code.lower() in by_code:
                code = f'{base_code}-{n}'
                n += 1
            color = MaterialColor.objects.create(
                code=code,
                name=text,
                hex_code='#9CA3AF',
                sort_order=999,
                is_active=True,
            )
            by_name[key] = color
            by_code[color.code.lower()] = color
        material.color_ref_id = color.pk
        material.save(update_fields=['color_ref_id'])


def reverse_material_color_text(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    MaterialColor = apps.get_model('kho_npl', 'MaterialColor')
    for material in Material.objects.exclude(color_ref_id__isnull=True).select_related('color_ref'):
        material.color_text = material.color_ref.name
        material.save(update_fields=['color_text'])


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0007_stocktake_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaterialColor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=40, unique=True, verbose_name='Mã màu')),
                ('name', models.CharField(max_length=80, verbose_name='Tên màu')),
                ('hex_code', models.CharField(max_length=7, verbose_name='Mã hex')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
            ],
            options={
                'verbose_name': 'Màu sắc NPL',
                'verbose_name_plural': 'Màu sắc NPL',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RunPython(seed_material_colors, unseed_material_colors),
        migrations.RenameField(
            model_name='material',
            old_name='color',
            new_name='color_text',
        ),
        migrations.AddField(
            model_name='material',
            name='color_ref',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='materials',
                to='kho_npl.materialcolor',
                verbose_name='Màu sắc',
            ),
        ),
        migrations.RunPython(migrate_material_color_text, reverse_material_color_text),
        migrations.RemoveField(
            model_name='material',
            name='color_text',
        ),
        migrations.RenameField(
            model_name='material',
            old_name='color_ref',
            new_name='color',
        ),
    ]
