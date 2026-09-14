"""Đọc/ghi công tắc quét virus file upload + danh sách định dạng cho phép.

Nguồn sự thật là DB (``FileScanConfig``) để IT bật/tắt ngay trên portal, không
phải sửa ``.env`` rồi deploy lại. ``.env`` giữ hai vai trò:

* ``AV_SCAN_ENABLED`` — giá trị khởi tạo lần đầu, và quyết định container
  ``clamav`` có được khởi động lúc deploy hay không (nó chiếm ~2GB RAM).
* ``AV_SCAN_FORCE_OFF`` — cầu dao khẩn cấp: bật lên là tắt quét bất kể DB nói
  gì, dùng khi scanner gây sự cố mà không vào được portal.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

_EXT_RE = re.compile(r'^\.?[a-z0-9]{1,16}$')


def force_off() -> bool:
    """Cầu dao khẩn cấp trong .env — thắng mọi cấu hình DB."""
    return bool(getattr(settings, 'AV_SCAN_FORCE_OFF', False))


def get_config():
    """Bản ghi cấu hình (memo hoá trong 1 request đọc)."""
    from audit.models import FileScanConfig
    from hrm.request_cache import get_or_set

    return get_or_set(('file_scan_config',), FileScanConfig.get_solo)


def _config_or_none():
    """Trả config, None nếu DB chưa sẵn sàng (migrate, test không có bảng)."""
    try:
        return get_config()
    except Exception:  # noqa: BLE001 - không để cấu hình làm sập luồng upload
        logger.debug('Chưa đọc được FileScanConfig — dùng giá trị .env', exc_info=True)
        return None


def scan_enabled() -> bool:
    if force_off():
        return False
    config = _config_or_none()
    if config is None:
        return bool(getattr(settings, 'AV_SCAN_ENABLED', False))
    return bool(config.enabled)


def scan_fail_closed() -> bool:
    config = _config_or_none()
    if config is None:
        return bool(getattr(settings, 'AV_FAIL_CLOSED', False))
    return bool(config.fail_closed)


_GROUP_MB_ATTR = {
    'image': 'max_mb_image',
    'doc': 'max_mb_doc',
    'archive': 'max_mb_archive',
    'design': 'max_mb_design',
    'video': 'max_mb_video',
}

_MIN_MB = 1
_MAX_MB = 2048  # trần an toàn trên UI; nginx vẫn có thể thấp hơn


def clamp_max_mb(value, *, default: int) -> int:
    try:
        mb = int(value)
    except (TypeError, ValueError):
        mb = default
    return max(_MIN_MB, min(_MAX_MB, mb))


def env_default_max_mb(group: str) -> int:
    """Giá trị mặc định từ settings (.env) — đơn vị MB."""
    from nas_storage.upload_guard import DEFAULT_MAX_BYTES, MB, _SETTING_BY_GROUP

    setting_name = _SETTING_BY_GROUP.get(group)
    default_bytes = DEFAULT_MAX_BYTES.get(group, 30 * MB)
    if setting_name:
        try:
            default_bytes = int(getattr(settings, setting_name, default_bytes) or default_bytes)
        except (TypeError, ValueError):
            pass
    return max(_MIN_MB, default_bytes // MB)


def configured_max_bytes(group: str) -> int | None:
    """Giới hạn byte đang có hiệu lực từ DB; None → caller dùng .env/mã."""
    from nas_storage.upload_guard import MB

    config = _config_or_none()
    if config is None:
        return None
    attr = _GROUP_MB_ATTR.get(group)
    if not attr:
        return None
    mb = getattr(config, attr, None)
    try:
        mb_i = int(mb)
    except (TypeError, ValueError):
        return None
    if mb_i <= 0:
        return None
    return clamp_max_mb(mb_i, default=env_default_max_mb(group)) * MB


def upload_limits_mb() -> dict[str, int]:
    """Dict MB theo nhóm — dùng hiển thị form."""
    config = _config_or_none()
    out = {g: env_default_max_mb(g) for g in _GROUP_MB_ATTR}
    if config is None:
        return out
    for group, attr in _GROUP_MB_ATTR.items():
        out[group] = clamp_max_mb(getattr(config, attr, out[group]), default=out[group])
    return out


def default_allowed_extensions() -> list[str]:
    """Danh sách mặc định trong mã (nas_storage.upload_guard.EXT_GROUPS)."""
    from nas_storage.upload_guard import EXT_GROUPS

    return sorted(EXT_GROUPS.keys())


def normalize_extension(raw: str) -> str | None:
    """Chuẩn hoá một đuôi: ``PDF`` / ``pdf`` / ``.pdf`` → ``.pdf``. None nếu không hợp lệ."""
    text = (raw or '').strip().lower()
    if not text:
        return None
    if not text.startswith('.'):
        text = f'.{text}'
    if not _EXT_RE.match(text):
        return None
    return text


def parse_extensions_input(raw: str) -> tuple[list[str], list[str]]:
    """Parse textarea (xuống dòng / dấu phẩy). Trả (hợp_lệ, bị_loại)."""
    from nas_storage.upload_guard import DANGEROUS_EXTS

    tokens: list[str] = []
    for part in re.split(r'[\s,;]+', raw or ''):
        part = part.strip()
        if part:
            tokens.append(part)

    valid: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        ext = normalize_extension(token)
        if not ext:
            rejected.append(token)
            continue
        if ext in DANGEROUS_EXTS:
            rejected.append(ext)
            continue
        if ext in seen:
            continue
        seen.add(ext)
        valid.append(ext)
    valid.sort()
    return valid, rejected


def configured_allowed_extensions() -> list[str]:
    """Danh sách đang có hiệu lực: DB nếu đã cấu hình, không thì mặc định mã."""
    config = _config_or_none()
    if config is None:
        return default_allowed_extensions()
    raw = getattr(config, 'allowed_extensions', None) or []
    if not isinstance(raw, list) or not raw:
        return default_allowed_extensions()
    cleaned, _ = parse_extensions_input('\n'.join(str(x) for x in raw))
    return cleaned or default_allowed_extensions()


def save_config(
    *,
    enabled: bool,
    fail_closed: bool,
    admin_user,
    max_mb_image: int | None = None,
    max_mb_doc: int | None = None,
    max_mb_archive: int | None = None,
    max_mb_design: int | None = None,
    max_mb_video: int | None = None,
):
    """Lưu công tắc + giới hạn dung lượng; trả bản ghi đã cập nhật."""
    from hrm.request_cache import invalidate

    config = get_config()
    config.enabled = bool(enabled)
    config.fail_closed = bool(fail_closed)
    if max_mb_image is not None:
        config.max_mb_image = clamp_max_mb(max_mb_image, default=env_default_max_mb('image'))
    if max_mb_doc is not None:
        config.max_mb_doc = clamp_max_mb(max_mb_doc, default=env_default_max_mb('doc'))
    if max_mb_archive is not None:
        config.max_mb_archive = clamp_max_mb(max_mb_archive, default=env_default_max_mb('archive'))
    if max_mb_design is not None:
        config.max_mb_design = clamp_max_mb(max_mb_design, default=env_default_max_mb('design'))
    if max_mb_video is not None:
        config.max_mb_video = clamp_max_mb(max_mb_video, default=env_default_max_mb('video'))
    config.updated_by = admin_user if getattr(admin_user, 'is_authenticated', False) else None
    config.save(update_fields=[
        'enabled', 'fail_closed',
        'max_mb_image', 'max_mb_doc', 'max_mb_archive', 'max_mb_design', 'max_mb_video',
        'updated_by', 'updated_at',
    ])
    invalidate('file_scan_config')
    return config


def save_allowed_extensions(*, extensions: list[str], admin_user, reset_default: bool = False):
    """Lưu / khôi phục danh sách đuôi được phép."""
    from hrm.request_cache import invalidate

    config = get_config()
    if reset_default:
        config.allowed_extensions = []
    else:
        cleaned, _ = parse_extensions_input('\n'.join(extensions))
        config.allowed_extensions = cleaned
    config.updated_by = admin_user if getattr(admin_user, 'is_authenticated', False) else None
    config.save(update_fields=['allowed_extensions', 'updated_by', 'updated_at'])
    invalidate('file_scan_config')
    return config


def scanner_status() -> dict:
    """Trạng thái scanner để hiển thị trên màn hình cấu hình."""
    from nas_storage.av_scan import ping, version

    alive = ping()
    return {
        'alive': alive,
        'version': version() if alive else '',
        'host': getattr(settings, 'AV_CLAMD_HOST', ''),
        'port': getattr(settings, 'AV_CLAMD_PORT', ''),
        'container_enabled': bool(getattr(settings, 'AV_SCAN_ENABLED', False)),
        'force_off': force_off(),
        'max_scan_mb': max(
            1,
            int(getattr(settings, 'AV_SCAN_MAX_BYTES', 200 * 1024 * 1024) or 0) // (1024 * 1024),
        ),
    }
