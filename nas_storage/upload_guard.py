"""Kiểm soát file người dùng upload trước khi ghi lên NAS / VPS.

VÌ SAO CẦN
----------
File đính kèm đi thẳng từ trình duyệt lên share NAS dùng chung, nơi nhân viên
map ổ đĩa qua SMB/WebDAV. Một file độc hại lọt vào là nằm sẵn trong ổ đĩa của
mọi máy — đường lây ransomware kinh điển. Trước đây luồng báo cáo không kiểm
tra gì: phần mở rộng, dung lượng, kiểu file thật đều không xét.

NGUYÊN TẮC
----------
* **Whitelist, không blacklist.** Danh sách dựng từ dữ liệu thật đang có trong
  DB, không đoán.
* **Không tin ``content_type`` do client gửi** — nó do trình duyệt khai và sửa
  được bằng ``curl``. Xác thực bằng chữ ký nhị phân (magic bytes) ở đầu file.
* **Không nhận SVG.** SVG là XML, chạy được JavaScript; nếu bị phục vụ inline
  cùng origin thì thành stored XSS. Dữ liệu thật không có file SVG nào.
* **Chặn file thực thi kể cả khi bị đổi tên** — nhận diện qua magic bytes.
"""

from __future__ import annotations

import logging
import os
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

MB = 1024 * 1024

GROUP_IMAGE = 'image'
GROUP_DOC = 'doc'
GROUP_ARCHIVE = 'archive'
GROUP_VIDEO = 'video'

ALL_GROUPS = (GROUP_IMAGE, GROUP_DOC, GROUP_ARCHIVE, GROUP_VIDEO)

# Phần mở rộng cho phép theo nhóm. Nguồn: quét toàn bộ FileField/ImageField
# trong DB (2.616 file) — jpg/jpeg/png chiếm 95%, còn lại pdf, xlsx, docx, ods,
# doc, xls, zip, mp4, mkv. Các đuôi raster khác thêm sẵn vì vô hại.
EXT_GROUPS: dict[str, str] = {
    # Ảnh — CỐ Ý không có .svg
    '.jpg': GROUP_IMAGE, '.jpeg': GROUP_IMAGE, '.png': GROUP_IMAGE,
    '.gif': GROUP_IMAGE, '.webp': GROUP_IMAGE, '.bmp': GROUP_IMAGE,
    '.heic': GROUP_IMAGE, '.heif': GROUP_IMAGE,
    # Tài liệu
    '.pdf': GROUP_DOC,
    '.doc': GROUP_DOC, '.docx': GROUP_DOC,
    '.xls': GROUP_DOC, '.xlsx': GROUP_DOC,  # .xlsm có macro → xem DANGEROUS_EXTS
    '.ppt': GROUP_DOC, '.pptx': GROUP_DOC,
    '.odt': GROUP_DOC, '.ods': GROUP_DOC, '.odp': GROUP_DOC,
    '.csv': GROUP_DOC, '.txt': GROUP_DOC,
    # Nén
    '.zip': GROUP_ARCHIVE, '.rar': GROUP_ARCHIVE, '.7z': GROUP_ARCHIVE,
    # Video
    '.mp4': GROUP_VIDEO, '.mkv': GROUP_VIDEO, '.webm': GROUP_VIDEO,
    '.mov': GROUP_VIDEO, '.avi': GROUP_VIDEO,
}

DEFAULT_MAX_BYTES: dict[str, int] = {
    GROUP_IMAGE: 15 * MB,
    GROUP_DOC: 30 * MB,
    GROUP_ARCHIVE: 50 * MB,
    GROUP_VIDEO: 200 * MB,
}

_SETTING_BY_GROUP = {
    GROUP_IMAGE: 'UPLOAD_MAX_BYTES_IMAGE',
    GROUP_DOC: 'UPLOAD_MAX_BYTES_DOC',
    GROUP_ARCHIVE: 'UPLOAD_MAX_BYTES_ARCHIVE',
    GROUP_VIDEO: 'UPLOAD_MAX_BYTES_VIDEO',
}

