from django.db import migrations, models


def clear_other_gender(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    Profile.objects.filter(gender='O').update(gender='')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0010_profile_roles_four_levels'),
    ]

    operations = [
        migrations.RunPython(clear_other_gender, noop),
        migrations.AlterField(
            model_name='profile',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('M', 'Nam'), ('F', 'Nữ')],
                max_length=1,
                verbose_name='Giới tính',
            ),
        ),
    ]
