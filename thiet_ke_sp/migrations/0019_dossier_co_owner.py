from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('thiet_ke_sp', '0018_test_mode_help'),
    ]

    operations = [
        migrations.AddField(
            model_name='productdevelopment',
            name='co_owner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='tksp_co_owned',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người phụ trách chính (2)',
            ),
        ),
    ]
