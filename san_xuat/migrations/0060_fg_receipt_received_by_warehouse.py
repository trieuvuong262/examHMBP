from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0059_sxteamdivisionmap'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxfgreceiptrequest',
            name='received_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fg_receipt_requests',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người nhập',
            ),
        ),
        migrations.AddField(
            model_name='sxfgreceiptrequest',
            name='warehouse_code',
            field=models.CharField(blank=True, default='', max_length=40, verbose_name='Mã kho nhập'),
        ),
        migrations.AddField(
            model_name='sxfgreceiptrequest',
            name='warehouse_name',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Kho nhập'),
        ),
    ]
