"""Đổi SĐT đăng ký từ 84xxxxxxxxx sang 0xxxxxxxxx."""

from django.db import migrations


def to_domestic(apps, schema_editor):
    from company_trip.phones import domestic_phone

    TripRegistration = apps.get_model('company_trip', 'TripRegistration')
    for reg in TripRegistration.objects.all().iterator():
        phone = domestic_phone(reg.phone)
        relative_phone = domestic_phone(reg.relative_phone)
        if phone == (reg.phone or '') and relative_phone == (reg.relative_phone or ''):
            continue
        reg.phone = phone
        reg.relative_phone = relative_phone
        reg.save(update_fields=['phone', 'relative_phone'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('company_trip', '0005_alter_tripemailtemplate_body_and_more'),
        ('hrm', '0109_trip_schedule_create_all_hcns_manage'),
    ]

    operations = [
        migrations.RunPython(to_domestic, noop),
    ]
