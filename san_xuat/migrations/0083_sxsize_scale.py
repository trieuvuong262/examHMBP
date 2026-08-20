from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0082_bom_audit_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsize',
            name='scale',
            field=models.CharField(
                choices=[
                    ('ALPHA', 'Size chữ (XS–6XL)'),
                    ('NUM', 'Size số (trẻ em)'),
                    ('OS', 'Một size'),
                    ('NONE', 'Không có size'),
                ],
                db_index=True,
                default='ALPHA',
                help_text='Size chữ và size số là hai thang đo khác nhau, không so sánh lẫn nhau.',
                max_length=10,
                verbose_name='Thang đo',
            ),
        ),
    ]
