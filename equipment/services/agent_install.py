"""Tạo gói cài Agent 1 file (.cmd) cá nhân hóa theo user đăng nhập."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


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


def create_install_token(user) -> 'AgentInstallToken':
    from equipment.models import AgentInstallToken

    AgentInstallToken.objects.filter(user=user, used_at__isnull=True).delete()
    return AgentInstallToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(hours=48),
    )


def link_user_from_agent_report(*, data: dict, device) -> None:
    """Gán user portal + hồ sơ HRM + đăng ký PC sau khi agent báo cáo."""
    from django.contrib.auth import get_user_model

    from equipment.models import AgentInstallToken, UserAgentRegistration
    from equipment.services.agent_device import (
        apply_agent_payload_from_data,
        apply_user_profile_to_device,
    )

    User = get_user_model()
    user = None
    install_token = (data.get('install_token') or '').strip()

    if install_token:
        tok = AgentInstallToken.objects.filter(token=install_token).select_related('user').first()
        if tok and tok.is_valid():
            user = tok.user
            tok.mark_used()

    if not user:
        uid = data.get('portal_user_id')
        if uid is not None and str(uid).isdigit():
            user = User.objects.select_related('profile__department', 'profile__division').filter(
                pk=int(uid),
            ).first()

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
    return (value or '').replace('^', '^^').replace('&', '^&').replace('|', '^|').replace('<', '^<')


def build_installer_cmd(*, user, token: str) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')
    payload = user_agent_payload(user)
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
        '(',
        'echo [portal]',
        f'echo url={base}',
        f'echo secret={secret}',
        'echo.',
        'echo [user]',
        f'echo portal_user_id={payload["portal_user_id"]}',
        f'echo username={_cmd_escape(payload["username"])}',
        f'echo full_name={_cmd_escape(payload["full_name"])}',
        f'echo email={_cmd_escape(payload["email"])}',
        f'echo department={_cmd_escape(payload["department"])}',
        f'echo department_id={payload["department_id"]}',
        f'echo division={_cmd_escape(payload["division"])}',
        f'echo job_position={_cmd_escape(payload["job_position"])}',
        f'echo job_title={_cmd_escape(payload["job_title"])}',
        f'echo employee_code={_cmd_escape(payload["employee_code"])}',
        f'echo install_token={token}',
        'echo.',
        'echo [agent]',
        'echo interval_minutes=30',
        'echo poll_seconds=60',
        ') > "%JP_DIR%\\justplay_agent.ini"',
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
