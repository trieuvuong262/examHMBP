"""Tạo gói cài Agent 1 file (.cmd) cá nhân hóa theo user đăng nhập."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


MACHINE_TYPE_COMPANY = 'company'
MACHINE_TYPE_PERSONAL = 'personal'
VALID_MACHINE_TYPES = {MACHINE_TYPE_COMPANY, MACHINE_TYPE_PERSONAL}


def normalize_machine_type(value: str | None) -> str:
    if value in VALID_MACHINE_TYPES:
        return value
    return MACHINE_TYPE_COMPANY


def agent_gate_enabled() -> bool:
    """Bật màn hình bắt buộc cài agent (middleware + trang gate)."""
    return bool(getattr(settings, 'EQUIPMENT_REQUIRE_AGENT_INSTALL', False))


def agent_install_enabled() -> bool:
    """Agent API + file cài — cần secret."""
    return bool(getattr(settings, 'EQUIPMENT_AGENT_SECRET', ''))


def is_exempt_from_agent_gate(user) -> bool:
    """Chỉ tài khoản admin (cấu hình) được bỏ qua gate."""
    raw = getattr(settings, 'EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES', 'admin')
    allowed = {name.strip().lower() for name in raw.split(',') if name.strip()}
    return user.username.lower() in allowed


def user_is_in_equipment_registry(user) -> bool:
    """User đã có trong quản lý thiết bị (gán trực tiếp hoặc đã cài agent)."""
    from equipment.models import Device, UserAgentRegistration

    if Device.objects.filter(assigned_user=user).exists():
        return True
    if UserAgentRegistration.objects.filter(user=user).exists():
        return True

    if Device.objects.filter(assigned_user_text__iexact=user.username).exists():
        return True
    profile = getattr(user, 'profile', None)
    if profile and profile.full_name:
        if Device.objects.filter(assigned_user_text__iexact=profile.full_name).exists():
            return True
    return False


def is_agent_install_required(request) -> bool:
    if not agent_gate_enabled():
        return False
    user = request.user
    if not user.is_authenticated:
        return False
    if is_exempt_from_agent_gate(user):
        return False
    ua = request.META.get('HTTP_USER_AGENT', '')
    if 'Windows' not in ua:
        return False
    if user_is_in_equipment_registry(user):
        return False
    return True


def user_agent_payload(user) -> dict:
    profile = getattr(user, 'profile', None)
    dept = ''
    dept_id = ''
    division = ''
    job_position = ''
    job_title = ''
    employee_code = ''
    if profile:
        if profile.department_id:
            dept = profile.department.name
            dept_id = str(profile.department_id)
        if profile.division_id:
            division = profile.division.name
        job_position = profile.job_position or ''
        job_title = profile.job_title or ''
        employee_code = profile.employee_code or ''
    full_name = ''
    if profile and profile.full_name:
        full_name = profile.full_name
    elif user.get_full_name():
        full_name = user.get_full_name()
    return {
        'portal_user_id': user.pk,
        'username': user.username,
        'full_name': full_name,
        'email': user.email or '',
        'department': dept,
        'department_id': dept_id,
        'division': division,
        'job_position': job_position,
        'job_title': job_title,
        'employee_code': employee_code,
    }


def create_install_token(user, machine_type: str | None = None) -> 'AgentInstallToken':
    from equipment.models import AgentInstallToken

    AgentInstallToken.objects.filter(user=user, used_at__isnull=True).delete()
    return AgentInstallToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        machine_type=normalize_machine_type(machine_type),
        expires_at=timezone.now() + timedelta(hours=48),
    )


def resolve_machine_type_from_report(data: dict) -> str:
    """Ưu tiên install_token trên server, sau đó field agent gửi kèm."""
    from equipment.models import AgentInstallToken

    install_token = (data.get('install_token') or '').strip()
    if install_token:
        tok = AgentInstallToken.objects.filter(token=install_token).only('machine_type').first()
        if tok:
            return normalize_machine_type(tok.machine_type)
    return normalize_machine_type(data.get('machine_type'))


def resolve_user_from_agent_data(data: dict):
    """Lấy user từ install_token (kể cả đã dùng) hoặc portal_user_id."""
    from django.contrib.auth import get_user_model

    from equipment.models import AgentInstallToken

    User = get_user_model()
    install_token = (data.get('install_token') or '').strip()

    if install_token:
        tok = (
            AgentInstallToken.objects.filter(token=install_token)
            .select_related('user__profile__department', 'user__profile__division')
            .first()
        )
        if tok:
            return tok.user, tok

    uid = data.get('portal_user_id')
    if uid is not None and str(uid).isdigit():
        user = User.objects.select_related('profile__department', 'profile__division').filter(
            pk=int(uid),
        ).first()
        if user:
            return user, None

    username = (data.get('username') or '').strip()
    if username:
        user = User.objects.select_related('profile__department', 'profile__division').filter(
            username__iexact=username,
        ).first()
        if user:
            return user, None

    return None, None


def ensure_user_registered_for_device(*, user, device) -> bool:
    """Đảm bảo user có trong registry sau báo cáo agent (máy công ty)."""
    from equipment.services.shared_pc import confirm_user_on_shared_device, user_registered_on_device

    if not user or not device:
        return False
    if user_is_in_equipment_registry(user):
        return True
    if not user_registered_on_device(user, device):
        confirm_user_on_shared_device(user, device)
    return user_is_in_equipment_registry(user)


def try_reconcile_agent_registration(request) -> bool:
    """
    Trang hoàn tất: agent đã gửi PC lên portal nhưng poll chưa thấy registry —
    gắn user theo cookie hostname / serial hoặc thiết bị vừa quét.
    """
    from datetime import timedelta

    from equipment.models import Device
    from equipment.services.shared_pc import (
        confirm_user_on_shared_device,
        find_device_for_client_request,
        user_registered_on_device,
    )

    user = request.user
    if not user.is_authenticated or user_is_in_equipment_registry(user):
        return user_is_in_equipment_registry(user)

    device = find_device_for_client_request(request)
    since = timezone.now() - timedelta(hours=2)

    if not device:
        hostname = (request.COOKIES.get('jp_hostname') or '').strip()
        if hostname:
            device = (
                Device.objects.filter(
                    hostname__iexact=hostname,
                    last_scan_date__gte=since,
                )
                .order_by('-last_scan_date')
                .first()
            )

    if not device:
        serial = (request.COOKIES.get('jp_agent_serial') or '').strip()
        if serial:
            device = Device.objects.filter(serial_number=serial).first()

    if device and not user_registered_on_device(user, device):
        confirm_user_on_shared_device(user, device)

    return user_is_in_equipment_registry(user)


def register_personal_agent_from_report(*, data: dict) -> bool:
    """
    Máy cá nhân: chỉ lưu UserAgentRegistration (device=null), không tạo thiết bị IT.
    Trả về True nếu đã gắn user.
    """
    from equipment.models import UserAgentRegistration

    serial = (data.get('serial') or '').strip()
    if not serial:
        return False

    from equipment.agent.core import is_bad_serial

    if is_bad_serial(serial):
        return False

    user, tok = resolve_user_from_agent_data(data)
    if not user:
        return False
    if tok and tok.is_valid():
        tok.mark_used()

    UserAgentRegistration.objects.update_or_create(
        user=user,
        serial_number=serial,
        defaults={'device': None},
    )
    return True


def link_user_from_agent_report(*, data: dict, device) -> None:
    """Gán user portal + hồ sơ HRM + đăng ký PC sau khi agent báo cáo."""
    from equipment.models import UserAgentRegistration
    from equipment.services.agent_device import (
        apply_agent_payload_from_data,
        apply_user_profile_to_device,
    )

    user, tok = resolve_user_from_agent_data(data)
    if user and tok and tok.is_valid():
        tok.mark_used()

    fields: set[str] = set()
    if user:
        # PC dùng chung: không ghi đè assigned_user nếu đã có người khác.
        if not device.assigned_user_id or device.assigned_user_id == user.pk:
            fields.update(apply_user_profile_to_device(device, user))
    fields.update(apply_agent_payload_from_data(device, data))

    if fields:
        device.save(update_fields=sorted(fields))

    if not user:
        return

    UserAgentRegistration.objects.update_or_create(
        user=user,
        serial_number=device.serial_number,
        defaults={'device': device},
    )


def _cmd_escape(value: str) -> str:
    """Escape cho echo trong khối ( ) của cmd — tránh đứt file .ini."""
    s = value or ''
    for char, repl in (
        ('^', '^^'),
        ('&', '^&'),
        ('|', '^|'),
        ('<', '^<'),
        ('>', '^>'),
        (')', '^)'),
        ('(', '^('),
        ('%', '%%'),
    ):
        s = s.replace(char, repl)
    return s


def _powershell_ini_line(key: str, value: str) -> str:
    """Một dòng ini an toàn (Unicode, ký tự đặc biệt)."""
    safe = (value or '').replace("'", "''")
    return f"Add-Content -LiteralPath $ini -Value '{key}={safe}' -Encoding UTF8"


def build_installer_cmd(*, user, token: str, machine_type: str | None = None) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')
    payload = user_agent_payload(user)
    machine_type = normalize_machine_type(machine_type)
    exe_url = f'{base}/thiet-bi/agent/exe/'
    done_url = f'{base}/thiet-bi/agent/hoan-tat/?token={token}'
    secret = getattr(settings, 'EQUIPMENT_AGENT_SECRET', '')

    lines = [
        '@echo off',
        'setlocal EnableExtensions',
        'chcp 65001 >nul 2>&1',
        'title JustPlay - Cai dat Agent thiet bi',
        'cd /d "%~dp0"',
        'if /I not "%~1"=="_run" (',
        '  cmd /k call "%~f0" _run',
        '  exit /b',
        ')',
        'echo.',
        'echo  ========================================',
        'echo   JustPlay Agent - dang cai dat...',
        'echo  ========================================',
        'echo.',
        'set "JP_DIR=%LOCALAPPDATA%\\JustPlayAgent"',
        'set "JP_LOG=%JP_DIR%\\install.log"',
        'if not exist "%JP_DIR%" mkdir "%JP_DIR%"',
        'echo [%date% %time%] Bat dau >> "%JP_LOG%"',
        'echo Thu muc: %JP_DIR%',
        'echo.',
        'echo [1/4] Tai JustPlayAgent.exe...',
        f'curl -fsSL "{exe_url}" -o "%JP_DIR%\\JustPlayAgent.exe" 2>> "%JP_LOG%"',
        'if not exist "%JP_DIR%\\JustPlayAgent.exe" (',
        '  echo curl that bai - thu PowerShell...',
        f'  powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri \'{exe_url}\' -OutFile \'%JP_DIR%\\JustPlayAgent.exe\' -UseBasicParsing" 2>> "%JP_LOG%"',
        ')',
        'if not exist "%JP_DIR%\\JustPlayAgent.exe" (',
        '  echo.',
        '  echo  LOI: Khong tai duoc JustPlayAgent.exe',
        '  echo  Xem log: %JP_LOG%',
        '  goto :end_fail',
        ')',
        'echo      OK',
        'echo.',
        'echo [2/4] Tao cau hinh...',
        'set "JP_INI=%JP_DIR%\\justplay_agent.ini"',
        'del /f /q "%JP_INI%" >nul 2>&1',
        'powershell -NoProfile -ExecutionPolicy Bypass -Command ^',
        '  "$ini=\'%JP_DIR%\\justplay_agent.ini\'; ^',
        '  New-Item -ItemType File -Path $ini -Force | Out-Null; ^',
        f"  Add-Content -LiteralPath $ini -Value '[portal]' -Encoding UTF8; ^",
        f"  Add-Content -LiteralPath $ini -Value 'url={base}' -Encoding UTF8; ^",
        f"  Add-Content -LiteralPath $ini -Value 'secret={secret}' -Encoding UTF8; ^",
        '  Add-Content -LiteralPath $ini -Value '' -Encoding UTF8; ^',
        "  Add-Content -LiteralPath $ini -Value '[user]' -Encoding UTF8; ^",
        f"  Add-Content -LiteralPath $ini -Value 'portal_user_id={payload['portal_user_id']}' -Encoding UTF8; ^",
        f"  {_powershell_ini_line('username', payload['username'])}; ^",
        f"  {_powershell_ini_line('full_name', payload['full_name'])}; ^",
        f"  {_powershell_ini_line('email', payload['email'])}; ^",
        f"  {_powershell_ini_line('department', payload['department'])}; ^",
        f"  Add-Content -LiteralPath $ini -Value 'department_id={payload['department_id']}' -Encoding UTF8; ^",
        f"  {_powershell_ini_line('division', payload['division'])}; ^",
        f"  {_powershell_ini_line('job_position', payload['job_position'])}; ^",
        f"  {_powershell_ini_line('job_title', payload['job_title'])}; ^",
        f"  {_powershell_ini_line('employee_code', payload['employee_code'])}; ^",
        f"  Add-Content -LiteralPath $ini -Value 'install_token={token}' -Encoding UTF8; ^",
        f"  Add-Content -LiteralPath $ini -Value 'machine_type={machine_type}' -Encoding UTF8; ^",
        '  Add-Content -LiteralPath $ini -Value '' -Encoding UTF8; ^',
        "  Add-Content -LiteralPath $ini -Value '[agent]' -Encoding UTF8; ^",
        "  Add-Content -LiteralPath $ini -Value 'interval_minutes=30' -Encoding UTF8; ^",
        "  Add-Content -LiteralPath $ini -Value 'poll_seconds=60' -Encoding UTF8",
        'if not exist "%JP_INI%" (',
        '  echo  LOI: Khong tao duoc justplay_agent.ini',
        '  goto :end_fail',
        ')',
        'echo      OK',
        'echo.',
        'echo [3/4] Dang ky chay khi dang nhap Windows...',
        'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "JustPlayAgent" /t REG_SZ /d "\"%JP_DIR%\\JustPlayAgent.exe\"" /f >nul 2>> "%JP_LOG%"',
        'net session >nul 2>&1',
        'if not errorlevel 1 (',
        '  schtasks /Delete /TN "JustPlay-Agent" /F >nul 2>&1',
        '  schtasks /Create /TN "JustPlay-Agent" /TR "\"%JP_DIR%\\JustPlayAgent.exe\"" /SC ONLOGON /RL LIMITED /F >nul 2>> "%JP_LOG%"',
        '  echo      OK ^(Task Scheduler^)',
        ') else (',
        '  echo      OK ^(Registry - khong can admin^)',
        ')',
        'echo.',
        'echo [4/4] Quet PC va gui len portal...',
        'if exist "%JP_DIR%\\.justplay_agent_state.json" del /f /q "%JP_DIR%\\.justplay_agent_state.json" >nul 2>&1',
        'timeout /t 3 /nobreak >nul',
        '"%JP_DIR%\\JustPlayAgent.exe" --once',
        'if errorlevel 1 (',
        '  echo.',
        '  echo  LOI: Agent khong gui duoc thong tin PC.',
        '  echo  Thu: chuot phai file cai -^> Run as administrator',
        '  echo  Log: %JP_LOG%',
        '  goto :end_fail',
        ')',
        'echo.',
        'echo  ========================================',
        'echo   THANH CONG - da gui thong tin PC',
        'echo  ========================================',
        f'start "" "{done_url}"',
        'echo  Trang portal se mo de xac nhan.',
        'echo.',
        'goto :end_ok',
        ':end_fail',
        'echo.',
        'echo  Nhan phim bat ky de dong...',
        'pause >nul',
        'exit /b 1',
        ':end_ok',
        'echo  Nhan phim bat ky de dong...',
        'pause >nul',
        'exit /b 0',
    ]
    return '\r\n'.join(lines) + '\r\n'