# Đuôi nguy hiểm — chặn cả khi nằm ở giữa tên (bao-cao.pdf.exe) vì Windows chỉ
# xét đuôi cuối, còn người dùng chỉ nhìn thấy phần đầu.
DANGEROUS_EXTS = frozenset({
    '.exe', '.com', '.scr', '.pif', '.cpl', '.msi', '.msp', '.msc',
    '.bat', '.cmd', '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse',
    '.wsf', '.wsh', '.hta', '.jar', '.lnk', '.url', '.reg', '.inf',
    '.dll', '.ocx', '.sys', '.drv', '.efi', '.gadget',
    '.sh', '.bash', '.zsh', '.run', '.bin', '.elf', '.deb', '.rpm', '.appimage',
    '.apk', '.app', '.dmg', '.pkg',
    '.php', '.phtml', '.asp', '.aspx', '.jsp', '.cgi', '.pl', '.py', '.rb',
    '.html', '.htm', '.xhtml', '.shtml', '.svg', '.svgz', '.xml', '.xsl',
    '.iso', '.img', '.vhd', '.vhdx', '.vmdk',
    # Office có macro — vector phát tán malware phổ biến nhất qua email/file
    '.docm', '.xlsm', '.xlsb', '.pptm', '.dotm', '.xltm', '.potm', '.ppam', '.xlam',
})

# Chữ ký nhị phân. Mỗi phần tử: (offset, bytes). Một đuôi có thể có nhiều
# chữ ký hợp lệ; khớp một cái là đủ.
_ZIP_SIGS = [(0, b'PK\x03\x04'), (0, b'PK\x05\x06'), (0, b'PK\x07\x08')]
_OLE_SIGS = [(0, b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')]
_FTYP_SIGS = [(4, b'ftyp')]

MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    '.jpg': [(0, b'\xff\xd8\xff')],
    '.jpeg': [(0, b'\xff\xd8\xff')],
    # Chỉ 4 byte đầu của chữ ký PNG (đủ phân biệt, không đòi file nguyên vẹn)
    '.png': [(0, b'\x89PNG')],
    '.gif': [(0, b'GIF87a'), (0, b'GIF89a')],
    '.webp': [(0, b'RIFF')],
    '.bmp': [(0, b'BM')],
    '.heic': _FTYP_SIGS,
    '.heif': _FTYP_SIGS,
    '.pdf': [(0, b'%PDF')],
    '.docx': _ZIP_SIGS, '.xlsx': _ZIP_SIGS,
    '.pptx': _ZIP_SIGS, '.odt': _ZIP_SIGS, '.ods': _ZIP_SIGS,
    '.odp': _ZIP_SIGS, '.zip': _ZIP_SIGS,
    '.doc': _OLE_SIGS, '.xls': _OLE_SIGS, '.ppt': _OLE_SIGS,
    '.rar': [(0, b'Rar!\x1a\x07\x00'), (0, b'Rar!\x1a\x07\x01\x00')],
    '.7z': [(0, b'7z\xbc\xaf\x27\x1c')],
    '.mp4': _FTYP_SIGS, '.mov': _FTYP_SIGS,
    '.mkv': [(0, b'\x1a\x45\xdf\xa3')],
    '.webm': [(0, b'\x1a\x45\xdf\xa3')],
    '.avi': [(0, b'RIFF')],
    # .csv/.txt là văn bản thuần, không có chữ ký — chỉ dựa vào kiểm tra
    # "chữ ký nguy hiểm" bên dưới.
}

# Chữ ký của file thực thi / script — chặn bất kể đuôi là gì.
DANGEROUS_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b'MZ', 'file thực thi Windows (PE)'),
    (0, b'\x7fELF', 'file thực thi Linux (ELF)'),
    (0, b'\xca\xfe\xba\xbe', 'Java class / Mach-O'),
    (0, b'\xfe\xed\xfa\xce', 'file thực thi macOS (Mach-O)'),
    (0, b'\xfe\xed\xfa\xcf', 'file thực thi macOS (Mach-O)'),
    (0, b'#!', 'script có shebang'),
    (0, b'<?php', 'mã PHP'),
    (0, b'\x4d\x53\x43\x46', 'gói cabinet Windows (CAB)'),
]

