from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0029_rename_adjustment_verbose_to_stocktake'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='primary_location',
            field=models.ForeignKey(
                blank=True,
                help_text='Kệ/kho gợi ý khi nhập. Để trống thì phiếu nhập dùng kho MAIN.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='default_materials',
                to='kho_npl.warehouselocation',
                verbose_name='Vị trí mặc định',
            ),
        ),
    ]
