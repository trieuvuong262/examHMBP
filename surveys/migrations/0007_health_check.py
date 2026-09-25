import json
from pathlib import Path

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def load_roster(apps, schema_editor):
    HealthCheckCampaign = apps.get_model('surveys', 'HealthCheckCampaign')
    HealthCheckPerson = apps.get_model('surveys', 'HealthCheckPerson')
    payload_path = Path(__file__).resolve().parent.parent / 'data' / 'ksk_2026_10.json'
    payload = json.loads(payload_path.read_text(encoding='utf-8'))
    campaign, _created = HealthCheckCampaign.objects.get_or_create(
        code=payload['code'],
        defaults={'title': payload['title'], 'is_open': True},
    )
    if campaign.people.exists():
        return
    HealthCheckPerson.objects.bulk_create([
        HealthCheckPerson(
            campaign=campaign,
            sort_order=row['sort_order'],
            employee_code=row.get('employee_code') or '',
            full_name=row.get('full_name') or '',
            id_number=row.get('id_number') or '',
            phone=row.get('phone') or '',
            street=row.get('street') or '',
            ward=row.get('ward') or '',
            province=row.get('province') or '',
        )
        for row in payload['people']
    ])


def unload_roster(apps, schema_editor):
    HealthCheckCampaign = apps.get_model('surveys', 'HealthCheckCampaign')
    HealthCheckCampaign.objects.filter(code='ksk-2026-10').delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('surveys', '0006_survey_text_questions'),
    ]

    operations = [
        migrations.CreateModel(
            name='HealthCheckCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=40, unique=True, verbose_name='Mã đợt')),
                ('title', models.CharField(max_length=255, verbose_name='Tiêu đề')),
                ('is_open', models.BooleanField(db_index=True, default=True, verbose_name='Đang mở')),
                ('closed_at', models.DateTimeField(blank=True, null=True, verbose_name='Thời điểm đóng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Đợt khám sức khỏe',
                'verbose_name_plural': 'Đợt khám sức khỏe',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='HealthCheckPerson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='STT')),
                ('employee_code', models.CharField(blank=True, db_index=True, max_length=50, verbose_name='Mã NV')),
                ('full_name', models.CharField(max_length=255, verbose_name='Họ và tên')),
                ('id_number', models.CharField(blank=True, max_length=20, verbose_name='Số CMND/CCCD')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='Số điện thoại')),
                ('street', models.CharField(blank=True, max_length=255, verbose_name='Số nhà, đường, ấp')),
                ('ward', models.CharField(blank=True, max_length=255, verbose_name='Phường/xã')),
                ('province', models.CharField(blank=True, max_length=255, verbose_name='Tỉnh/thành phố')),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='people', to='surveys.healthcheckcampaign', verbose_name='Đợt')),
            ],
            options={
                'verbose_name': 'Người trong danh sách KSK',
                'verbose_name_plural': 'Người trong danh sách KSK',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='HealthCheckSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255, verbose_name='Họ và tên')),
                ('id_number', models.CharField(max_length=20, verbose_name='Số CMND/CCCD')),
                ('phone', models.CharField(max_length=20, verbose_name='Số điện thoại')),
                ('street', models.CharField(max_length=255, verbose_name='Số nhà, đường, ấp')),
                ('ward', models.CharField(max_length=255, verbose_name='Phường/xã')),
                ('province', models.CharField(max_length=255, verbose_name='Tỉnh/thành phố')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='surveys.healthcheckcampaign', verbose_name='Đợt')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='surveys.healthcheckperson', verbose_name='Dòng danh sách')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='health_check_submissions', to=settings.AUTH_USER_MODEL, verbose_name='Nhân viên')),
            ],
            options={
                'verbose_name': 'Xác nhận thông tin KSK',
                'verbose_name_plural': 'Xác nhận thông tin KSK',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='healthcheckperson',
            constraint=models.UniqueConstraint(condition=models.Q(('employee_code', ''), _negated=True), fields=('campaign', 'employee_code'), name='surveys_ksk_unique_code'),
        ),
        migrations.AddConstraint(
            model_name='healthchecksubmission',
            constraint=models.UniqueConstraint(fields=('campaign', 'user'), name='surveys_ksk_unique_submission'),
        ),
        migrations.RunPython(load_roster, unload_roster),
    ]
