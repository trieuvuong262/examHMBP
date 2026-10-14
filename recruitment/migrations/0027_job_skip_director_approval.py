from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0026_candidate_cv_nas_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobposting',
            name='skip_director_approval',
            field=models.BooleanField(default=False, verbose_name='Bỏ qua giám đốc duyệt'),
        ),
        migrations.AlterField(
            model_name='interview',
            name='final_result',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', '—'),
                    ('pending', 'Chờ giám đốc duyệt'),
                    ('pass', 'Giám đốc duyệt Đạt'),
                    ('fail', 'Giám đốc duyệt Không đạt'),
                    ('skipped', 'Không cần giám đốc duyệt'),
                ],
                db_index=True,
                default='',
                max_length=10,
                verbose_name='Duyệt cấp 2',
            ),
        ),
    ]
