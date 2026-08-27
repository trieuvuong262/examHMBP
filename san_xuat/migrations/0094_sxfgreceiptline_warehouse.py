# Generated manually for per-line FG warehouse

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0013_alter_stockledger_source_doc_type'),
        ('san_xuat', '0093_sxteamworkaccept'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxfgreceiptline',
            name='warehouse',
            field=models.ForeignKey(
                blank=True,
                help_text='Kho ghi tăng tồn cho dòng này; trống thì dùng kho trên phiếu.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fg_receipt_lines',
                to='kho_san_pham.warehouse',
                verbose_name='Kho nhập',
            ),
        ),
    ]
