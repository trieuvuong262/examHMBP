import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import utilities.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('utilities', '0013_meal_eligible_employee'),
    ]

    operations = [
        migrations.CreateModel(
            name='GomokuStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wins', models.PositiveIntegerField(default=0, verbose_name='Thắng')),
                ('losses', models.PositiveIntegerField(default=0, verbose_name='Thua')),
                ('draws', models.PositiveIntegerField(default=0, verbose_name='Hòa')),
                ('elo', models.PositiveIntegerField(default=1000, verbose_name='Elo')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='gomoku_stats', to=settings.AUTH_USER_MODEL, verbose_name='Nhân viên')),
            ],
            options={
                'verbose_name': 'Điểm Caro',
                'verbose_name_plural': 'Điểm Caro',
            },
        ),
        migrations.CreateModel(
            name='GomokuRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=4, verbose_name='Mã phòng')),
                ('status', models.CharField(choices=[('waiting', 'Đang chờ'), ('playing', 'Đang chơi'), ('finished', 'Đã kết thúc'), ('closed', 'Đã đóng')], db_index=True, default='waiting', max_length=16, verbose_name='Trạng thái')),
                ('board', models.JSONField(default=utilities.models.gomoku_empty_board, verbose_name='Bàn cờ')),
                ('host_color', models.CharField(choices=[('black', 'Đen'), ('white', 'Trắng')], default='black', max_length=8, verbose_name='Màu chủ phòng')),
                ('turn', models.CharField(choices=[('black', 'Đen'), ('white', 'Trắng')], default='black', max_length=8, verbose_name='Lượt đi')),
                ('move_count', models.PositiveIntegerField(default=0, verbose_name='Số nước')),
                ('last_row', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Hàng nước cuối')),
                ('last_col', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Cột nước cuối')),
                ('turn_deadline', models.DateTimeField(blank=True, null=True, verbose_name='Hết giờ lượt')),
                ('host_rematch', models.BooleanField(default=False, verbose_name='Chủ phòng muốn chơi lại')),
                ('guest_rematch', models.BooleanField(default=False, verbose_name='Khách muốn chơi lại')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('draw_offer_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Người xin hòa')),
                ('guest', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='gomoku_rooms_joined', to=settings.AUTH_USER_MODEL, verbose_name='Người vào')),
                ('host', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gomoku_rooms_hosted', to=settings.AUTH_USER_MODEL, verbose_name='Chủ phòng')),
            ],
            options={
                'verbose_name': 'Phòng Caro',
                'verbose_name_plural': 'Phòng Caro',
            },
        ),
        migrations.CreateModel(
            name='GomokuGame',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('result', models.CharField(choices=[('black', 'Đen thắng'), ('white', 'Trắng thắng'), ('draw', 'Hòa')], max_length=8, verbose_name='Kết quả')),
                ('reason', models.CharField(choices=[('five', 'Năm quân'), ('resign', 'Đầu hàng'), ('timeout', 'Hết giờ'), ('draw', 'Xin hòa')], max_length=16, verbose_name='Lý do')),
                ('black_elo_before', models.PositiveIntegerField(verbose_name='Elo đen trước ván')),
                ('black_elo_after', models.PositiveIntegerField(verbose_name='Elo đen sau ván')),
                ('white_elo_before', models.PositiveIntegerField(verbose_name='Elo trắng trước ván')),
                ('white_elo_after', models.PositiveIntegerField(verbose_name='Elo trắng sau ván')),
                ('finished_at', models.DateTimeField(auto_now_add=True, verbose_name='Kết thúc')),
                ('black', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gomoku_games_as_black', to=settings.AUTH_USER_MODEL, verbose_name='Quân đen')),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='games', to='utilities.gomokuroom', verbose_name='Phòng')),
                ('white', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gomoku_games_as_white', to=settings.AUTH_USER_MODEL, verbose_name='Quân trắng')),
            ],
            options={
                'verbose_name': 'Ván Caro',
                'verbose_name_plural': 'Ván Caro',
                'ordering': ['-finished_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='gomokuroom',
            index=models.Index(fields=['host', 'status'], name='util_gomoku_host_status_idx'),
        ),
        migrations.AddIndex(
            model_name='gomokuroom',
            index=models.Index(fields=['guest', 'status'], name='util_gomoku_guest_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='gomokuroom',
            constraint=models.UniqueConstraint(condition=models.Q(status__in=['waiting', 'playing', 'finished']), fields=('code',), name='utilities_gomoku_open_code_uniq'),
        ),
        migrations.AddIndex(
            model_name='gomokugame',
            index=models.Index(fields=['black', 'finished_at'], name='util_gomoku_black_played_idx'),
        ),
        migrations.AddIndex(
            model_name='gomokugame',
            index=models.Index(fields=['white', 'finished_at'], name='util_gomoku_white_played_idx'),
        ),
    ]
