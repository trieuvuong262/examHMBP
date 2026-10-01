from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0016_loginsecurityconfig_geo'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResponseTimeDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(unique=True)),
                ('request_count', models.PositiveIntegerField(default=0)),
                ('total_ms', models.BigIntegerField(default=0)),
                ('p50_ms', models.PositiveIntegerField(default=0)),
                ('p95_ms', models.PositiveIntegerField(default=0)),
                ('max_ms', models.PositiveIntegerField(default=0)),
                ('le_1s_count', models.PositiveIntegerField(default=0)),
                ('gt_3s_count', models.PositiveIntegerField(default=0)),
                ('by_url', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Thời gian phản hồi theo ngày',
                'verbose_name_plural': 'Thời gian phản hồi theo ngày',
                'ordering': ['-day'],
            },
        ),
        migrations.CreateModel(
            name='DbQuerySnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(unique=True)),
                ('calls', models.BigIntegerField(default=0)),
                ('total_exec_ms', models.FloatField(default=0)),
                ('slow_query_count', models.PositiveIntegerField(default=0)),
                ('taken_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ảnh chụp truy vấn DB',
                'verbose_name_plural': 'Ảnh chụp truy vấn DB',
                'ordering': ['-day'],
            },
        ),
    ]
