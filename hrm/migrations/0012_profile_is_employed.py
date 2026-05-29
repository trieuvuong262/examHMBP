from django.db import migrations, models


def sync_is_employed_from_user(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    for profile in Profile.objects.select_related('user').all():
        employed = profile.user.is_active
        if profile.is_employed != employed:
            profile.is_employed = employed
            profile.save(update_fields=['is_employed'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0011_gender_nam_nu_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='is_employed',
            field=models.BooleanField(db_index=True, default=True, verbose_name='Đang làm việc'),
        ),
        migrations.RunPython(sync_is_employed_from_user, noop),
    ]
