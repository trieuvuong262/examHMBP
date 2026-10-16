from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0029_test_mode_switch'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='join_date',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày nhận việc'),
        ),
    ]
