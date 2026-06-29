"""Xuất danh sách user + mật khẩu gợi ý ra Excel (CLI / IT)."""

import io
from pathlib import Path

import pandas as pd
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from hrm.choices import EXCEL_ALL_HEADERS, user_to_excel_row
from hrm.user_search import apply_user_list_sort, exclude_hidden_hrm_users


class Command(BaseCommand):
    help = (
        'Xuất Excel danh sách nhân viên. Cột password: trống nếu đã đăng nhập và đổi MK; '
        'ngược lại hiển thị mật khẩu mặc định Portal.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '-o', '--output',
            default='Danh_sach_dang_nhap.xlsx',
            help='Đường dẫn file .xlsx đầu ra (mặc định: Danh_sach_dang_nhap.xlsx)',
        )
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Chỉ user đang làm việc (is_employed=True).',
        )

    def handle(self, *args, **options):
        output_path = Path(options['output']).expanduser().resolve()
        users = User.objects.select_related(
            'profile',
            'profile__department',
            'profile__division',
            'profile__permission_group',
        )
        users = exclude_hidden_hrm_users(users)
        if options['active_only']:
            users = users.filter(profile__is_employed=True)
        users = apply_user_list_sort(users, 'username', 'asc')

        rows = [user_to_excel_row(u) for u in users]
        df = pd.DataFrame(rows, columns=EXCEL_ALL_HEADERS)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Nhan_Vien')
        output_path.write_bytes(buffer.getvalue())

        with_default = sum(1 for r in rows if r.get('password'))
        self.stdout.write(self.style.SUCCESS(
            f'Đã xuất {len(rows)} user → {output_path} '
            f'({with_default} user còn mật khẩu mặc định).',
        ))
