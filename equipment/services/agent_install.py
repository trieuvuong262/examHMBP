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
    if profile and profile.department_id:
        dept = profile.department.name
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
    """Gán user portal + đăng ký PC sau khi agent báo cáo."""
    from django.contrib.auth import get_user_model

    from equipment.models import AgentInstallToken, UserAgentRegistration

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
            user = User.objects.filter(pk=int(uid)).first()

    if not user:
        return

    device.assigned_user = user
    full_name = (data.get('full_name') or '').strip()
    username = (data.get('username') or user.username).strip()
    if full_name:
        device.assigned_user_text = full_name
    elif username:
        device.assigned_user_text = username
    elif not device.assigned_user_text:
        profile = getattr(user, 'profile', None)
        if profile and profile.full_name:
            device.assigned_user_text = profile.full_name
    device.save(update_fields=['assigned_user', 'assigned_user_text'])

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

    lines = [
        '@echo off',
        'setlocal EnableDelayedExpansion',
        'chcp 65001 >nul',
        'title JustPlay - Cai dat Agent thiet bi',
        'echo.',
        'echo  JustPlay Agent - dang cai dat...',
        'echo.',
        'net session >nul 2>&1',
        'if errorlevel 1 (',
        '  echo Can quyen Administrator - bam Yes tren cua so UAC...',
        '  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath ''%~f0'' -ArgumentList ''_elevated'' -Verb RunAs -Wait"',
        '  exit /b !errorlevel!',
        ')',
        'if /I "%~1"=="_elevated" shift',
        'set "JP_DIR=%LOCALAPPDATA%\\JustPlayAgent"',
        'if not exist "%JP_DIR%" mkdir "%JP_DIR%"',
        f'curl -fsSL "{exe_url}" -o "%JP_DIR%\\JustPlayAgent.exe"',
        'if errorlevel 1 (',
        '  echo Khong tai duoc JustPlayAgent.exe - kiem tra mang.',
        '  pause',
        '  exit /b 1',
        ')',
        '(',
        'echo [portal]',
        f'echo url={base}',
        f'echo secret={getattr(settings, "EQUIPMENT_AGENT_SECRET", "")}',
        'echo.',
        'echo [user]',
        f'echo portal_user_id={payload["portal_user_id"]}',
        f'echo username={_cmd_escape(payload["username"])}',
        f'echo full_name={_cmd_escape(payload["full_name"])}',
        f'echo email={_cmd_escape(payload["email"])}',
        f'echo department={_cmd_escape(payload["department"])}',
        f'echo install_token={token}',
        'echo.',
        'echo [agent]',
        'echo interval_minutes=30',
        'echo poll_seconds=60',
        'echo first_delay_seconds=5',
        ') > "%JP_DIR%\\justplay_agent.ini"',
        'echo Dang ky agent chay khi dang nhap Windows...',
        'schtasks /Delete /TN "JustPlay-Agent" /F >nul 2>&1',
        'schtasks /Create /TN "JustPlay-Agent" /TR "\"%JP_DIR%\\JustPlayAgent.exe\"" /SC ONLOGON /RL LIMITED /F >nul 2>&1',
        'if errorlevel 1 (',
        '  echo Task Scheduler khong duoc - dung Registry Run ^(khong can admin^)...',
        '  reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "JustPlayAgent" /t REG_SZ /d "\"%JP_DIR%\\JustPlayAgent.exe\"" /f >nul',
        ')',
        'echo Cho 5 giay roi quet PC va gui len portal...',
        'timeout /t 5 /nobreak >nul',
        '"%JP_DIR%\\JustPlayAgent.exe" --once',
        'if errorlevel 1 (',
        '  echo.',
        '  echo  LOI: Khong gui duoc thong tin PC len portal.',
        '  echo  Thu chay lai file cai ^(Run as administrator^) hoac lien he IT.',
        '  pause',
        '  exit /b 1',
        ')',
        'echo.',
        'echo  Da gui thong tin PC len portal thanh cong.',
        f'start "" "{done_url}"',
        'echo  Trang portal se mo de xac nhan.',
        'timeout /t 5',
    ]
    return '\r\n'.join(lines) + '\r\n'
