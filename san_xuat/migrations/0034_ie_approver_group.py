from django.db import migrations


def create_ie_approver_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='SX_IE_Approver')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0033_alter_sxrouting_approval_status'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_ie_approver_group, noop_reverse),
    ]
