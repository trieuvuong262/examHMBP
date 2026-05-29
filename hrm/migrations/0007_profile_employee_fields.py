from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0006_profile_must_change_password'),
    ]

    operations = [
        migrations.RenameField(
            model_name='profile',
            old_name='position',
            new_name='job_position',
        ),
        migrations.AlterField(
            model_name='profile',
            name='job_position',
            field=models.CharField(
                blank=True,
                default='Công nhân may',
                max_length=100,
                verbose_name='Vị trí',
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='employee_code',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=50,
                null=True,
                unique=True,
                verbose_name='Mã NS',
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='department',
            field=models.CharField(blank=True, max_length=100, verbose_name='Phòng ban'),
        ),
        migrations.AddField(
            model_name='profile',
            name='division',
            field=models.CharField(blank=True, max_length=100, verbose_name='Bộ phận'),
        ),
        migrations.AddField(
            model_name='profile',
            name='job_title',
            field=models.CharField(blank=True, max_length=100, verbose_name='Chức vụ'),
        ),
        migrations.AddField(
            model_name='profile',
            name='join_date',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày vào'),
        ),
        migrations.AddField(
            model_name='profile',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày sinh'),
        ),
        migrations.AddField(
            model_name='profile',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('', '---'), ('M', 'Nam'), ('F', 'Nữ'), ('O', 'Khác')],
                max_length=1,
                verbose_name='Giới tính',
            ),
        ),
    ]
