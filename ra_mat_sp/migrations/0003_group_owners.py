from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ra_mat_sp', '0002_default_checklist'),
    ]

    operations = [
        migrations.CreateModel(
            name='LaunchGroupDefault',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.CharField(
                    choices=[
                        ('product', 'Sản phẩm & kỹ thuật'),
                        ('production', 'Sản xuất & cung ứng'),
                        ('price', 'Giá & kinh doanh'),
                        ('marketing', 'Marketing'),
                        ('channel', 'Kênh bán hàng'),
                        ('logistics', 'Kho vận'),
                        ('approval', 'Phê duyệt & điều kiện'),
                    ],
                    max_length=20,
                    unique=True,
                    verbose_name='Nhóm',
                )),
                ('owner', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người chịu trách nhiệm',
                )),
            ],
            options={
                'verbose_name': 'Phụ trách nhóm mặc định',
                'verbose_name_plural': 'Phụ trách nhóm mặc định',
                'db_table': 'ra_mat_sp_group_default',
            },
        ),
        migrations.CreateModel(
            name='LaunchPlanGroupOwner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.CharField(
                    choices=[
                        ('product', 'Sản phẩm & kỹ thuật'),
                        ('production', 'Sản xuất & cung ứng'),
                        ('price', 'Giá & kinh doanh'),
                        ('marketing', 'Marketing'),
                        ('channel', 'Kênh bán hàng'),
                        ('logistics', 'Kho vận'),
                        ('approval', 'Phê duyệt & điều kiện'),
                    ],
                    max_length=20,
                    verbose_name='Nhóm',
                )),
                ('owner', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ra_mat_group_owned',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người chịu trách nhiệm',
                )),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='group_owners',
                    to='ra_mat_sp.launchplan',
                )),
            ],
            options={
                'verbose_name': 'Phụ trách nhóm trên kế hoạch',
                'verbose_name_plural': 'Phụ trách nhóm trên kế hoạch',
                'db_table': 'ra_mat_sp_plan_group_owner',
            },
        ),
        migrations.AddConstraint(
            model_name='launchplangroupowner',
            constraint=models.UniqueConstraint(fields=('plan', 'group'), name='ra_mat_sp_plan_group_owner_uniq'),
        ),
    ]
