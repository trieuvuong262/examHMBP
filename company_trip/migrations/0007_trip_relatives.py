"""Lưu tối đa 3 người thân trên một đăng ký."""

from django.db import migrations, models
import django.db.models.deletion


def copy_existing_relatives(apps, schema_editor):
    TripRegistration = apps.get_model('company_trip', 'TripRegistration')
    TripRelative = apps.get_model('company_trip', 'TripRelative')
    rows = []
    for reg in TripRegistration.objects.exclude(relative_full_name='').iterator():
        if not (reg.relative_full_name or '').strip():
            continue
        if not reg.relative_date_of_birth or not (reg.relative_cccd or '').strip():
            continue
        rows.append(TripRelative(
            registration_id=reg.pk,
            position=1,
            full_name=reg.relative_full_name,
            cccd=reg.relative_cccd or '',
            phone=reg.relative_phone or '',
            gender=reg.relative_gender or '',
            date_of_birth=reg.relative_date_of_birth,
        ))
    if rows:
        TripRelative.objects.bulk_create(rows)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('company_trip', '0006_domestic_trip_phones'),
    ]

    operations = [
        migrations.CreateModel(
            name='TripRelative',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(verbose_name='Thứ tự')),
                ('full_name', models.CharField(max_length=255, verbose_name='Họ tên')),
                ('cccd', models.CharField(max_length=20, verbose_name='Số CCCD')),
                ('phone', models.CharField(max_length=32, verbose_name='Số điện thoại')),
                ('gender', models.CharField(max_length=10, verbose_name='Giới tính')),
                ('date_of_birth', models.DateField(verbose_name='Ngày sinh')),
                ('registration', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='relatives',
                    to='company_trip.tripregistration',
                    verbose_name='Đăng ký',
                )),
            ],
            options={
                'verbose_name': 'Người thân',
                'verbose_name_plural': 'Người thân',
                'ordering': ['position'],
            },
        ),
        migrations.AddConstraint(
            model_name='triprelative',
            constraint=models.UniqueConstraint(fields=('registration', 'position'), name='uniq_trip_relative_position'),
        ),
        migrations.RunPython(copy_existing_relatives, noop),
    ]
