import django.db.models.deletion
from django.db import migrations, models


DIVISION_DEPARTMENT_MAP = {
    'QC': 'ĐẢM BẢO CHẤT LƯỢNG',
    'Ép logo': 'SẢN XUẤT',
    'Giao Hàng': 'SẢN XUẤT',
    'HCNS': 'HÀNH CHÍNH NHÂN SỰ',
    'Marketing': 'KINH DOANH - MARKETING',
    'Merchandise': 'KINH DOANH - MARKETING',
    'Thiết kế sản phẩm': 'R&D',
    'IE': 'KẾ HOẠCH SẢN XUẤT',
    'May mẫu': 'R&D',
    'Kế toán': 'TÀI CHÍNH KẾ TOÁN',
    'Kho nguyên phụ liệu': 'SẢN XUẤT',
    'Điều phối (Kiểm đếm xuất nhập hàng)': 'SẢN XUẤT',
}


def assign_division_departments(apps, schema_editor):
    Division = apps.get_model('hrm', 'Division')
    Department = apps.get_model('hrm', 'Department')
    dept_cache = {dept.name: dept for dept in Department.objects.all()}
    for division in Division.objects.filter(department__isnull=True):
        dept_name = DIVISION_DEPARTMENT_MAP.get(division.name)
        if dept_name and dept_name in dept_cache:
            division.department_id = dept_cache[dept_name].id
            division.save(update_fields=['department_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0012_profile_is_employed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='division',
            name='name',
            field=models.CharField(max_length=150, verbose_name='Tên bộ phận'),
        ),
        migrations.AddField(
            model_name='division',
            name='department',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='divisions',
                to='hrm.department',
                verbose_name='Phòng ban',
            ),
        ),
        migrations.AddConstraint(
            model_name='division',
            constraint=models.UniqueConstraint(
                fields=('department', 'name'),
                name='hrm_division_department_name_uniq',
            ),
        ),
        migrations.RunPython(assign_division_departments, noop),
    ]
