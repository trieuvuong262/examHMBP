from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0074_sxsalesorderline_bom_line_overrides'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxTeamPersonnelSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_demo', models.BooleanField(db_index=True, default=False, verbose_name='Dữ liệu demo')),
                ('team_slug', models.CharField(
                    choices=[
                        ('cat', 'Cắt'),
                        ('inep', 'In - Ép'),
                        ('theu', 'Thêu'),
                        ('may', 'May'),
                        ('ht', 'Ủi - Gấp xếp'),
                        ('gh', 'Giao hàng thành phẩm'),
                    ],
                    db_index=True,
                    max_length=20,
                    verbose_name='Tổ chuyền',
                )),
                ('process_keys', models.JSONField(
                    blank=True,
                    default=list,
                    help_text='Danh sách key công đoạn theo mẫu tổ (progress_template).',
                    verbose_name='Công đoạn làm được',
                )),
                ('skill_level', models.CharField(
                    blank=True,
                    choices=[('', 'Chưa xếp'), ('A', 'A'), ('B', 'B'), ('C', 'C')],
                    db_index=True,
                    default='',
                    max_length=1,
                    verbose_name='Cấp kỹ năng',
                )),
                ('machines', models.CharField(
                    blank=True,
                    default='',
                    max_length=255,
                    verbose_name='Máy / thiết bị vận hành',
                )),
                ('is_multiskill', models.BooleanField(db_index=True, default=False, verbose_name='Đa năng')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Ghi chú tổ trưởng')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Cập nhật lúc')),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(app_label)s_%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sx_team_personnel_skills_updated',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người cập nhật',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sx_team_personnel_skills',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Nhân viên',
                )),
            ],
            options={
                'verbose_name': 'Năng lực nhân sự tổ',
                'verbose_name_plural': 'Năng lực nhân sự tổ',
                'ordering': ['team_slug', 'user_id'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxteampersonnelskill',
            constraint=models.UniqueConstraint(
                fields=('user', 'team_slug'),
                name='san_xuat_team_personnel_skill_user_slug_uniq',
            ),
        ),
    ]
