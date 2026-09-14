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
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Request đang validate upload — views gắn vào để log biết ai gửi file bị chặn.
_upload_request: ContextVar[object | None] = ContextVar('upload_request', default=None)


@contextmanager
def upload_audit(request=None):
    """Gắn request vào luồng validate — log biết user/IP/path khi từ chối file."""
    token = _upload_request.set(request)
    try:
        yield
    finally:
        _upload_request.reset(token)


def _current_request():
    return _upload_request.get()


def _actor_from_request(request) -> tuple[str, str]:
    """Trả (username, label hiển thị)."""
    if request is None:
        return '', 'anonymous'
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return '', 'anonymous'
    username = getattr(user, 'username', '') or ''
    full = (getattr(user, 'get_full_name', lambda: '')() or '').strip()
    label = f'{username} ({full})' if full and full != username else (username or 'anonymous')
    return username, label


def _client_ip(request) -> str:
    if request is None:
        return ''
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    return forwarded or (request.META.get('REMOTE_ADDR') or '')


def _file_meta(uploaded) -> dict:
    if uploaded is None:
        return {}
    meta = {
        'filename': getattr(uploaded, 'name', '') or '',
        'size': getattr(uploaded, 'size', None),
        'content_type': getattr(uploaded, 'content_type', '') or '',
    }
    return {k: v for k, v in meta.items() if v is not None and v != ''}


def _log_blocked_upload(
    message: str,
    *,
    code: str,
    name: str = '',
    uploaded=None,
    signature: str = '',
    detail: str = '',
) -> None:
    """Ghi log server + nhật ký thao tác (khi có request) cho mọi lần chặn upload."""
    request = _current_request()
    username, actor = _actor_from_request(request)
    ip = _client_ip(request)
    path = getattr(request, 'path', '') if request is not None else ''
    meta = _file_meta(uploaded)
    filename = name or meta.get('filename') or '(không tên)'
    size = meta.get('size')
    content_type = meta.get('content_type') or ''

    logger.warning(
        'UPLOAD_BLOCKED code=%s user=%s ip=%s path=%s file=%s size=%s content_type=%s '
        'signature=%s detail=%s msg=%s',
        code,
        username or actor,
        ip or '-',
        path or '-',
        filename,
        size if size is not None else '-',
        content_type or '-',
        signature or '-',
        detail or '-',
        message,
    )

    if request is None:
        return
    try:
        from audit.models import UserActivityLog
        from audit.utils import create_activity_log

        summary = f'Từ chối upload «{filename}» [{code}] — {actor}'
        if signature:
            summary = f'{summary} · {signature}'
        create_activity_log(
            request=request,
            action=UserActivityLog.ACTION_OTHER,
            summary=summary[:500],
            object_type='upload_rejected',
            object_repr=filename[:255],
            extra={
                'upload_block': {
                    'code': code,
                    'filename': filename,
                    'size': size,
                    'content_type': content_type,
                    'signature': signature,
                    'detail': detail,
                    'message': message,
                },
            },
        )
    except Exception:  # noqa: BLE001 — không để ghi log làm gãy luồng upload
        logger.debug('Không ghi được UserActivityLog cho upload bị chặn', exc_info=True)


def _reject(
    message: str,
    *,
    code: str,
    name: str = '',
    uploaded=None,
    signature: str = '',
    detail: str = '',
) -> None:
    """Log rồi raise UploadRejected — mọi chỗ chặn đi qua đây."""
    _log_blocked_upload(
        message,
        code=code,
        name=name,
        uploaded=uploaded,
        signature=signature,
        detail=detail,
    )
    raise UploadRejected(message)

MB = 1024 * 1024

GROUP_IMAGE = 'image'
GROUP_DOC = 'doc'
GROUP_ARCHIVE = 'archive'
GROUP_VIDEO = 'video'
GROUP_DESIGN = 'design'

ALL_GROUPS = (GROUP_IMAGE, GROUP_DOC, GROUP_ARCHIVE, GROUP_VIDEO, GROUP_DESIGN)

