# Generated manually for Style → SKU (Style + Color + Size)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_COLORS = [
    ("NVY", "Navy", 10),
    ("BLK", "Đen", 20),
    ("WHT", "Trắng", 30),
    ("GRY", "Xám", 40),
    ("RED", "Đỏ", 50),
    ("BLU", "Xanh dương", 60),
    ("GRN", "Xanh lá", 70),
    ("BEG", "Be", 80),
]

DEFAULT_SIZES = [
    ("XS", "XS", 10),
    ("S", "S", 20),
    ("M", "M", 30),
    ("L", "L", 40),
    ("XL", "XL", 50),
    ("XXL", "XXL", 60),
    ("3XL", "3XL", 70),
]


def seed_colors_sizes(apps, schema_editor):
    SxColor = apps.get_model("san_xuat", "SxColor")
    SxSize = apps.get_model("san_xuat", "SxSize")
    for code, name, order in DEFAULT_COLORS:
        SxColor.objects.get_or_create(
            code=code,
            defaults={"name": name, "sort_order": order, "is_active": True, "is_demo": False},
        )
    for code, name, order in DEFAULT_SIZES:
        SxSize.objects.get_or_create(
            code=code,
            defaults={"name": name, "sort_order": order, "is_active": True, "is_demo": False},
        )


def unseed_colors_sizes(apps, schema_editor):
    SxColor = apps.get_model("san_xuat", "SxColor")
    SxSize = apps.get_model("san_xuat", "SxSize")
    SxColor.objects.filter(code__in=[c for c, _, _ in DEFAULT_COLORS]).delete()
    SxSize.objects.filter(code__in=[c for c, _, _ in DEFAULT_SIZES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("san_xuat", "0028_sxgeneralsettings_list_default_date_range_3"),
    ]

    operations = [
        migrations.CreateModel(
            name="SxColor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_demo", models.BooleanField(db_index=True, default=False, verbose_name="Dữ liệu demo")),
                ("code", models.CharField(max_length=20, unique=True, verbose_name="Mã màu")),
                ("name", models.CharField(max_length=80, verbose_name="Tên màu")),
                ("sort_order", models.PositiveSmallIntegerField(db_index=True, default=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Người tạo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Màu (SKU)",
                "verbose_name_plural": "Màu (SKU)",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.CreateModel(
            name="SxSize",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_demo", models.BooleanField(db_index=True, default=False, verbose_name="Dữ liệu demo")),
                ("code", models.CharField(max_length=20, unique=True, verbose_name="Size")),
                ("name", models.CharField(blank=True, default="", max_length=80, verbose_name="Tên hiển thị")),
                ("sort_order", models.PositiveSmallIntegerField(db_index=True, default=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Người tạo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Size (SKU)",
                "verbose_name_plural": "Size (SKU)",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.CreateModel(
            name="SxSku",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_demo", models.BooleanField(db_index=True, default=False, verbose_name="Dữ liệu demo")),
                ("style_code", models.CharField(db_index=True, help_text="Mã Style = product_code hồ sơ / lệnh sản xuất.", max_length=60, verbose_name="Style (mã SP)")),
                ("style_name", models.CharField(blank=True, default="", max_length=255)),
                ("color_code", models.CharField(db_index=True, max_length=20, verbose_name="Mã màu")),
                ("color_label", models.CharField(blank=True, default="", max_length=80, verbose_name="Tên màu")),
                ("size_label", models.CharField(db_index=True, max_length=20, verbose_name="Size")),
                ("sku_code", models.CharField(max_length=100, unique=True, verbose_name="SKU")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Người tạo",
                    ),
                ),
            ],
            options={
                "verbose_name": "SKU",
                "verbose_name_plural": "SKU",
                "ordering": ["style_code", "color_code", "size_label"],
            },
        ),
        migrations.CreateModel(
            name="SxFgReceiptLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku_code", models.CharField(blank=True, default="", max_length=100, verbose_name="SKU")),
                ("size_label", models.CharField(blank=True, default="", max_length=40, verbose_name="Size")),
                ("color_label", models.CharField(blank=True, default="", max_length=40, verbose_name="Màu")),
                ("color_code", models.CharField(blank=True, default="", max_length=20, verbose_name="Mã màu")),
                ("qty", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                (
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="san_xuat.sxfgreceiptrequest",
                    ),
                ),
                (
                    "sku",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fg_receipt_lines",
                        to="san_xuat.sxsku",
                    ),
                ),
            ],
            options={
                "verbose_name": "Dòng nhập thành phẩm",
                "verbose_name_plural": "Dòng nhập thành phẩm",
                "ordering": ["pk"],
            },
        ),
        migrations.AddField(
            model_name="sxgeneralsettings",
            name="gate_sku_on_packing",
            field=models.CharField(
                choices=[("off", "Tắt — không kiểm tra"), ("warn", "Cảnh báo — cho phép nhưng nhắc"), ("block", "Chặn — bắt buộc đúng bước")],
                default="warn",
                max_length=10,
                verbose_name="Bắt buộc SKU trên mỗi dòng đóng gói có SL",
            ),
        ),
        migrations.AddField(
            model_name="sxgeneralsettings",
            name="gate_sku_on_stat",
            field=models.CharField(
                choices=[("off", "Tắt — không kiểm tra"), ("warn", "Cảnh báo — cho phép nhưng nhắc"), ("block", "Chặn — bắt buộc đúng bước")],
                default="warn",
                help_text="SKU = Style + Màu + Size. Style lấy từ mã SP trên lệnh.",
                max_length=10,
                verbose_name="Bắt buộc SKU (màu + size) khi ghi thống kê sản xuất",
            ),
        ),
        migrations.AddField(
            model_name="sxpackingline",
            name="color_code",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Mã màu"),
        ),
        migrations.AddField(
            model_name="sxpackingline",
            name="sku",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="packing_lines",
                to="san_xuat.sxsku",
                verbose_name="SKU (master)",
            ),
        ),
        migrations.AddField(
            model_name="sxproductionstat",
            name="color_code",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Mã màu"),
        ),
        migrations.AddField(
            model_name="sxproductionstat",
            name="sku",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="production_stats",
                to="san_xuat.sxsku",
                verbose_name="SKU (master)",
            ),
        ),
        migrations.AddField(
            model_name="sxqcrequest",
            name="color_code",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Mã màu"),
        ),
        migrations.AddField(
            model_name="sxqcrequest",
            name="sku",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="qc_requests",
                to="san_xuat.sxsku",
                verbose_name="SKU (master)",
            ),
        ),
        migrations.AlterField(
            model_name="sxpackingline",
            name="sku_code",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="SKU"),
        ),
        migrations.AlterField(
            model_name="sxproductionstat",
            name="sku_code",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="SKU"),
        ),
        migrations.AlterField(
            model_name="sxqcrequest",
            name="sku_code",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="SKU"),
        ),
        migrations.AddConstraint(
            model_name="sxsku",
            constraint=models.UniqueConstraint(
                fields=("style_code", "color_code", "size_label"),
                name="sx_sku_style_color_size_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="sxsku",
            index=models.Index(fields=["style_code", "is_active"], name="sx_sku_style_active_idx"),
        ),
        migrations.RunPython(seed_colors_sizes, unseed_colors_sizes),
    ]
