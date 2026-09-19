from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_default_template(apps, schema_editor):
    CertificateTemplate = apps.get_model('assessment', 'CertificateTemplate')
    if CertificateTemplate.objects.exists():
        return
    CertificateTemplate.objects.create(
        name='Mẫu JustPlay mặc định',
        heading='CERTIFICATE',
        ribbon_text='OF ACHIEVEMENT',
        presented_label='THIS CERTIFICATE IS PROUDLY PRESENTED TO',
        body_text=(
            'Chứng nhận đã hoàn thành kỳ thi «{exam_title}» với số điểm {score}. '
            'Chứng chỉ số {code}, cấp ngày {date}.'
        ),
        issuer_name='JustPlay.vn',
        issuer_title='Ban Đào tạo',
        seal_text='JUST PLAY',
        is_default=True,
        is_active=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0009_choice_sort_order'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Tên mẫu')),
                ('heading', models.CharField(default='CERTIFICATE', max_length=120, verbose_name='Tiêu đề lớn')),
                ('ribbon_text', models.CharField(default='OF ACHIEVEMENT', max_length=80, verbose_name='Dòng phụ')),
                ('presented_label', models.CharField(default='THIS CERTIFICATE IS PROUDLY PRESENTED TO', max_length=160, verbose_name='Dòng giới thiệu')),
                ('body_text', models.TextField(default='Chứng nhận đã hoàn thành kỳ thi «{exam_title}» với số điểm {score}. Chứng chỉ số {code}, cấp ngày {date}.', help_text='Có thể dùng {name}, {exam_title}, {score}, {date}, {code}.', verbose_name='Nội dung')),
                ('issuer_name', models.CharField(default='JustPlay.vn', max_length=120, verbose_name='Đơn vị cấp')),
                ('issuer_title', models.CharField(default='Ban Đào tạo', max_length=120, verbose_name='Chức danh ký')),
                ('seal_text', models.CharField(default='JUST PLAY', max_length=40, verbose_name='Chữ trên huy hiệu')),
                ('is_default', models.BooleanField(default=False, verbose_name='Mẫu mặc định')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Mẫu chứng chỉ',
                'verbose_name_plural': 'Mẫu chứng chỉ',
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.AddField(
            model_name='exam',
            name='issue_certificate',
            field=models.BooleanField(default=True, verbose_name='Cấp chứng chỉ khi hoàn thành'),
        ),
        migrations.AddField(
            model_name='exam',
            name='pass_score',
            field=models.FloatField(default=5.0, help_text='Thí sinh đạt từ mức này trở lên mới được cấp chứng chỉ.', verbose_name='Điểm đạt (cấp chứng chỉ)'),
        ),
        migrations.AddField(
            model_name='exam',
            name='certificate_template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exams', to='assessment.certificatetemplate', verbose_name='Mẫu chứng chỉ'),
        ),
        migrations.CreateModel(
            name='Certificate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True, verbose_name='Mã chứng chỉ')),
                ('recipient_name', models.CharField(max_length=255, verbose_name='Họ tên trên chứng chỉ')),
                ('exam_title', models.CharField(max_length=255, verbose_name='Tên kỳ thi')),
                ('score', models.FloatField(default=0, verbose_name='Điểm')),
                ('body_text', models.TextField(blank=True, verbose_name='Nội dung đã điền')),
                ('issued_at', models.DateTimeField(auto_now_add=True, verbose_name='Ngày cấp')),
                ('is_revoked', models.BooleanField(default=False, verbose_name='Đã thu hồi')),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certificates', to='assessment.exam')),
                ('revoked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revoked_certificates', to=settings.AUTH_USER_MODEL)),
                ('submission', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='certificates', to='assessment.examsubmission')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issued_certificates', to='assessment.certificatetemplate')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certificates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Chứng chỉ',
                'verbose_name_plural': 'Chứng chỉ',
                'ordering': ['-issued_at'],
                'unique_together': {('user', 'exam')},
            },
        ),
        migrations.RunPython(seed_default_template, noop),
    ]
