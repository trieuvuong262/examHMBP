"""Quét WMI / dải IP — chỉ hỗ trợ Windows (dev/local)."""

from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess

from django.conf import settings
from django.utils import timezone

BAD_SERIALS = frozenset({
    'Default string',
    'To be filled by O.E.M.',
    'System Serial Number',
    'None',
    '00000000',
})


def is_wmi_scan_supported() -> bool:
    """WMI qua PowerShell — Windows và môi trường dev/local."""
    if platform.system().lower() != 'windows':
        return False
    return bool(getattr(settings, 'IS_LOCAL', False) or getattr(settings, 'DEBUG', False))


def wmi_unavailable_message() -> str:
    if platform.system().lower() != 'windows':
        return 'Quét WMI chỉ chạy trên Windows (máy dev). Server Linux/VPS dùng agent_scan.py.'
    return 'Quét WMI chỉ bật khi DEBUG hoặc DJANGO_ENV=local.'


def is_bad_serial(serial: str | None) -> bool:
    if not serial:
        return True
    text = str(serial).strip()
    if not text or text in BAD_SERIALS:
        return True
    return any(bad in text for bad in BAD_SERIALS)


def get_info_via_powershell(ip: str, username: str, password: str) -> dict | None:
    """Lấy Serial, Model, CPU, RAM, Disk qua PowerShell WMI."""
    is_local = False
    try:
        hostname = socket.gethostname()
        local_ips = {socket.gethostbyname(hostname), '127.0.0.1'}
        try:
            local_ips.update(socket.gethostbyname_ex(hostname)[2])
        except OSError:
            pass
        if ip in local_ips:
            is_local = True
    except OSError:
        pass

    safe_pass = password.replace("'", "''")
    ps_func = """
    function Get-Info {
        param([bool]$UseCreds)

        if ($UseCreds) {
            $sec = ConvertTo-SecureString '%s' -AsPlainText -Force;
            $cred = New-Object System.Management.Automation.PSCredential ('%s', $sec);
            $p = @{ ComputerName = '%s'; Credential = $cred; ErrorAction = 'Stop' }
        } else {
            $p = @{ ErrorAction = 'Stop' }
        }

        try {
            $bios = Get-WmiObject -Class Win32_BIOS @p;
            $sys = Get-WmiObject -Class Win32_ComputerSystem @p;
            $sn = $bios.SerialNumber;
            $model = $sys.Model;

            $bad = @('Default string', 'To be filled by O.E.M.', 'System Serial Number', 'None', '00000000');
            if ($bad -contains $sn -or [string]::IsNullOrWhiteSpace($sn)) {
                $board = Get-WmiObject -Class Win32_BaseBoard @p;
                $sn = $board.SerialNumber;
            }

            $cpuInfo = Get-WmiObject -Class Win32_Processor @p | Select-Object -First 1;
            $cpu = $cpuInfo.Name;

            $memItems = Get-WmiObject -Class Win32_PhysicalMemory @p;
            $totalRam = ($memItems | Measure-Object -Property Capacity -Sum).Sum;
            $ramGB = [math]::Round($totalRam / 1GB, 0);

            $diskInfo = Get-WmiObject -Class Win32_DiskDrive @p | Sort-Object Size -Descending | Select-Object -First 1;
            $diskSize = [math]::Round($diskInfo.Size / 1GB, 0);
            $diskName = $diskInfo.Model;

            return "SUCCESS|$sn|$model|$cpu|$ramGB|$diskName ($diskSize GB)";
        } catch {
            return "ERROR|$($_.Exception.Message)";
        }
    }
    """ % (safe_pass, username, ip)

    if is_local:
        final_script = ps_func + "\nWrite-Output (Get-Info -UseCreds $false)"
    else:
        final_script = ps_func + """
        $res = Get-Info -UseCreds $true;
        if ($res -like "*User credentials cannot be used for local connections*") {
            $res = Get-Info -UseCreds $false;
        }
        Write-Output $res
        """

    try:
        result = subprocess.run(
            ['powershell', '-Command', final_script],
            capture_output=True,
            text=True,
            timeout=45,
        )
        output = (result.stdout or '').strip()
        if output.startswith('SUCCESS|'):
            parts = output.split('|')
            if len(parts) >= 6:
                data = {
                    'serial': parts[1].strip(),
                    'model': parts[2].strip(),
                    'cpu': parts[3].strip(),
                    'ram': parts[4].strip(),
                    'disk': parts[5].strip(),
                }
                if is_bad_serial(data['serial']):
                    data['serial'] = None
                return data
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return None


