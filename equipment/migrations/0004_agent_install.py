from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('equipment', '0003_equipmentscancontrol'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentInstallToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_install_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserAgentRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('serial_number', models.CharField(db_index=True, max_length=100)),
                ('registered_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_registrations', to='equipment.device')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_registrations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-registered_at'],
                'unique_together': {('user', 'serial_number')},
            },
        ),
    ]
