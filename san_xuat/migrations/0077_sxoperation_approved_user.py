from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def link_existing_approvers(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    SxOperation = apps.get_model('san_xuat', 'SxOperation')

    users_by_name = {}
    for user in User.objects.filter(is_active=True).iterator():
        username = (getattr(user, 'username', '') or '').strip()
        if username:
            users_by_name.setdefault(username.casefold(), user.pk)
        full_name = ' '.join(
            part for part in (
                (getattr(user, 'first_name', '') or '').strip(),
                (getattr(user, 'last_name', '') or '').strip(),
            ) if part
        )
        if full_name:
            users_by_name.setdefault(full_name.casefold(), user.pk)

    for operation in SxOperation.objects.exclude(approved_by='').filter(approved_user__isnull=True).iterator():
        user_id = users_by_name.get((operation.approved_by or '').strip().casefold())
        if user_id:
            operation.approved_user_id = user_id
            operation.save(update_fields=['approved_user'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0076_smv_minutes_to_seconds'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxoperation',
            name='approved_user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sx_operations_approved',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Tài khoản người duyệt',
            ),
        ),
        migrations.RunPython(link_existing_approvers, migrations.RunPython.noop),
    ]