_MAGIC_READ_BYTES = 64

# Ký tự vô hình đảo chiều hiển thị — dùng để che đuôi thật
# (vd. "anh<U+202E>gpj.exe" hiện thành "anhexe.jpg").
_BIDI_CONTROLS = frozenset('\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200f\u200e')


class UploadRejected(ValidationError):
    """File bị từ chối — hiển thị được cho người dùng."""


def _max_bytes_for(group: str) -> int:
    setting_name = _SETTING_BY_GROUP.get(group)
    default = DEFAULT_MAX_BYTES.get(group, 30 * MB)
    if not setting_name:
        return default
    try:
        value = int(getattr(settings, setting_name, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _mb(value: int) -> str:
    return f'{value / MB:.0f}'.rstrip('0').rstrip('.') or '0'


def allowed_extensions(groups=None) -> list[str]:
    groups = tuple(groups) if groups else ALL_GROUPS
    return sorted(ext for ext, grp in EXT_GROUPS.items() if grp in groups)


def _clean_name(uploaded) -> str:
    raw = getattr(uploaded, 'name', '') or ''
    # Chỉ giữ phần tên, bỏ mọi thành phần đường dẫn (chống ../ và C:\)
    name = raw.replace('\\', '/').split('/')[-1].strip()
    if not name:
        raise UploadRejected('Tên file trống.')
    if any(ch in _BIDI_CONTROLS for ch in name):
        raise UploadRejected(
            'Tên file chứa ký tự đảo chiều hiển thị — không được phép. '
            'Hãy đổi tên file rồi gửi lại.',
        )
    if any(unicodedata.category(ch) == 'Cc' for ch in name):
        raise UploadRejected('Tên file chứa ký tự điều khiển — hãy đổi tên file.')
    if len(name) > 200:
        raise UploadRejected('Tên file quá dài (tối đa 200 ký tự).')
    return name


def _check_extension(name: str, groups) -> tuple[str, str]:
    parts = name.lower().split('.')
    if len(parts) < 2:
        raise UploadRejected(
            f'File «{name}» không có phần mở rộng. '
            f'Chỉ nhận: {", ".join(allowed_extensions(groups))}.',
        )

    # Đuôi nguy hiểm nằm ở bất kỳ vị trí nào — chặn double extension
    for segment in parts[1:]:
        if f'.{segment}' in DANGEROUS_EXTS:
            raise UploadRejected(
                f'File «{name}» có phần mở rộng không được phép (.{segment}).',
            )

    ext = f'.{parts[-1]}'
    group = EXT_GROUPS.get(ext)
    if group is None:
        raise UploadRejected(
            f'File «{name}»: định dạng {ext} không được phép. '
            f'Chỉ nhận: {", ".join(allowed_extensions(groups))}.',
        )
    if groups and group not in groups:
        raise UploadRejected(
            f'File «{name}»: chỗ này chỉ nhận '
            f'{", ".join(allowed_extensions(groups))}.',
        )
    return ext, group


def _check_size(uploaded, name: str, group: str, max_bytes: int | None) -> None:
    size = getattr(uploaded, 'size', None)
    if size is None:
        return
    limit = max_bytes if max_bytes else _max_bytes_for(group)
    if size > limit:
        raise UploadRejected(
            f'File «{name}» nặng {_mb(size)}MB, vượt giới hạn {_mb(limit)}MB.',
        )
    if size == 0:
        raise UploadRejected(f'File «{name}» rỗng (0 byte).')


def _read_head(uploaded) -> bytes:
    """Đọc vài byte đầu rồi trả con trỏ về 0 để lưu file không bị mất đầu."""
    try:
        if hasattr(uploaded, 'seek'):
            uploaded.seek(0)
        head = uploaded.read(_MAGIC_READ_BYTES) or b''
    except (OSError, ValueError):
        return b''
    finally:
        try:
            if hasattr(uploaded, 'seek'):
                uploaded.seek(0)
        except (OSError, ValueError):
            pass
    return bytes(head)


def _matches(head: bytes, offset: int, signature: bytes) -> bool:
    end = offset + len(signature)
    return len(head) >= end and head[offset:end] == signature


def _check_magic(uploaded, name: str, ext: str) -> None:
    head = _read_head(uploaded)
    if not head:
        return

    for offset, signature, label in DANGEROUS_SIGNATURES:
        if _matches(head, offset, signature):
            raise UploadRejected(
                f'File «{name}» thực chất là {label} — bị từ chối '
                f'dù phần mở rộng là {ext}.',
            )

    expected = MAGIC_SIGNATURES.get(ext)
    if not expected:
        return
    if not any(_matches(head, off, sig) for off, sig in expected):
        raise UploadRejected(
            f'Nội dung file «{name}» không khớp phần mở rộng {ext}. '
            'File có thể bị đổi tên hoặc đã hỏng.',
        )


def scan_for_malware(uploaded, name: str) -> None:
    """Quét virus. Raise ``UploadRejected`` nếu nhiễm.

    Tách riêng khỏi các phép kiểm tra rẻ vì đây là lần duy nhất có I/O mạng —
    chỉ gọi khi file đã qua whitelist và magic bytes.
    """
    from nas_storage.av_scan import av_enabled, av_fail_closed, scan_upload

    if not av_enabled():
        return

    result = scan_upload(uploaded)
    if result.is_infected:
        logger.warning(
            'Từ chối file nhiễm virus: %s — %s', name, result.signature,
        )
        raise UploadRejected(
            f'File «{name}» chứa mã độc ({result.signature}) — đã bị từ chối. '
            'Hãy quét virus máy của bạn rồi gửi lại.',
        )
    if result.is_clean:
        return

    # Không quét được (clamd chết, quá lớn, timeout).
    logger.warning('Không quét được virus cho «%s»: %s', name, result.detail)
    if av_fail_closed():
        raise UploadRejected(
            f'Chưa quét được virus cho «{name}» nên tạm thời không nhận file. '
            'Vui lòng thử lại sau hoặc liên hệ IT.',
        )


def validate_upload(
    uploaded,
    *,
    groups=None,
    max_bytes: int | None = None,
    scan: bool = True,
) -> str:
    """Kiểm tra một file upload. Raise ``UploadRejected`` nếu không hợp lệ.

    ``groups``: giới hạn nhóm cho phép, vd. ``(GROUP_IMAGE,)`` cho ô chỉ nhận ảnh.
    ``scan``: có quét virus không (đặt False khi đã quét ở nơi khác).
    Trả về tên file đã chuẩn hoá.
    """
    if uploaded is None:
        raise UploadRejected('Không có file.')
    groups = tuple(groups) if groups else None
    name = _clean_name(uploaded)
    ext, group = _check_extension(name, groups)
    _check_size(uploaded, name, group, max_bytes)
    _check_magic(uploaded, name, ext)
    if scan:
        scan_for_malware(uploaded, name)
    return name


def validate_uploads(files, *, groups=None, max_bytes: int | None = None) -> None:
    """Kiểm tra danh sách file — lỗi đầu tiên là dừng.

    Chạy hai lượt: lượt 1 toàn bộ phép kiểm tra rẻ, lượt 2 mới quét virus. Nhờ
    vậy một lô có file sai định dạng bị chặn ngay, không phải chờ quét.
    """
    items = [f for f in (files or []) if f]
    names = [
        validate_upload(f, groups=groups, max_bytes=max_bytes, scan=False)
        for f in items
    ]
    for uploaded, name in zip(items, names):
        scan_for_malware(uploaded, name)
