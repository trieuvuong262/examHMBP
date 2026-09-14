"""Quét virus file upload bằng ClamAV (giao thức INSTREAM qua TCP).

VÌ SAO TỰ VIẾT CLIENT
---------------------
Giao thức INSTREAM của clamd rất đơn giản (gửi ``zINSTREAM\\0``, rồi từng khối
kèm độ dài 4 byte big-endian, kết thúc bằng độ dài 0). Tự viết ~80 dòng thì
không phải thêm dependency mới vào requirements, và kiểm soát được timeout —
điều quan trọng vì mọi thứ trong luồng này nằm trong request web.

THIẾT KẾ
--------
* Quét **đồng bộ trong request**, sau khi các phép kiểm tra rẻ (whitelist, magic
  bytes) đã qua — không tốn công quét file vốn đã bị từ chối.
* Có giới hạn dung lượng quét ``AV_SCAN_MAX_BYTES``. File lớn hơn không quét
  được (clamd cũng có ``StreamMaxLength`` riêng); hành vi khi đó do
  ``AV_FAIL_CLOSED`` quyết định.
* ``AV_FAIL_CLOSED``:
  - ``True``  → không quét được thì TỪ CHỐI (an toàn hơn, nhưng ClamAV chết là
    không ai upload được).
  - ``False`` → không quét được thì cho qua và ghi log cảnh báo (mặc định, giữ
    portal chạy được; vẫn còn lớp whitelist + magic bytes + AV trên NAS).
"""

from __future__ import annotations

import logging
import socket
import struct

from django.conf import settings

logger = logging.getLogger(__name__)

_CHUNK = 64 * 1024
_END = struct.pack('!I', 0)

RESULT_CLEAN = 'clean'
RESULT_INFECTED = 'infected'
RESULT_SKIPPED = 'skipped'
RESULT_ERROR = 'error'


class ScanResult:
    __slots__ = ('status', 'signature', 'detail')

    def __init__(self, status: str, *, signature: str = '', detail: str = ''):
        self.status = status
        self.signature = signature
        self.detail = detail

    @property
    def is_clean(self) -> bool:
        return self.status == RESULT_CLEAN

    @property
    def is_infected(self) -> bool:
        return self.status == RESULT_INFECTED

    @property
    def scanned(self) -> bool:
        return self.status in (RESULT_CLEAN, RESULT_INFECTED)

    def __repr__(self) -> str:  # pragma: no cover - chỉ để debug
        return f'ScanResult({self.status!r}, signature={self.signature!r})'


def av_enabled() -> bool:
    """Có quét hay không — công tắc trong DB, .env là giá trị dự phòng.

    Import muộn vì ``audit`` đã import ``nas_storage`` (nas_monitor), import ở
    đầu module sẽ thành vòng tròn.
    """
    from audit.file_scan_config import scan_enabled

    return scan_enabled()


def av_fail_closed() -> bool:
    from audit.file_scan_config import scan_fail_closed

    return scan_fail_closed()


def _host_port() -> tuple[str, int]:
    host = (getattr(settings, 'AV_CLAMD_HOST', '') or 'clamav').strip()
    try:
        port = int(getattr(settings, 'AV_CLAMD_PORT', 3310) or 3310)
    except (TypeError, ValueError):
        port = 3310
    return host, port


def _timeout() -> float:
    try:
        value = float(getattr(settings, 'AV_SCAN_TIMEOUT', 30) or 30)
    except (TypeError, ValueError):
        value = 30.0
    return max(1.0, min(120.0, value))


def _max_bytes() -> int:
    try:
        value = int(getattr(settings, 'AV_SCAN_MAX_BYTES', 50 * 1024 * 1024) or 0)
    except (TypeError, ValueError):
        value = 50 * 1024 * 1024
    return value if value > 0 else 50 * 1024 * 1024


def _read_until_nul(sock: socket.socket) -> bytes:
    buf = bytearray()
    while b'\0' not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > 8192:  # phản hồi clamd rất ngắn; dài hơn là bất thường
            break
    return bytes(buf).split(b'\0', 1)[0]


def ping() -> bool:
    """clamd còn sống không — dùng cho health check / management command."""
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=_timeout()) as sock:
            sock.settimeout(_timeout())
            sock.sendall(b'zPING\0')
            return _read_until_nul(sock).strip() == b'PONG'
    except OSError:
        return False


def version() -> str:
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=_timeout()) as sock:
            sock.settimeout(_timeout())
            sock.sendall(b'zVERSION\0')
            return _read_until_nul(sock).decode('utf-8', 'replace').strip()
    except OSError as exc:
        return f'(không kết nối được: {exc})'


def _parse_response(raw: bytes) -> ScanResult:
    text = raw.decode('utf-8', 'replace').strip()
    if not text:
        return ScanResult(RESULT_ERROR, detail='clamd không phản hồi')
    if text.endswith('ERROR'):
        return ScanResult(RESULT_ERROR, detail=text)
    if text.endswith('FOUND'):
        # 'stream: Eicar-Test-Signature FOUND'
        body = text.rsplit(' FOUND', 1)[0]
        signature = body.split(':', 1)[-1].strip() if ':' in body else body.strip()
        return ScanResult(RESULT_INFECTED, signature=signature or 'unknown', detail=text)
    if text.endswith('OK'):
        return ScanResult(RESULT_CLEAN, detail=text)
    return ScanResult(RESULT_ERROR, detail=text)


def scan_stream(fileobj, *, size: int | None = None) -> ScanResult:
    """Quét một file-like object. Luôn trả con trỏ về 0 sau khi quét."""
    if not av_enabled():
        return ScanResult(RESULT_SKIPPED, detail='AV_SCAN_ENABLED=0')

    limit = _max_bytes()
    if size is not None and size > limit:
        return ScanResult(
            RESULT_SKIPPED,
            detail=f'file {size} byte vượt giới hạn quét {limit} byte',
        )

    host, port = _host_port()
    try:
        if hasattr(fileobj, 'seek'):
            fileobj.seek(0)
    except (OSError, ValueError):
        pass

    try:
        with socket.create_connection((host, port), timeout=_timeout()) as sock:
            sock.settimeout(_timeout())
            sock.sendall(b'zINSTREAM\0')
            sent = 0
            while True:
                chunk = fileobj.read(_CHUNK)
                if not chunk:
                    break
                sent += len(chunk)
                if sent > limit:
                    sock.sendall(_END)
                    return ScanResult(
                        RESULT_SKIPPED,
                        detail=f'vượt giới hạn quét {limit} byte',
                    )
                sock.sendall(struct.pack('!I', len(chunk)) + chunk)
            sock.sendall(_END)
            return _parse_response(_read_until_nul(sock))
    except socket.timeout:
        logger.warning('Quét virus quá %.0fs — bỏ qua', _timeout())
        return ScanResult(RESULT_ERROR, detail='hết thời gian chờ clamd')
    except OSError as exc:
        logger.warning('Không kết nối được clamd %s:%s — %s', host, port, exc)
        return ScanResult(RESULT_ERROR, detail=f'không kết nối được clamd: {exc}')
    finally:
        try:
            if hasattr(fileobj, 'seek'):
                fileobj.seek(0)
        except (OSError, ValueError):
            pass


def scan_upload(uploaded) -> ScanResult:
    """Quét một ``UploadedFile`` của Django."""
    return scan_stream(uploaded, size=getattr(uploaded, 'size', None))