def build_configuration(info: dict) -> str:
    return (
        f"CPU: {info.get('cpu', '—')}\n"
        f"RAM: {info.get('ram', '—')} GB\n"
        f"Disk: {info.get('disk', '—')}"
    )


def port_135_open(ip: str, *, timeout: float = 1.0) -> bool:
    try:
        socket.create_connection((ip, 135), timeout=timeout).close()
        return True
    except OSError:
        return False


def resolve_device_ip(device) -> tuple[str | None, bool]:
    """Trả về (ip, ip_changed)."""
    socket.setdefaulttimeout(2)
    target_ip = None
    ip_changed = False

    if device.hostname:
        try:
            resolved = socket.gethostbyname(device.hostname)
            if device.ip_address != resolved or not device.is_online:
                device.ip_address = resolved
                device.is_online = True
                ip_changed = True
            target_ip = resolved
        except OSError:
            if device.is_online:
                device.is_online = False
                device.save(update_fields=['is_online', 'updated_at'])

    if not target_ip and device.ip_address:
        target_ip = str(device.ip_address)
    return target_ip, ip_changed


def apply_wmi_info_to_device(device, info: dict) -> bool:
    """Cập nhật model/serial/config — True nếu serial/model đổi (cần vẽ lại QR)."""
    important_change = False
    if info.get('model') and device.model_number != info['model']:
        device.model_number = info['model']
        important_change = True

    new_sn = info.get('serial')
    if new_sn and not is_bad_serial(new_sn) and device.serial_number != new_sn:
        device.serial_number = new_sn
        important_change = True

    new_config = build_configuration(info)
    if device.configuration != new_config:
        device.configuration = new_config
        if not important_change:
            device.save(update_fields=['configuration', 'updated_at'])
    return important_change


def scan_device_wmi(device, *, username: str, password: str) -> tuple[bool, bool, bool]:
    """
    Quét một thiết bị.
    Returns: (ip_updated, wmi_updated, qr_redrawn)
    """
    ip_updated = False
    wmi_updated = False
    qr_redrawn = False

    target_ip, ip_changed = resolve_device_ip(device)
    if ip_changed:
        device.last_scan_date = timezone.now()
        device.save(update_fields=['ip_address', 'is_online', 'last_scan_date', 'updated_at'])
        ip_updated = True

    if target_ip and username and password and port_135_open(target_ip):
        info = get_info_via_powershell(target_ip, username, password)
        if info:
            important = apply_wmi_info_to_device(device, info)
            wmi_updated = True
            device.last_scan_date = timezone.now()
            if important:
                device.save()
                qr_redrawn = True
            else:
                device.save(update_fields=['last_scan_date', 'updated_at'])

    if not wmi_updated and not ip_updated:
        device.last_scan_date = timezone.now()
        device.save(update_fields=['last_scan_date', 'updated_at'])

    return ip_updated, wmi_updated, qr_redrawn


def discover_device_from_ip(ip_str: str, *, username: str, password: str):
    """Tìm máy trên IP — trả về (device, created) hoặc None."""
    from equipment.models import Device

    if not port_135_open(ip_str, timeout=0.5):
        return None

    info = get_info_via_powershell(ip_str, username, password)
    if not info or not info.get('serial') or is_bad_serial(info['serial']):
        return None

    device, created = Device.objects.get_or_create(
        serial_number=info['serial'],
        defaults={
            'name': f"{info.get('model', 'PC')} — {ip_str}",
            'managed_by': Device.MANAGED_IT,
            'category': 'PC',
            'status': Device.STATUS_ACTIVE,
        },
    )
    device.ip_address = ip_str
    device.model_number = info.get('model') or device.model_number
    device.configuration = build_configuration(info)
    device.is_online = True
    device.last_scan_date = timezone.now()

    try:
        host_val = socket.gethostbyaddr(ip_str)[0]
        device.hostname = host_val
        if created:
            device.name = host_val
    except OSError:
        pass

    device.save()
    return device, created


def parse_ip_range(start_ip: str, end_ip: str, *, max_hosts: int = 255) -> list[str]:
    start = ipaddress.IPv4Address(start_ip.strip())
    end = ipaddress.IPv4Address(end_ip.strip())
    if int(end) < int(start):
        raise ValueError('IP kết thúc phải lớn hơn hoặc bằng IP bắt đầu.')
    if int(end) - int(start) > max_hosts:
        raise ValueError(f'Chỉ quét tối đa {max_hosts} IP mỗi lần.')
    return [str(ipaddress.IPv4Address(i)) for i in range(int(start), int(end) + 1)]
