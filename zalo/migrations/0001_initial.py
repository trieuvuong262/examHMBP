# Generated manually — Zalo OAuth token store

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ZaloOAuthToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.TextField(blank=True, default='')),
                ('refresh_token', models.TextField(blank=True, default='')),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Zalo OAuth token',
                'verbose_name_plural': 'Zalo OAuth tokens',
            },
        ),
    ]
