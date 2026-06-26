"""Upload/tải file lên NAS qua DSM File Station — fallback khi SMB/rclone lỗi."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class DsmUploadError(OSError):
    pass


def _dsm_upload_session() -> tuple[str, str, str]:
    from audit.services.nas_monitor import _dsm_base_url, _dsm_credentials, _dsm_verify_ssl

    account, password = _dsm_credentials()
    if not account or not password:
        raise DsmUploadError('Chưa cấu hình DSM (NAS_DSM_URL / .nas-cred).')
    base = _dsm_base_url()
    verify = _dsm_verify_ssl()
    login_params = {
        'api': 'SYNO.API.Auth',
        'version': '7',
        'method': 'login',
        'account': account,
        'passwd': password,
        'session': 'FileStation',
        'format': 'sid',
        'enable_syno_token': 'yes',
    }
    for version in ('7', '6'):
        login_params['version'] = version
        try:
            resp = requests.post(
                f'{base}/webapi/auth.cgi',
                data=login_params,
                timeout=30,
                verify=verify,
            )
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise DsmUploadError(f'Không kết nối DSM: {exc}') from exc
        if payload.get('success'):
            data = payload.get('data') or {}
            sid = data.get('sid') or ''
            token = data.get('synotoken') or ''
            if sid:
                return base, sid, token
        code = (payload.get('error') or {}).get('code')
        if version == '6':
            raise DsmUploadError(f'Đăng nhập DSM thất bại (mã {code}).')
    raise DsmUploadError('Đăng nhập DSM thất bại.')


def dsm_folder_path_for_rel(full_rel: str) -> str:
    """Đường dẫn thư mục đích trên NAS: /99_LUU_TRU/.../inline"""
    rel = (full_rel or '').strip().strip('/').replace('\\', '/')
    if not rel:
        raise DsmUploadError('Đường dẫn NAS trống.')
    if '/' not in rel:
        return f'/{rel}'
    parent = rel.rsplit('/', 1)[0]
    return f'/{parent}'


def _dsm_post_upload(
    *,
    base_url: str,
    sid: str,
    syno_token: str,
    folder_path: str,
    filename: str,
    local_path: Path,
) -> dict:
    from audit.services.nas_monitor import _dsm_verify_ssl

    verify = _dsm_verify_ssl()
    query = {'_sid': sid}
    form = {
        'api': 'SYNO.FileStation.Upload',
        'version': '2',
        'method': 'upload',
        'path': folder_path,
        'create_parents': 'true',
        'overwrite': 'true',
    }
    headers = {'X-SYNO-TOKEN': syno_token} if syno_token else {}
    with local_path.open('rb') as handle:
        resp = requests.post(
            f'{base_url}/webapi/entry.cgi',
            params=query,
            data=form,
            files={'file': (filename, handle)},
            headers=headers,
            timeout=180,
            verify=verify,
        )
    return resp.json()


def dsm_upload_nas_rel(local_path: Path, full_rel: str) -> None:
    """
    Ghi file lên NAS qua DSM API.
    full_rel: đường dẫn đầy đủ từ tên share, vd. 99_LUU_TRU/1.2026/BAO_CAO_NGAY/.../a.png
    """
    local_path = Path(local_path)
    if not local_path.is_file():
        raise DsmUploadError(f'File tạm không tồn tại: {local_path}')

    rel = (full_rel or '').strip().strip('/').replace('\\', '/')
    if not rel:
        raise DsmUploadError('Đường dẫn NAS trống.')

    folder_path = dsm_folder_path_for_rel(rel)
    filename = rel.rsplit('/', 1)[-1]
    base_url, sid, syno_token = _dsm_upload_session()
    try:
        payload = _dsm_post_upload(
            base_url=base_url,
            sid=sid,
            syno_token=syno_token,
            folder_path=folder_path,
            filename=filename,
            local_path=local_path,
        )
    except (requests.RequestException, ValueError) as exc:
        raise DsmUploadError(f'Upload DSM lỗi: {exc}') from exc

    if not payload.get('success'):
        code = (payload.get('error') or {}).get('code')
        if code in (105, 106, 107, 119):
            base_url, sid, syno_token = _dsm_upload_session()
            payload = _dsm_post_upload(
                base_url=base_url,
                sid=sid,
                syno_token=syno_token,
                folder_path=folder_path,
                filename=filename,
                local_path=local_path,
            )
    if not payload.get('success'):
        code = (payload.get('error') or {}).get('code')
        raise DsmUploadError(f'Upload DSM thất bại (mã {code}).')
    logger.info('DSM upload OK: %s/%s', folder_path, filename)


def dsm_download_nas_rel(full_rel: str, dest_path: Path) -> Path:
    """Tải file từ NAS qua DSM vào dest_path (cache local)."""
    from audit.services.nas_monitor import _dsm_verify_ssl

    rel = (full_rel or '').strip().strip('/').replace('\\', '/')
    if not rel:
        raise DsmUploadError('Đường dẫn NAS trống.')
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    base_url, sid, syno_token = _dsm_upload_session()
    verify = _dsm_verify_ssl()
    params = {
        'api': 'SYNO.FileStation.Download',
        'version': '2',
        'method': 'download',
        '_sid': sid,
        'path': json.dumps([f'/{rel}']),
        'mode': 'download',
    }
    headers = {'X-SYNO-TOKEN': syno_token} if syno_token else {}
    try:
        resp = requests.get(
            f'{base_url}/webapi/entry.cgi',
            params=params,
            headers=headers,
            timeout=120,
            verify=verify,
            stream=True,
        )
        resp.raise_for_status()
        with dest_path.open('wb') as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)
    except (requests.RequestException, OSError) as exc:
        raise DsmUploadError(f'Tải DSM lỗi: {exc}') from exc

    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise DsmUploadError('Tải DSM không có dữ liệu.')
    return dest_path
