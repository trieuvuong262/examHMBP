"""Test lớp chặn file upload độc hại trước khi ghi lên NAS."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from nas_storage.upload_guard import (
    GROUP_ARCHIVE,
    GROUP_DOC,
    GROUP_IMAGE,
    GROUP_VIDEO,
    UploadRejected,
    allowed_extensions,
    validate_upload,
    validate_uploads,
)

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 40
JPEG = b'\xff\xd8\xff\xe0' + b'0' * 40
GIF = b'GIF89a' + b'0' * 40
PDF = b'%PDF-1.7\n' + b'0' * 40
ZIP = b'PK\x03\x04' + b'0' * 40
OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'0' * 40
MKV = b'\x1a\x45\xdf\xa3' + b'0' * 40
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'0' * 40
EXE = b'MZ\x90\x00' + b'0' * 40
ELF = b'\x7fELF\x02\x01\x01\x00' + b'0' * 40


def up(name: str, content: bytes = PNG, content_type: str = 'application/octet-stream'):
    return SimpleUploadedFile(name, content, content_type=content_type)


class AcceptsRealWorldFilesTests(SimpleTestCase):
    """Các định dạng đang thực dùng trong DB phải tiếp tục được nhận."""

    def test_accepts_formats_found_in_database(self):
        cases = [
            ('anh.jpg', JPEG), ('anh.jpeg', JPEG), ('anh.png', PNG),
            ('bao-cao.pdf', PDF),
            ('bang.xlsx', ZIP), ('van-ban.docx', ZIP), ('bang.ods', ZIP),
            ('cu.doc', OLE), ('cu.xls', OLE),
            ('goi.zip', ZIP),
            ('video.mp4', MP4), ('video.mkv', MKV),
        ]
        for name, content in cases:
            with self.subTest(name=name):
                self.assertEqual(validate_upload(up(name, content)), name)

    def test_accepts_vietnamese_filename(self):
        name = 'Báo cáo tuần 39 — Tổ May 1.pdf'
        self.assertEqual(validate_upload(up(name, PDF)), name)

    def test_strips_path_components(self):
        self.assertEqual(validate_upload(up('C:\\Users\\a\\anh.png', PNG)), 'anh.png')
        self.assertEqual(validate_upload(up('../../etc/anh.png', PNG)), 'anh.png')

    def test_text_files_have_no_magic_requirement(self):
        self.assertEqual(validate_upload(up('ghi-chu.txt', b'noi dung tu do')), 'ghi-chu.txt')
        self.assertEqual(validate_upload(up('data.csv', b'a,b,c\n1,2,3')), 'data.csv')


class RejectsExecutablesTests(SimpleTestCase):
    def test_rejects_executable_extension(self):
        for name in ('virus.exe', 'run.bat', 'a.cmd', 'x.ps1', 'y.vbs',
                     'z.js', 'w.hta', 'q.jar', 'r.lnk', 'p.msi', 's.scr'):
            with self.subTest(name=name):
                with self.assertRaises(UploadRejected):
                    validate_upload(up(name, b'anything'))

    def test_rejects_double_extension(self):
        """bao-cao.pdf.exe — Windows chỉ xét đuôi cuối, người dùng chỉ thấy phần đầu."""
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('bao-cao.pdf.exe', PDF))
        self.assertIn('.exe', ' '.join(ctx.exception.messages))

    def test_rejects_exe_renamed_to_pdf(self):
        """Đổi tên .exe thành .pdf vẫn bị chặn nhờ magic bytes."""
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('bao-cao.pdf', EXE))
        self.assertIn('thực thi Windows', ' '.join(ctx.exception.messages))

    def test_rejects_elf_renamed_to_image(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('anh.png', ELF))

    def test_rejects_shell_script_content(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('ghi-chu.txt', b'#!/bin/bash\nrm -rf /'))

    def test_rejects_php_content(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('note.txt', b'<?php system($_GET["c"]); ?>'))


class RejectsSvgAndHtmlTests(SimpleTestCase):
    """SVG/HTML chạy được JavaScript — nguồn stored XSS."""

    def test_rejects_svg(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with self.assertRaises(UploadRejected):
            validate_upload(up('logo.svg', svg))

    def test_rejects_html(self):
        for name in ('trang.html', 'trang.htm', 'a.xhtml', 'b.shtml'):
            with self.subTest(name=name):
                with self.assertRaises(UploadRejected):
                    validate_upload(up(name, b'<html></html>'))

    def test_svg_not_in_allowed_list(self):
        self.assertNotIn('.svg', allowed_extensions())
        self.assertNotIn('.svg', allowed_extensions((GROUP_IMAGE,)))

    def test_rejects_macro_office(self):
        for name in ('a.docm', 'b.xlsm', 'c.pptm', 'd.xlsb', 'e.xlam'):
            with self.subTest(name=name):
                with self.assertRaises(UploadRejected):
                    validate_upload(up(name, ZIP))


class ConfigConsistencyTests(SimpleTestCase):
    """Bất biến cấu hình — bắt lỗi khi ai đó thêm đuôi vào sai chỗ."""

    def test_no_extension_both_allowed_and_dangerous(self):
        from nas_storage.upload_guard import DANGEROUS_EXTS, EXT_GROUPS

        overlap = sorted(set(EXT_GROUPS) & DANGEROUS_EXTS)
        self.assertEqual(overlap, [], f'Đuôi vừa cho phép vừa nguy hiểm: {overlap}')

    def test_every_allowed_extension_has_a_known_group(self):
        from nas_storage.upload_guard import ALL_GROUPS, EXT_GROUPS

        bad = sorted(e for e, g in EXT_GROUPS.items() if g not in ALL_GROUPS)
        self.assertEqual(bad, [])

    def test_magic_table_only_covers_allowed_extensions(self):
        from nas_storage.upload_guard import EXT_GROUPS, MAGIC_SIGNATURES

        orphan = sorted(set(MAGIC_SIGNATURES) - set(EXT_GROUPS))
        self.assertEqual(orphan, [], f'Chữ ký cho đuôi không còn cho phép: {orphan}')


class MagicMismatchTests(SimpleTestCase):
    def test_rejects_extension_content_mismatch(self):
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('anh.png', PDF))
        self.assertIn('không khớp phần mở rộng', ' '.join(ctx.exception.messages))

    def test_ignores_client_content_type(self):
        """content_type do trình duyệt khai — không được dùng để quyết định."""
        with self.assertRaises(UploadRejected):
            validate_upload(up('x.png', EXE, content_type='image/png'))

    def test_seek_position_restored_after_check(self):
        """Đọc magic bytes rồi phải trả con trỏ về 0, không thì lưu file mất đầu."""
        f = up('anh.png', PNG)
        validate_upload(f)
        self.assertEqual(f.tell(), 0)
        self.assertEqual(f.read(4), b'\x89PNG')


class FilenameTricksTests(SimpleTestCase):
    def test_rejects_rtl_override(self):
        """U+202E đảo chiều hiển thị để che đuôi thật."""
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('anh\u202egpj.exe', PNG))
        self.assertIn('đảo chiều', ' '.join(ctx.exception.messages))

    def test_rejects_control_characters(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('anh\x00.png', PNG))

    def test_rejects_no_extension(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('khongcoduoi', PNG))

    def test_rejects_overly_long_name(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('a' * 250 + '.png', PNG))

    def test_rejects_empty_name(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('   ', PNG))


class SizeLimitTests(SimpleTestCase):
    @override_settings(UPLOAD_MAX_BYTES_IMAGE=1024)
    def test_rejects_oversize_image(self):
        big = PNG + b'0' * 2048
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('anh.png', big))
        self.assertIn('vượt giới hạn', ' '.join(ctx.exception.messages))

    @override_settings(UPLOAD_MAX_BYTES_IMAGE=1024 * 1024)
    def test_accepts_within_limit(self):
        self.assertEqual(validate_upload(up('anh.png', PNG)), 'anh.png')

    def test_rejects_empty_file(self):
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('anh.png', b''))
        self.assertIn('rỗng', ' '.join(ctx.exception.messages))

    def test_explicit_max_bytes_wins(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('anh.png', PNG), max_bytes=8)

    @override_settings(UPLOAD_MAX_BYTES_DOC='sai')
    def test_bad_setting_falls_back_to_default(self):
        self.assertEqual(validate_upload(up('a.pdf', PDF)), 'a.pdf')


class GroupRestrictionTests(SimpleTestCase):
    def test_image_only_field_rejects_pdf(self):
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(up('bao-cao.pdf', PDF), groups=(GROUP_IMAGE,))
        self.assertIn('chỉ nhận', ' '.join(ctx.exception.messages))

    def test_image_only_field_accepts_image(self):
        self.assertEqual(
            validate_upload(up('anh.jpg', JPEG), groups=(GROUP_IMAGE,)), 'anh.jpg',
        )

    def test_doc_group_rejects_video(self):
        with self.assertRaises(UploadRejected):
            validate_upload(up('v.mp4', MP4), groups=(GROUP_DOC,))

    def test_allowed_extensions_by_group(self):
        self.assertIn('.jpg', allowed_extensions((GROUP_IMAGE,)))
        self.assertNotIn('.pdf', allowed_extensions((GROUP_IMAGE,)))
        self.assertIn('.zip', allowed_extensions((GROUP_ARCHIVE,)))
        self.assertIn('.mp4', allowed_extensions((GROUP_VIDEO,)))


class ValidateUploadsListTests(SimpleTestCase):
    def test_accepts_all_valid(self):
        validate_uploads([up('a.png', PNG), up('b.pdf', PDF)])

    def test_raises_on_first_bad_file(self):
        with self.assertRaises(UploadRejected):
            validate_uploads([up('ok.png', PNG), up('bad.exe', EXE)])

    def test_skips_none_and_empty_list(self):
        validate_uploads(None)
        validate_uploads([])
        validate_uploads([None, up('a.png', PNG)])
