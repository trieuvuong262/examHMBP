from django.conf import settings
from django.db import migrations, models


DEFAULT_COLORS = {
    'cat': '#ffd7b0',
    'inep': '#fecaca',
    'theu': '#fef08a',
    'may': '#bfdbfe',
    'ht': '#bbf7d0',
    'gh': '#f0cfe0',
}


def seed_team_stage_colors(apps, schema_editor):
    SxTeamStageColor = apps.get_model('san_xuat', 'SxTeamStageColor')
    for slug, color in DEFAULT_COLORS.items():
        SxTeamStageColor.objects.get_or_create(
            team_slug=slug,
            defaults={'color': color},
        )


def unseed_team_stage_colors(apps, schema_editor):
    SxTeamStageColor = apps.get_model('san_xuat', 'SxTeamStageColor')
    SxTeamStageColor.objects.filter(team_slug__in=DEFAULT_COLORS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0122_plan_step_khsx_capacity'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxTeamStageColor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
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
                    unique=True,
                    verbose_name='Tổ chuyền',
                )),
                ('color', models.CharField(
                    help_text='Mã #RRGGBB — dùng cho cột bộ phận và ô SL trên lộ trình.',
                    max_length=7,
                    verbose_name='Màu KHSX',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=models.SET_NULL,
                    related_name='sx_team_stage_colors_updated',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người cập nhật',
                )),
            ],
            options={
                'verbose_name': 'Màu bộ phận KHSX',
                'verbose_name_plural': 'Màu bộ phận KHSX',
                'ordering': ['team_slug'],
            },
        ),
        migrations.RunPython(seed_team_stage_colors, unseed_team_stage_colors),
    ]
