# Generated manually for catalog types / styles / KV map

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_types(apps, schema_editor):
    ProductType = apps.get_model('kho_san_pham', 'ProductType')
    rows = [
        ('TEE', 'Áo thun', 10),
        ('POLO', 'Áo polo', 20),
        ('JKT', 'Áo khoác', 30),
        ('TANK', 'Áo ba lỗ', 40),
        ('SHRT', 'Quần short', 50),
        ('PANT', 'Quần dài', 60),
        ('LGG', 'Legging', 70),
        ('SKT', 'Váy thể thao', 80),
        ('SET', 'Bộ sản phẩm', 90),
        ('SWM', 'Đồ bơi', 100),
        ('ACC', 'Phụ kiện', 110),
        ('SET-SC', 'Bộ bóng đá', 120),
        ('SET-VB', 'Bộ bóng chuyền', 130),
        ('SET-BB', 'Bộ bóng rổ', 140),
        ('SJY-SC', 'Áo bóng đá', 150),
        ('SJY-VB', 'Áo bóng chuyền', 160),
        ('ACC-BALO', 'Balo', 170),
        ('ACC-BAG', 'Túi', 180),
        ('ACC-SHCK', 'Vớ', 190),
        ('ACC-HAT', 'Nón/mũ', 200),
    ]
    for code, name, order in rows:
        ProductType.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )


def unseed_types(apps, schema_editor):
    ProductType = apps.get_model('kho_san_pham', 'ProductType')
    ProductType.objects.filter(
        code__in=[
            'TEE', 'POLO', 'JKT', 'TANK', 'SHRT', 'PANT', 'LGG', 'SKT', 'SET', 'SWM',
            'ACC', 'SET-SC', 'SET-VB', 'SET-BB', 'SJY-SC', 'SJY-VB',
            'ACC-BALO', 'ACC-BAG', 'ACC-SHCK', 'ACC-HAT',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_san_pham', '0002_product_sku_style_color_size'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True, verbose_name='Mã loại')),
                ('name', models.CharField(max_length=120, verbose_name='Nội dung')),
                ('sort_order', models.PositiveSmallIntegerField(db_index=True, default=100)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'verbose_name': 'Loại sản phẩm (mã)',
                'verbose_name_plural': 'Loại sản phẩm (mã)',
                'db_table': 'kho_sp_product_type',
                'ordering': ['sort_order', 'code'],
            },
        ),
        migrations.CreateModel(
            name='ProductStyle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=80, unique=True, verbose_name='Mã Style')),
                ('name', models.CharField(blank=True, default='', max_length=500, verbose_name='Tên / mô tả')),
                ('brand', models.CharField(default='JP', max_length=16, verbose_name='Brand')),
                ('year', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Năm')),
                ('sequence', models.PositiveIntegerField(blank=True, null=True, verbose_name='STT')),
                ('root_kiotviet_code', models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='Mã KV gốc')),
                ('source', models.CharField(choices=[('manual', 'Nhập tay'), ('kiotviet', 'KiotViet')], default='manual', max_length=20, verbose_name='Nguồn')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kho_sp_styles_created', to=settings.AUTH_USER_MODEL)),
                ('product_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='styles', to='kho_san_pham.producttype', verbose_name='Loại')),
            ],
            options={
                'verbose_name': 'Style',
                'verbose_name_plural': 'Style',
                'db_table': 'kho_sp_product_style',
                'ordering': ['code'],
            },
        ),
        migrations.CreateModel(
            name='ProductTypeKvMap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('match_value', models.CharField(max_length=255, verbose_name='Nhóm hàng KV')),
                ('match_mode', models.CharField(choices=[('exact', 'Khớp đúng'), ('contains', 'Chứa chuỗi')], default='exact', max_length=20, verbose_name='Kiểu khớp')),
                ('priority', models.PositiveSmallIntegerField(default=100, help_text='Số nhỏ = ưu tiên cao hơn.')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('product_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kv_maps', to='kho_san_pham.producttype', verbose_name='Loại mã')),
            ],
            options={
                'verbose_name': 'Map nhóm hàng KV → loại',
                'verbose_name_plural': 'Map nhóm hàng KV → loại',
                'db_table': 'kho_sp_product_type_kv_map',
                'ordering': ['priority', 'match_value'],
            },
        ),
        migrations.AddField(
            model_name='product',
            name='catalog_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products', to='kho_san_pham.producttype', verbose_name='Loại mã'),
        ),
        migrations.AlterField(
            model_name='product',
            name='style_code',
            field=models.CharField(blank=True, db_index=True, default='', help_text='Mã Style (vd. JP-TEE-260001, JP-SET-SC-SP002771).', max_length=80, verbose_name='Style'),
        ),
        migrations.AddIndex(
            model_name='productstyle',
            index=models.Index(fields=['product_type', 'year'], name='kho_sp_prod_product_5b0f0a_idx'),
        ),
        migrations.AddIndex(
            model_name='productstyle',
            index=models.Index(fields=['source', 'is_active'], name='kho_sp_prod_source_8d2c1a_idx'),
        ),
        migrations.AddConstraint(
            model_name='producttypekvmap',
            constraint=models.UniqueConstraint(fields=('match_value', 'match_mode'), name='kho_sp_type_kv_map_uniq'),
        ),
        migrations.RunPython(seed_types, unseed_types),
    ]
