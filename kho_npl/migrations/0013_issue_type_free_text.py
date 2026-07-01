from django.db import migrations, models

LEGACY_ISSUE_TYPE_LABELS = {
    'production': 'Xuất cho sản xuất',
    'sample': 'Xuất làm mẫu',
    'waste': 'Xuất bù hao hụt',
    'return_supplier': 'Xuất trả nhà cung cấp',
    'scrap': 'Xuất hủy / hư hỏng',
    'transfer': 'Xuất điều chuyển kho',
}


def convert_legacy_issue_types(apps, schema_editor):
    StockIssue = apps.get_model('kho_npl', 'StockIssue')
    for issue in StockIssue.objects.all().iterator():
        label = LEGACY_ISSUE_TYPE_LABELS.get(issue.issue_type)
        if label:
            issue.issue_type = label
            issue.save(update_fields=['issue_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0012_stockissue_recipient'),
    ]

    operations = [
        migrations.RunPython(convert_legacy_issue_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stockissue',
            name='issue_type',
            field=models.CharField(
                blank=True,
                default='',
                max_length=120,
                verbose_name='Lý do xuất',
            ),
        ),
    ]