# Phần mở rộng cho phép theo nhóm. Nguồn: quét toàn bộ FileField/ImageField
# trong DB (2.616 file) — jpg/jpeg/png chiếm 95%, còn lại pdf, xlsx, docx, ods,
# doc, xls, zip, mp4, mkv. Các đuôi raster khác thêm sẵn vì vô hại.
# Nhóm design: PSD/AI/EPS… dùng cho thiết kế sản phẩm / hồ sơ SX.
EXT_GROUPS: dict[str, str] = {
    # Ảnh — CỐ Ý không có .svg
    '.jpg': GROUP_IMAGE, '.jpeg': GROUP_IMAGE, '.png': GROUP_IMAGE,
    '.gif': GROUP_IMAGE, '.webp': GROUP_IMAGE, '.bmp': GROUP_IMAGE,
    '.heic': GROUP_IMAGE, '.heif': GROUP_IMAGE,
    '.tif': GROUP_IMAGE, '.tiff': GROUP_IMAGE,
    # Tài liệu
    '.pdf': GROUP_DOC,
    '.doc': GROUP_DOC, '.docx': GROUP_DOC,
    '.xls': GROUP_DOC, '.xlsx': GROUP_DOC,  # .xlsm có macro → xem DANGEROUS_EXTS
    '.ppt': GROUP_DOC, '.pptx': GROUP_DOC,
    '.odt': GROUP_DOC, '.ods': GROUP_DOC, '.odp': GROUP_DOC,
    '.csv': GROUP_DOC, '.txt': GROUP_DOC,
    # Thiết kế (Adobe / Corel / Affinity / Sketch…)
    '.psd': GROUP_DESIGN, '.psb': GROUP_DESIGN,
    '.ai': GROUP_DESIGN, '.eps': GROUP_DESIGN,
    '.indd': GROUP_DESIGN, '.idml': GROUP_DESIGN,
    '.cdr': GROUP_DESIGN,
    '.sketch': GROUP_DESIGN, '.xd': GROUP_DESIGN,
    '.fig': GROUP_DESIGN,
    '.afdesign': GROUP_DESIGN, '.afphoto': GROUP_DESIGN, '.afpub': GROUP_DESIGN,
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
    GROUP_DESIGN: 100 * MB,
}

