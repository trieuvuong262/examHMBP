"""Tạo gói cài Agent 1 file (.cmd) cá nhân hóa theo user đăng nhập."""

from __future__ import annotations

import base64
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


def build_agent_ini_content(
    *,
    base_url: str,
    secret: str,
    payload: dict,
    token: str,
    machine_type: str,
) -> str:
    """Nội dung justplay_agent.ini — UTF-8, không qua cmd echo."""
    lines = [
        '[portal]',
        f'url={base_url}',
        f'secret={secret}',
        '',
        '[user]',
        f'portal_user_id={payload["portal_user_id"]}',
        f'username={payload["username"]}',
        f'full_name={payload["full_name"]}',
        f'email={payload["email"]}',
        f'department={payload["department"]}',
        f'department_id={payload["department_id"]}',
        f'division={payload["division"]}',
        f'job_position={payload["job_position"]}',
        f'job_title={payload["job_title"]}',
        f'employee_code={payload["employee_code"]}',
        f'install_token={token}',
        f'machine_type={machine_type}',
        '',
        '[agent]',
        'scan_once=1',
        '',
    ]
    return '\r\n'.join(lines)


_PORTAL_INSTALL_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$u = $env:JP_PORTAL_URL
$page = $env:JP_APP_PAGE
$iconUrl = $env:JP_ICON_URL
$jpDir = $env:JP_DIR
if (-not $jpDir) { $jpDir = Join-Path $env:LOCALAPPDATA 'JustPlayAgent' }
if (-not $u) {
    Write-Error '[5/6] PWA: thieu JP_PORTAL_URL'
    exit 1
}
if (-not $page) { $page = $u }
$installUrl = $u.TrimEnd('/') + '/'
$pwaProfile = Join-Path $jpDir 'browser-pwa-profile'
if (-not (Test-Path $pwaProfile)) { New-Item -ItemType Directory -Path $pwaProfile -Force | Out-Null }

function Write-JpLog([string]$msg) {
    if ($env:JP_LOG) { Add-Content -Path $env:JP_LOG -Value $msg -Encoding UTF8 -ErrorAction SilentlyContinue }
}

Write-JpLog '[5/6] PWA: bat dau'

function Get-JpPortalIconFile {
    if (-not $iconUrl -or -not $jpDir) { return $null }
    $iconFile = Join-Path $jpDir 'portal-icon.png'
    if (-not (Test-Path $iconFile)) {
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $iconUrl -OutFile $iconFile -UseBasicParsing
        } catch {}
    }
    if (Test-Path $iconFile) { return $iconFile }
    return $null
}

function Add-JpPortalAppShortcut([string]$browser, [string]$appUrl, [string]$linkPath) {
    if (-not $browser -or -not $appUrl -or -not $linkPath) { return $false }
    try {
        $dir = Split-Path $linkPath -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $wsh = New-Object -ComObject WScript.Shell
        $lnk = $wsh.CreateShortcut($linkPath)
        $lnk.TargetPath = $browser
        $lnk.Arguments = '--app=' + $appUrl
        $lnk.Description = 'JustPlay Portal'
        $iconFile = Get-JpPortalIconFile
        if ($iconFile) { $lnk.IconLocation = "$iconFile,0" }
        $lnk.Save()
        return $true
    } catch { return $false }
}

function Invoke-ShortcutShellVerb([string]$linkPath, [string]$verb) {
    if (-not (Test-Path $linkPath)) { return $false }
    try {
        $dir = Split-Path $linkPath -Parent
        $name = [System.IO.Path]::GetFileName($linkPath)
        $shell = New-Object -ComObject Shell.Application
        $folder = $shell.Namespace($dir)
        if (-not $folder) { return $false }
        $item = $folder.ParseName($name)
        if (-not $item) { return $false }
        $item.InvokeVerb($verb)
        return $true
    } catch { return $false }
}

