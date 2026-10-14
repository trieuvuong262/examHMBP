import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0139_qc_flow_check'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxqcflowdefectline',
            name='defect',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='flow_lines',
                to='san_xuat.sxqcdefect',
                verbose_name='Mã lỗi',
            ),
        ),
        migrations.AddField(
            model_name='sxqcflowdefectline',
            name='size_label',
            field=models.CharField(blank=True, default='', max_length=40, verbose_name='Size'),
        ),
        migrations.CreateModel(
            name='SxQcFlowSizeLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('size_label', models.CharField(max_length=40, verbose_name='Size')),
                ('qty_order', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL lệnh')),
                ('qty_checked', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL kiểm')),
                ('qty_pass', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL đạt')),
                ('qty_repair', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL sửa')),
                ('qty_fail', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL lỗi')),
                ('sheet', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='size_lines',
                    to='san_xuat.sxqcflowcheck',
                )),
            ],
            options={
                'verbose_name': 'QC theo size',
                'verbose_name_plural': 'QC theo size',
                'ordering': ['id'],
                'constraints': [
                    models.UniqueConstraint(fields=('sheet', 'size_label'), name='sx_qc_flow_size_uniq'),
                ],
            },
        ),
    ]
