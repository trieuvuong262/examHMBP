import django.db.models.deletion
from django.db import migrations, models

# Giá trị cũ (danh sách cứng) → mã Loại trong danh mục Kho sản phẩm; không khớp thì để trống cho người dùng chọn lại.
OLD_TYPE_CODES = {
    'ao': 'TEE',
    'quan': 'SHRT',
    'bo': 'SET',
    'ao_khoac': 'JKT',
    'polo': 'POLO',
    'phu_kien': 'ACC',
}
OLD_GROUP_TYPE_CODES = {
    ('bong_da', 'ao'): 'SJY-SC',
    ('bong_da', 'bo'): 'SET-SC',
    ('bong_chuyen', 'ao'): 'SJY-VB',
    ('bong_chuyen', 'bo'): 'SET-VB',
    ('bong_ro', 'bo'): 'SET-BB',
}


def forwards(apps, schema_editor):
    Dossier = apps.get_model('thiet_ke_sp', 'ProductDevelopment')
    CatalogType = apps.get_model('kho_san_pham', 'ProductType')
    types = {t.code: t for t in CatalogType.objects.all()}
    for dossier in Dossier.objects.all().only('pk', 'product_group', 'product_type'):
        code = OLD_GROUP_TYPE_CODES.get((dossier.product_group, dossier.product_type)) or OLD_TYPE_CODES.get(
            dossier.product_type,
        )
        ptype = types.get(code)
        Dossier.objects.filter(pk=dossier.pk).update(
            catalog_type=ptype,
            product_group=ptype.code.split('-', 1)[0] if ptype else '',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0003_catalog_type_style_kv_map'),
        ('thiet_ke_sp', '0003_dossier_members_product_photos'),
    ]

    operations = [
        migrations.AddField(
            model_name='productdevelopment',
            name='catalog_type',
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to='kho_san_pham.producttype',
            ),
        ),
        migrations.AlterField(
            model_name='productdevelopment',
            name='product_group',
            field=models.CharField(
                blank=True, db_index=True, default='', max_length=32, verbose_name='Nhóm sản phẩm',
                help_text='Mã nhóm trong danh mục Loại mã (SET-SC → SET).',
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
