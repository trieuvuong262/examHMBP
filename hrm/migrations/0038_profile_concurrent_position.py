from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0037_add_kiotviet_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfileConcurrentPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_position', models.CharField(blank=True, default='', max_length=100, verbose_name='Vị trí')),
                ('job_title', models.CharField(blank=True, max_length=100, verbose_name='Chức vụ')),
                ('role', models.CharField(
                    choices=[
                        ('EMPLOYEE', 'Nhân viên'),
                        ('TEAM_LEADER', 'Tổ trưởng'),
                        ('DIVISION_HEAD', 'Trưởng bộ phận'),
                        ('DIRECTOR', 'Giám đốc'),
                    ],
                    default='EMPLOYEE',
                    max_length=20,
                    verbose_name='Vai trò tại vị trí kiêm nhiệm',
                )),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang hiệu lực')),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('department', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='concurrent_position_slots',
                    to='hrm.department',
                    verbose_name='Phòng ban',
                )),
                ('division', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='concurrent_position_slots',
                    to='hrm.division',
                    verbose_name='Bộ phận',
                )),
                ('profile', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='concurrent_positions',
                    to='hrm.profile',
                    verbose_name='Nhân viên',
                )),
            ],
            options={
                'verbose_name': 'Vị trí kiêm nhiệm',
                'verbose_name_plural': 'Vị trí kiêm nhiệm',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='profileconcurrentposition',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_active', True)),
                fields=('profile', 'department', 'division', 'job_position'),
                name='hrm_concurrent_slot_active_uniq',
            ),
        ),
    ]