function Set-JpPortalAutoStart([string]$browser, [string]$appUrl) {
    if (-not $browser -or -not $appUrl) { return }
    $runCmd = "`"$browser`" --app=$appUrl"
    try {
        Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
            -Name 'JustPlayPortal' -Value $runCmd -ErrorAction Stop
        Write-JpLog '[5/6] PWA: auto-start Run (JustPlayPortal)'
    } catch {
        Write-JpLog '[5/6] PWA: auto-start Run that bai'
    }
}

function Deploy-JustPlayPortalShortcuts([string]$browser, [string]$appUrl) {
    $desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'JustPlay Portal.lnk'
    $programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'JustPlay Portal.lnk'
    $startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'JustPlay Portal.lnk'
    $commonPrograms = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'JustPlay Portal.lnk'

    foreach ($path in @($programs, $desktop, $startup, $commonPrograms)) {
        if (Add-JpPortalAppShortcut $browser $appUrl $path) {
            Write-JpLog "[5/6] PWA: shortcut $path"
        }
    }

    if (Test-Path $programs) { Copy-Item $programs $desktop -Force -ErrorAction SilentlyContinue }
    if (Test-Path $programs) { Copy-Item $programs $startup -Force -ErrorAction SilentlyContinue }

    if (Invoke-ShortcutShellVerb $desktop 'pintostartmenu') {
        Write-JpLog '[5/6] PWA: pin Start menu (verb)'
    }
    if (Invoke-ShortcutShellVerb $desktop 'taskbarpin') {
        Write-JpLog '[5/6] PWA: pin taskbar (verb)'
    }

    $taskbarDir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
    if ((Test-Path $taskbarDir) -and (Test-Path $desktop)) {
        Copy-Item $desktop (Join-Path $taskbarDir 'JustPlay Portal.lnk') -Force -ErrorAction SilentlyContinue
        Write-JpLog '[5/6] PWA: copy taskbar Quick Launch'
    }

    Set-JpPortalAutoStart $browser $appUrl
}

$edge = @(
    ${env:ProgramFiles(x86)} + '\Microsoft\Edge\Application\msedge.exe',
    $env:ProgramFiles + '\Microsoft\Edge\Application\msedge.exe'
)
$chrome = @(
    ${env:ProgramFiles(x86)} + '\Google\Chrome\Application\chrome.exe',
    $env:ProgramFiles + '\Google\Chrome\Application\chrome.exe'
)

function Start-JpBrowserWindow([string]$browserPath, [string]$url, [string[]]$extra) {
    if (-not $browserPath -or -not $url) { return $false }
    $args = @(
        "--user-data-dir=$pwaProfile",
        '--no-first-run',
        '--no-default-browser-check',
        '--new-window',
        $url
    )
    if ($extra) { $args = $extra + $args }
    try {
        $proc = Start-Process -FilePath $browserPath -ArgumentList $args -PassThru -WindowStyle Normal -ErrorAction Stop
        Write-JpLog "[5/6] PWA: mo $url (pid=$($proc.Id))"
        return $true
    } catch {
        Write-JpLog "[5/6] PWA: mo trang that bai — $($_.Exception.Message)"
        return $false
    }
}

$browser = $null
foreach ($p in ($edge + $chrome)) {
    if (Test-Path $p) { $browser = $p; break }
}
if (-not $browser) {
    Write-JpLog '[5/6] PWA: khong tim thay Edge/Chrome — thu trinh duyet mac dinh'
    try {
        Start-Process $page -ErrorAction Stop
        Write-JpLog '[5/6] PWA: da mo bang Start-Process (mac dinh)'
    } catch {
        Write-Error '[5/6] PWA: khong mo duoc trinh duyet'
        exit 1
    }
    Start-Sleep -Seconds 20
} else {
    Write-JpLog '[5/6] PWA: mo trang Cai JustPlay Portal (cua so moi)'
    if (-not (Start-JpBrowserWindow $browser $page)) { exit 1 }
    Start-Sleep -Seconds 25

    Write-JpLog '[5/6] PWA: goi --install-app (trang cai)'
    Start-Process -FilePath $browser -ArgumentList @(
        "--user-data-dir=$pwaProfile",
        '--no-first-run',
        ('--install-app=' + $page)
    ) -WindowStyle Normal -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    Write-JpLog '[5/6] PWA: goi --install-app (start_url)'
    Start-Process -FilePath $browser -ArgumentList @(
        "--user-data-dir=$pwaProfile",
        '--no-first-run',
        ('--install-app=' + $installUrl)
    ) -WindowStyle Normal -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

Deploy-JustPlayPortalShortcuts $browser $installUrl

Write-JpLog '[5/6] PWA: Desktop + Startup + pin (best-effort) + auto-start Run'
Write-JpLog '[5/6] PWA: neu chua thay hop thoai — tren tab dang mo bam nut Cai hoac menu Apps > Install'
Write-JpLog '[5/6] PWA: xong'
exit 0
"""


def portal_install_powershell_script() -> str:
    """Script PowerShell bước 5 — phục vụ tải qua /thiet-bi/agent/jp-portal-install.ps1."""
    return _PORTAL_INSTALL_PS


def _installer_portal_ps_b64() -> str:
    return base64.b64encode(_PORTAL_INSTALL_PS.encode('utf-16le')).decode('ascii')


def _installer_uv_password() -> str:
    from equipment.agent.ultraviewer import resolve_ultraviewer_password

    return resolve_ultraviewer_password()


def _installer_uv_setup_url() -> str:
    from equipment.agent.ultraviewer import resolve_ultraviewer_setup_url

    return resolve_ultraviewer_setup_url()


def _ultraviewer_collect_b64() -> str:
    from equipment.agent.ultraviewer import ultraviewer_collect_b64

    return ultraviewer_collect_b64(
        _installer_uv_password(),
        _installer_uv_setup_url(),
    )


def build_installer_cmd(*, user, token: str, machine_type: str | None = None) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')
    payload = user_agent_payload(user)
    machine_type = normalize_machine_type(machine_type)
    portal_url = f'{base}/'
    portal_app_page = f'{base}/thiet-bi/agent/cai-portal-app/?autoinstall=1'
    portal_icon_url = f'{base}/static/images/logo/icon-192.png'
    exe_url = f'{base}/thiet-bi/agent/exe/'
    done_url = f'{base}/thiet-bi/agent/hoan-tat/?token={token}'
    secret = getattr(settings, 'EQUIPMENT_AGENT_SECRET', '')
    ini_b64 = base64.b64encode(
        build_agent_ini_content(
            base_url=base,
            secret=secret,
            payload=payload,
            token=token,
            machine_type=machine_type,
        ).encode('utf-8'),
    ).decode('ascii')

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
        'echo [1/5] Tai JustPlayAgent.exe...',
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
        'echo [2/5] Tao cau hinh...',
        'set "JP_INI=%JP_DIR%\\justplay_agent.ini"',
        'del /f /q "%JP_INI%" >nul 2>&1',
        (
            'powershell -NoProfile -ExecutionPolicy Bypass -Command '
            f'"[IO.File]::WriteAllBytes(\'%JP_DIR%\\justplay_agent.ini\', '
            f'[Convert]::FromBase64String(\'{ini_b64}\'))"'
        ),
        'if not exist "%JP_INI%" (',
        '  echo  LOI: Khong tao duoc justplay_agent.ini',
        '  goto :end_fail',
        ')',
        'findstr /C:"install_token=" "%JP_INI%" >nul 2>&1 || (',
        '  echo  LOI: File cau hinh thieu install_token',
        '  goto :end_fail',
        ')',
        'findstr /C:"portal_user_id=" "%JP_INI%" >nul 2>&1 || (',
        '  echo  LOI: File cau hinh thieu portal_user_id',
        '  goto :end_fail',
        ')',
        'echo      OK',
        'echo.',
        'echo [3/5] Go bo Agent tu khoi dong Windows (neu co ban cu)...',
        'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "JustPlayAgent" /f >nul 2>> "%JP_LOG%"',
        'schtasks /Delete /TN "JustPlay-Agent" /F >nul 2>&1',
        'echo      OK ^(Agent chi quet 1 lan khi cai^)',
        'echo.',
        'echo [4/5] Quet PC, UltraViewer, gui len portal...',
        f'set "JP_UV_PASSWORD={_installer_uv_password()}"',
        f'set "JP_UV_SETUP_URL={_installer_uv_setup_url()}"',
        'if exist "%JP_DIR%\\ultraviewer_sidecar.json" del /f /q "%JP_DIR%\\ultraviewer_sidecar.json" >nul 2>&1',
        'echo      UltraViewer: cai neu chua co, dat mat khau co dinh, doc ID...',
        (
            'powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand '
            f'{_ultraviewer_collect_b64()} 2>> "%JP_LOG%"'
        ),
        'if exist "%JP_DIR%\\ultraviewer_sidecar.json" (echo      UltraViewer: OK) else (echo      UltraViewer: that bai - chuot phai .cmd -^> Run as administrator)',
        'if exist "%JP_DIR%\\.justplay_agent_state.json" del /f /q "%JP_DIR%\\.justplay_agent_state.json" >nul 2>&1',
        'timeout /t 2 /nobreak >nul',
        '"%JP_DIR%\\JustPlayAgent.exe" --once',
        'if errorlevel 1 (',
        '  echo.',
        '  echo  LOI: Agent khong gui duoc thong tin PC.',
        '  echo  Thu: chuot phai file cai -^> Run as administrator',
        '  echo  Log: %JP_LOG%',
        '  goto :end_fail',
        ')',
        'echo      OK',
        'echo.',
        f'set "JP_PORTAL_URL={portal_url}"',
        f'set "JP_APP_PAGE={portal_app_page}"',
        f'set "JP_ICON_URL={portal_icon_url}"',
        'echo [5/5] Cai ung dung JustPlay Portal (Install app)...',
        'echo      Dang tai script cai Portal...',
        f'curl -fsSL "{base}/thiet-bi/agent/jp-portal-install.ps1" -o "%JP_DIR%\\jp-portal-install.ps1" 2>> "%JP_LOG%"',
        'if not exist "%JP_DIR%\\jp-portal-install.ps1" (',
        '  echo      curl that bai - thu PowerShell...',
        (
            '  powershell -NoProfile -ExecutionPolicy Bypass -Command '
            f'"[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; '
            f'Invoke-WebRequest -Uri \'{base}/thiet-bi/agent/jp-portal-install.ps1\' '
            f'-OutFile \'%JP_DIR%\\jp-portal-install.ps1\' -UseBasicParsing" 2>> "%JP_LOG%"'
        ),
        ')',
        'if not exist "%JP_DIR%\\jp-portal-install.ps1" (',
        '  echo  LOI: Khong tai duoc jp-portal-install.ps1',
        '  echo  Xem log: %JP_LOG%',
        '  goto :end_fail',
        ')',
        'echo      Mo trang Cai JustPlay Portal ^(Edge/Chrome^)...',
        'if exist "%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe" (',
        '  start "" "%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe" --user-data-dir="%JP_DIR%\\browser-pwa-profile" --new-window "%JP_APP_PAGE%"',
        ') else if exist "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe" (',
        '  start "" "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe" --user-data-dir="%JP_DIR%\\browser-pwa-profile" --new-window "%JP_APP_PAGE%"',
        ') else if exist "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" (',
        '  start "" "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" --user-data-dir="%JP_DIR%\\browser-pwa-profile" --new-window "%JP_APP_PAGE%"',
        ') else (',
        '  start "" "%JP_APP_PAGE%"',
        ')',
        'echo      Neu khong thay cua so: kiem tra taskbar Edge/Chrome.',
        'echo      Dang chay cai Portal ^(co the mat 30-60 giay^)...',
        'powershell -NoProfile -ExecutionPolicy Bypass -File "%JP_DIR%\\jp-portal-install.ps1" 2>> "%JP_LOG%"',
        'if errorlevel 1 (',
        '  echo  LOI: Buoc 5 cai Portal that bai',
        '  echo  Xem log: %JP_LOG%',
        '  goto :end_fail',
        ')',
        'echo      OK',
        'echo      Da mo trang cai + goi Install app (Edge/Chrome).',
        'echo      Neu co hop thoai: bam **Cai dat** / **Install**.',
        'echo      Tu dong: Desktop shortcut, Startup, pin taskbar/Start (neu Windows cho phep),',
        'echo      auto-start khi dang nhap Windows (Registry JustPlayPortal).',
        'echo.',
        'echo      Mo trang xac nhan portal...',
        'timeout /t 5 /nobreak >nul',
        f'start "" "{done_url}"',
        'echo.',
        'echo  ========================================',
        'echo   THANH CONG',
        'echo   - Da gui thong tin PC + UltraViewer (neu co)',
        'echo   - Da goi cai ung dung Portal (Install app)',
        'echo  ========================================',
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
