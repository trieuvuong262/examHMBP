from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


ATTACHMENT_MODELS = (
    'stockreceipt',
    'stockissue',
    'stocktransfer',
    'stockadjustment',
    'stockdisposal',
    'stocktake',
)


def backfill_doc_attachments(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    NplDocAttachment = apps.get_model('kho_npl', 'NplDocAttachment')
    for model_name in ATTACHMENT_MODELS:
        Model = apps.get_model('kho_npl', model_name)
        ct = ContentType.objects.get(app_label='kho_npl', model=model_name)
        for obj in Model.objects.all():
            attachment = getattr(obj, 'attachment', None)
            if not attachment or not getattr(attachment, 'name', ''):
                continue
            NplDocAttachment.objects.create(
                content_type=ct,
                object_id=obj.pk,
                file=attachment.name,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_npl', '0019_backfill_material_category_levels'),
    ]

    operations = [
        migrations.CreateModel(
            name='NplDocAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('file', models.FileField(upload_to='npl/doc_attachments/%Y/%m/', verbose_name='Chứng từ / ảnh')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='npl_doc_attachments_uploaded', to=settings.AUTH_USER_MODEL, verbose_name='Người tải lên')),
            ],
            options={
                'verbose_name': 'Chứng từ đính kèm',
                'verbose_name_plural': 'Chứng từ đính kèm',
                'ordering': ['uploaded_at', 'pk'],
            },
        ),
        migrations.AddIndex(
            model_name='npldocattachment',
            index=models.Index(fields=['content_type', 'object_id'], name='kho_npl_npl_content_6a8f0d_idx'),
        ),
        migrations.RunPython(backfill_doc_attachments, migrations.RunPython.noop),
    ]
