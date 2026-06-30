import re

from django.db import migrations, models
import django.db.models.deletion

from kho_npl.choices import DEFAULT_MATERIAL_SPECIFICATIONS


def seed_material_specifications(apps, schema_editor):
    MaterialSpecification = apps.get_model('kho_npl', 'MaterialSpecification')
    for code, name, sort_order in DEFAULT_MATERIAL_SPECIFICATIONS:
        MaterialSpecification.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def unseed_material_specifications(apps, schema_editor):
    MaterialSpecification = apps.get_model('kho_npl', 'MaterialSpecification')
    MaterialSpecification.objects.filter(
        code__in=[code for code, _, _ in DEFAULT_MATERIAL_SPECIFICATIONS],
    ).delete()


def _slug_code(text: str) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', text.lower().strip())
    return text.strip('-')[:40] or 'qc-khac'


def migrate_material_specification_text(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    MaterialSpecification = apps.get_model('kho_npl', 'MaterialSpecification')

    by_name = {s.name.lower(): s for s in MaterialSpecification.objects.all()}
    by_code = {s.code.lower(): s for s in MaterialSpecification.objects.all()}

    for material in Material.objects.exclude(specification_text='').iterator():
        text = (material.specification_text or '').strip()
        if not text:
            continue
        key = text.lower()
        spec = by_name.get(key) or by_code.get(key)
        if not spec:
            code = _slug_code(text)
            base_code = code
            n = 2
            while code.lower() in by_code:
                code = f'{base_code}-{n}'
                n += 1
            spec = MaterialSpecification.objects.create(
                code=code,
                name=text,
                sort_order=999,
                is_active=True,
            )
            by_name[key] = spec
            by_code[spec.code.lower()] = spec
        material.specification_ref_id = spec.pk
        material.save(update_fields=['specification_ref_id'])


def reverse_material_specification_text(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    for material in Material.objects.exclude(specification_ref_id__isnull=True).select_related('specification_ref'):
        material.specification_text = material.specification_ref.name
        material.save(update_fields=['specification_text'])


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0008_material_color'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaterialSpecification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=40, unique=True, verbose_name='Mã quy cách')),
                ('name', models.CharField(max_length=120, verbose_name='Quy cách / khổ')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
            ],
            options={
                'verbose_name': 'Quy cách NPL',
                'verbose_name_plural': 'Quy cách NPL',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RunPython(seed_material_specifications, unseed_material_specifications),
        migrations.RenameField(
            model_name='material',
            old_name='specification',
            new_name='specification_text',
        ),
        migrations.AddField(
            model_name='material',
            name='specification_ref',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='materials',
                to='kho_npl.materialspecification',
                verbose_name='Quy cách / khổ',
            ),
        ),
        migrations.RunPython(migrate_material_specification_text, reverse_material_specification_text),
        migrations.RemoveField(
            model_name='material',
            name='specification_text',
        ),
        migrations.RenameField(
            model_name='material',
            old_name='specification_ref',
            new_name='specification',
        ),
    ]
