from django.db import migrations

from hrm.choices import LEGACY_POSITION_MAP, normalize_position


def migrate_positions(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    JobPosting = apps.get_model('recruitment', 'JobPosting')

    for profile in Profile.objects.all().only('id', 'position'):
        new_pos = normalize_position(profile.position)
        if profile.position != new_pos:
            profile.position = new_pos
            profile.save(update_fields=['position'])

    for job in JobPosting.objects.all().only('id', 'position'):
        new_pos = normalize_position(job.position)
        if job.position != new_pos:
            job.position = new_pos
            job.save(update_fields=['position'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0002_profile_role_profile_subordinates'),
        ('recruitment', '0005_remove_candidate_new_license_number_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_positions, migrations.RunPython.noop),
    ]
