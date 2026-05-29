from django.db import migrations, models


def migrate_pro_to_flash(apps, schema_editor):
    LibraryQAConfig = apps.get_model('documents', 'LibraryQAConfig')
    LibraryQAConfig.objects.filter(gemini_model='gemini-2.5-pro').update(
        gemini_model='gemini-2.5-flash',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_update_qa_model_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='libraryqaconfig',
            name='gemini_model',
            field=models.CharField(
                choices=[
                    ('gemini-2.5-flash', 'Nhanh & cân bằng (khuyên dùng)'),
                    ('gemini-flash-latest', 'Tự động cập nhật (flash)'),
                    ('gemini-2.0-flash-lite', 'Siêu nhẹ'),
                ],
                default='gemini-2.5-flash',
                max_length=64,
                verbose_name='Model',
            ),
        ),
        migrations.RunPython(migrate_pro_to_flash, migrations.RunPython.noop),
    ]