_SETTING_BY_GROUP = {
    GROUP_IMAGE: 'UPLOAD_MAX_BYTES_IMAGE',
    GROUP_DOC: 'UPLOAD_MAX_BYTES_DOC',
    GROUP_ARCHIVE: 'UPLOAD_MAX_BYTES_ARCHIVE',
    GROUP_VIDEO: 'UPLOAD_MAX_BYTES_VIDEO',
    GROUP_DESIGN: 'UPLOAD_MAX_BYTES_DESIGN',
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
    '.tif': [(0, b'II*\x00'), (0, b'MM\x00*')],
    '.tiff': [(0, b'II*\x00'), (0, b'MM\x00*')],
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
    # Thiết kế
    '.psd': [(0, b'8BPS')],
    '.psb': [(0, b'8BPS')],
    # AI hiện đại thường là PDF; bản cũ/EPS là PostScript; một số bản lưu CFB.
    '.ai': [(0, b'%PDF'), (0, b'%!PS'), (0, b'%!'), *_OLE_SIGS],
    '.eps': [(0, b'%!PS'), (0, b'%!'), (0, b'\xc5\xd0\xd3\xc6')],
    '.idml': _ZIP_SIGS,
    '.sketch': _ZIP_SIGS,
    '.xd': _ZIP_SIGS,
    '.fig': _ZIP_SIGS,  # Figma export thường là zip
    '.afdesign': _ZIP_SIGS,
    '.afphoto': _ZIP_SIGS,
    '.afpub': _ZIP_SIGS,
    # CorelDRAW X4+ thường RIFF…CDR / ZIP; bản cũ không bắt buộc magic.
    '.cdr': [(0, b'RIFF'), *_ZIP_SIGS],
    # .indd / .csv / .txt — không có chữ ký ổn định → chỉ chặn magic nguy hiểm.
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
    """Ưu tiên giới hạn trong DB (tab Quét virus), không thì .env / mặc định mã."""
    try:
        from audit.file_scan_config import configured_max_bytes

        configured = configured_max_bytes(group)
        if configured is not None and configured > 0:
            return configured
    except Exception:  # noqa: BLE001 — không để cấu hình làm gãy upload
        logger.debug('Không đọc được giới hạn upload từ DB', exc_info=True)

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
    """Đuôi được phép — giao của nhóm yêu cầu và danh sách cấu hình (DB hoặc mặc định mã)."""
    groups = tuple(groups) if groups else ALL_GROUPS
    try:
        from audit.file_scan_config import configured_allowed_extensions

        configured = set(configured_allowed_extensions())
    except Exception:  # noqa: BLE001 — DB/migrate chưa sẵn thì dùng mã nguồn
        logger.debug('Không đọc được allowed_extensions từ DB', exc_info=True)
        configured = None

    out: list[str] = []
    for ext, grp in EXT_GROUPS.items():
        if grp not in groups:
            continue
        if configured is not None and ext not in configured:
            continue
        out.append(ext)
    return sorted(out)


def _clean_name(uploaded) -> str:
    raw = getattr(uploaded, 'name', '') or ''
    # Chỉ giữ phần tên, bỏ mọi thành phần đường dẫn (chống ../ và C:\)
    name = raw.replace('\\', '/').split('/')[-1].strip()
    if not name:
        _reject('Tên file trống.', code='empty_name', uploaded=uploaded)
    if any(ch in _BIDI_CONTROLS for ch in name):
        _reject(
            'Tên file chứa ký tự đảo chiều hiển thị — không được phép. '
            'Hãy đổi tên file rồi gửi lại.',
            code='bidi_name',
            name=name,
            uploaded=uploaded,
        )
    if any(unicodedata.category(ch) == 'Cc' for ch in name):
        _reject(
            'Tên file chứa ký tự điều khiển — hãy đổi tên file.',
            code='control_name',
            name=name,
            uploaded=uploaded,
        )
    if len(name) > 200:
        _reject(
            'Tên file quá dài (tối đa 200 ký tự).',
            code='name_too_long',
            name=name,
            uploaded=uploaded,
        )
    return name


def _check_extension(name: str, groups, uploaded=None) -> tuple[str, str]:
    parts = name.lower().split('.')
    allowed = allowed_extensions(groups)
    if len(parts) < 2:
        _reject(
            f'File «{name}» không có phần mở rộng. '
            f'Chỉ nhận: {", ".join(allowed)}.',
            code='no_extension',
            name=name,
            uploaded=uploaded,
        )

    # Đuôi nguy hiểm nằm ở bất kỳ vị trí nào — chặn double extension
    for segment in parts[1:]:
        if f'.{segment}' in DANGEROUS_EXTS:
            _reject(
                f'File «{name}» có phần mở rộng không được phép (.{segment}).',
                code='dangerous_ext',
                name=name,
                uploaded=uploaded,
                detail=f'.{segment}',
            )

    ext = f'.{parts[-1]}'
    group = EXT_GROUPS.get(ext)
    if group is None:
        _reject(
            f'File «{name}»: định dạng {ext} không được phép. '
            f'Chỉ nhận: {", ".join(allowed)}.',
            code='ext_not_allowed',
            name=name,
            uploaded=uploaded,
            detail=ext,
        )
    if groups and group not in groups:
        _reject(
            f'File «{name}»: chỗ này chỉ nhận '
            f'{", ".join(allowed)}.',
            code='ext_group_denied',
            name=name,
            uploaded=uploaded,
            detail=ext,
        )
    if ext not in allowed:
        # Có trong mã nhưng bị cắt bởi danh sách tuỳ chỉnh trên UI.
        _reject(
            f'File «{name}»: định dạng {ext} không được phép. '
            f'Chỉ nhận: {", ".join(allowed)}.',
            code='ext_not_allowed',
            name=name,
            uploaded=uploaded,
            detail=ext,
        )
    return ext, group


def _check_size(uploaded, name: str, group: str, max_bytes: int | None) -> None:
    size = getattr(uploaded, 'size', None)
    if size is None:
        return
    limit = max_bytes if max_bytes else _max_bytes_for(group)
    if size > limit:
        _reject(
            f'File «{name}» nặng {_mb(size)}MB, vượt giới hạn {_mb(limit)}MB.',
            code='too_large',
            name=name,
            uploaded=uploaded,
            detail=f'size={size} limit={limit}',
        )
    if size == 0:
        _reject(
            f'File «{name}» rỗng (0 byte).',
            code='empty_file',
            name=name,
            uploaded=uploaded,
        )


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
            _reject(
                f'File «{name}» thực chất là {label} — bị từ chối '
                f'dù phần mở rộng là {ext}.',
                code='dangerous_magic',
                name=name,
                uploaded=uploaded,
                detail=label,
            )

    expected = MAGIC_SIGNATURES.get(ext)
    if not expected:
        return
    if not any(_matches(head, off, sig) for off, sig in expected):
        _reject(
            f'Nội dung file «{name}» không khớp phần mở rộng {ext}. '
            'File có thể bị đổi tên hoặc đã hỏng.',
            code='magic_mismatch',
            name=name,
            uploaded=uploaded,
            detail=ext,
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
        _reject(
            f'File «{name}» chứa mã độc ({result.signature}) — đã bị từ chối. '
            'Hãy quét virus máy của bạn rồi gửi lại.',
            code='malware',
            name=name,
            uploaded=uploaded,
            signature=result.signature or '',
            detail=result.detail or '',
        )
    if result.is_clean:
        return

    # Không quét được (clamd chết, quá lớn, timeout).
    request = _current_request()
    username, actor = _actor_from_request(request)
    logger.warning(
        'UPLOAD_SCAN_SKIPPED user=%s ip=%s file=%s detail=%s',
        username or actor,
        _client_ip(request) or '-',
        name,
        result.detail,
    )
    if av_fail_closed():
        _reject(
            f'Chưa quét được virus cho «{name}» nên tạm thời không nhận file. '
            'Vui lòng thử lại sau hoặc liên hệ IT.',
            code='scan_unavailable',
            name=name,
            uploaded=uploaded,
            detail=result.detail or '',
        )


def validate_upload(
    uploaded,
    *,
    groups=None,
    max_bytes: int | None = None,
    scan: bool = True,
    request=None,
) -> str:
    """Kiểm tra một file upload. Raise ``UploadRejected`` nếu không hợp lệ.

    ``groups``: giới hạn nhóm cho phép, vd. ``(GROUP_IMAGE,)`` cho ô chỉ nhận ảnh.
    ``scan``: có quét virus không (đặt False khi đã quét ở nơi khác).
    ``request``: gắn vào audit context nếu chưa có (để log user/IP).
    Trả về tên file đã chuẩn hoá.
    """
    def _run() -> str:
        if uploaded is None:
            _reject('Không có file.', code='no_file')
        groups_t = tuple(groups) if groups else None
        name = _clean_name(uploaded)
        ext, group = _check_extension(name, groups_t, uploaded=uploaded)
        _check_size(uploaded, name, group, max_bytes)
        _check_magic(uploaded, name, ext)
        if scan:
            scan_for_malware(uploaded, name)
        return name

    if request is not None and _current_request() is None:
        with upload_audit(request):
            return _run()
    return _run()


def validate_uploads(files, *, groups=None, max_bytes: int | None = None, request=None) -> None:
    """Kiểm tra danh sách file — có bất kỳ file lỗi nào thì raise (chế độ nghiêm).

    Dùng ``partition_uploads`` khi muốn nhận phần hợp lệ và chỉ báo file bị chặn.
    """
    _accepted, rejected = partition_uploads(
        files, groups=groups, max_bytes=max_bytes, request=request,
    )
    if rejected:
        raise UploadRejected(rejected)


def partition_uploads(
    files,
    *,
    groups=None,
    max_bytes: int | None = None,
    request=None,
) -> tuple[list, list[str]]:
    """Lọc danh sách upload: trả (file_hợp_lệ, danh_sách_lý_do_từ_chối).

    File lỗi bị loại + ghi log; file còn lại vẫn nhận. Dùng khi gửi báo cáo /
    nhận xét: nội dung chữ và file chuẩn vẫn lưu, popup báo các file bị chặn.
    """
    def _run() -> tuple[list, list[str]]:
        items = [f for f in (files or []) if f]
        candidates: list[tuple[object, str]] = []
        rejected: list[str] = []
        for uploaded in items:
            try:
                name = validate_upload(
                    uploaded, groups=groups, max_bytes=max_bytes, scan=False,
                )
                candidates.append((uploaded, name))
            except UploadRejected as exc:
                rejected.extend(exc.messages)
        accepted: list = []
        for uploaded, name in candidates:
            try:
                scan_for_malware(uploaded, name)
            except UploadRejected as exc:
                rejected.extend(exc.messages)
                continue
            accepted.append(uploaded)
        return accepted, rejected

    if request is not None and _current_request() is None:
        with upload_audit(request):
            return _run()
    return _run()


def format_rejected_upload_notice(rejected: list[str], *, saved_ok: bool = True) -> str:
    """Ghép thông báo popup khi một phần file bị chặn."""
    if not rejected:
        return ''
    detail = '; '.join(rejected)
    if saved_ok:
        return (
            f'Không nhận {len(rejected)} file: {detail}. '
            'Nội dung báo cáo / nhận xét và các file hợp lệ đã được lưu.'
        )
    return f'Không nhận {len(rejected)} file: {detail}.'
