"""Đóng gói .deb Công cụ IT Ubuntu (pure Python, không cần dpkg-deb)."""

from __future__ import annotations

import hashlib
import io
import tarfile
import time
from pathlib import Path


PACKAGE_NAME = 'justplay-cong-cu-it'
PACKAGE_VERSION = '1.0.1'
ARCH = 'all'


def _normalize_tar_path(name: str) -> str:
    """Đường dẫn trong data/control.tar: ./usr/... (chuẩn Debian)."""
    n = name.replace('\\', '/').lstrip('/')
    if n in ('', '.'):
        return '.'
    if not n.startswith('./'):
        n = './' + n
    return n.rstrip('/') if n != '.' else '.'


def _parent_dirs(path: str) -> list[str]:
    """./usr/local/bin/file → ['./usr', './usr/local', './usr/local/bin']."""
    path = _normalize_tar_path(path)
    if path == '.':
        return []
    parts = path.split('/')
    # ['.', 'usr', 'local', 'bin', 'file'] → dirs tới trước tên file
    out: list[str] = []
    acc = '.'
    for part in parts[1:-1]:
        acc = f'./{part}' if acc == '.' else f'{acc}/{part}'
        out.append(acc)
    return out


def _tar_gz_bytes(files: dict[str, bytes], *, include_root: bool = True) -> bytes:
    """
    files: archive path -> content bytes.
    BẮT BUỘC thêm entry thư mục — thiếu dir khiến dpkg -i lỗi
    \"unable to create ... No such file or directory\".
    """
    buf = io.BytesIO()
    mtime = int(time.time())
    added: set[str] = set()

    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.GNU_FORMAT) as tar:

        def add_dir(name: str) -> None:
            name = _normalize_tar_path(name)
            if name in added:
                return
            info = tarfile.TarInfo(name=name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = mtime
            info.uid = 0
            info.gid = 0
            info.uname = 'root'
            info.gname = 'root'
            tar.addfile(info)
            added.add(name)

        def add_file(name: str, data: bytes) -> None:
            name = _normalize_tar_path(name)
            for d in _parent_dirs(name):
                add_dir(d)
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = mtime
            info.uid = 0
            info.gid = 0
            info.uname = 'root'
            info.gname = 'root'
            if name.endswith('.sh') or name.endswith('/justplay-cong-cu-it') or name.endswith('postinst'):
                info.mode = 0o755
            else:
                info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
            added.add(name)

        if include_root:
            add_dir('.')

        for name, data in sorted(files.items(), key=lambda kv: _normalize_tar_path(kv[0])):
            add_file(name, data)

    return buf.getvalue()


def _ar_member(name: str, data: bytes) -> bytes:
    """GNU ar member header (60 bytes) + data, padded to even size."""
    # deb(5): tên tối đa 15 ký tự + optional trailing slash
    name_field = (name + '/').encode('ascii')[:16].ljust(16)
    timestamp = str(int(time.time())).encode('ascii').ljust(12)
    owner = b'0'.ljust(6)
    group = b'0'.ljust(6)
    mode = b'100644'.ljust(8)
    size = str(len(data)).encode('ascii').ljust(10)
    magic = b'`\n'
    header = name_field + timestamp + owner + group + mode + size + magic
    assert len(header) == 60
    out = header + data
    if len(data) % 2 == 1:
        out += b'\n'
    return out


def _md5sums(files: dict[str, bytes]) -> bytes:
    lines = []
    for name, data in sorted(files.items(), key=lambda kv: _normalize_tar_path(kv[0])):
        rel = _normalize_tar_path(name)
        if rel.startswith('./'):
            rel = rel[2:]
        digest = hashlib.md5(data).hexdigest()
        lines.append(f'{digest}  {rel}\n')
    return ''.join(lines).encode('utf-8')


def build_ubuntu_it_deb(
    *,
    rustdesk_sh: bytes | None,
    equipment_sh: bytes | None,
    raidrive_sh: bytes | None,
    launcher_sh: bytes,
    config_json: bytes,
    desktop_entry: bytes | None = None,
) -> bytes:
    """
    Tạo file .deb (ar) chứa script Ubuntu + menu launcher.
    Cài: sudo apt install -fy ./justplay-cong-cu-it_....deb
    """
    share = 'usr/local/share/justplay-it'
    data_files: dict[str, bytes] = {
        f'{share}/JustPlay-Cong-Cu-IT-Ubuntu.sh': launcher_sh,
        f'{share}/JustPlay-NAS-Config.json': config_json,
        'usr/local/bin/justplay-cong-cu-it': (
            b'#!/bin/sh\n'
            b'exec /usr/local/share/justplay-it/JustPlay-Cong-Cu-IT-Ubuntu.sh "$@"\n'
        ),
    }
    if rustdesk_sh:
        data_files[f'{share}/JustPlay-RustDesk-Setup.sh'] = rustdesk_sh
    if equipment_sh:
        data_files[f'{share}/JustPlay-Equipment-Scan.sh'] = equipment_sh
    if raidrive_sh:
        data_files[f'{share}/JustPlay-RaiDrive-Setup.sh'] = raidrive_sh

    if desktop_entry is None:
        desktop_entry = (
            '[Desktop Entry]\n'
            'Type=Application\n'
            'Name=JustPlay Công cụ IT\n'
            'Comment=RustDesk, cấu hình máy, RaiDrive (Ubuntu)\n'
            'Exec=justplay-cong-cu-it\n'
            'Terminal=true\n'
            'Categories=System;Utility;\n'
            'Keywords=JustPlay;RustDesk;IT;\n'
        ).encode('utf-8')
    data_files['usr/share/applications/justplay-cong-cu-it.desktop'] = desktop_entry

    # Chuẩn hóa LF (tránh CRLF từ Windows làm bash lỗi)
    for key, val in list(data_files.items()):
        if key.endswith('.sh') or key.endswith('/justplay-cong-cu-it') or key.endswith('.desktop'):
            text = val.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
            if not text.endswith('\n'):
                text += '\n'
            data_files[key] = text.encode('utf-8')

    data_tar = _tar_gz_bytes(data_files)

    installed_size_kb = max(1, sum(len(v) for v in data_files.values()) // 1024)
    # Depends chỉ bash — zenity/whiptail là tùy chọn (Recommends), tránh apt fail trên máy thiếu GUI
    control = (
        f'Package: {PACKAGE_NAME}\n'
        f'Version: {PACKAGE_VERSION}\n'
        f'Section: utils\n'
        f'Priority: optional\n'
        f'Architecture: {ARCH}\n'
        f'Maintainer: JustPlay IT <it@justplay.vn>\n'
        f'Installed-Size: {installed_size_kb}\n'
        f'Depends: bash\n'
        f'Recommends: zenity | whiptail | dialog\n'
        f'Description: JustPlay Cong cu IT cho Ubuntu\n'
        f' Menu cai RustDesk, them cau hinh may, RaiDrive CLI.\n'
        f' Tai tu Portal JustPlay (ca nhan hoa theo user).\n'
        f'\n'
    ).encode('utf-8')

    postinst = (
        '#!/bin/sh\n'
        'set -e\n'
        'chmod 755 /usr/local/bin/justplay-cong-cu-it 2>/dev/null || true\n'
        'chmod 755 /usr/local/share/justplay-it/*.sh 2>/dev/null || true\n'
        'command -v update-desktop-database >/dev/null 2>&1 && '
        'update-desktop-database -q /usr/share/applications 2>/dev/null || true\n'
        'exit 0\n'
    ).encode('utf-8')

    control_files = {
        'control': control,
        'md5sums': _md5sums(data_files),
        'postinst': postinst,
    }
    control_tar = _tar_gz_bytes(control_files)
    debian_binary = b'2.0\n'

    out = b'!<arch>\n'
    out += _ar_member('debian-binary', debian_binary)
    out += _ar_member('control.tar.gz', control_tar)
    out += _ar_member('data.tar.gz', data_tar)
    return out


def deb_filename() -> str:
    return f'{PACKAGE_NAME}_{PACKAGE_VERSION}_{ARCH}.deb'


def read_launcher_template(base_dir: Path) -> bytes:
    path = base_dir / 'scripts' / 'JustPlay-Cong-Cu-IT-Ubuntu.sh'
    body = path.read_text(encoding='utf-8')
    body = body.replace('\r\n', '\n')
    if not body.endswith('\n'):
        body += '\n'
    return body.encode('utf-8')
