"""WMI / dải IP — không phụ thuộc Django (dùng scan_relay trên máy Windows IT)."""

from __future__ import annotations

import ipaddress
import socket
import subprocess

BAD_SERIALS = frozenset({
    'Default string',
    'To be filled by O.E.M.',
    'System Serial Number',
    'None',
    '00000000',
})


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
        socket.create_connection((ip, timeout), timeout=timeout).close()
        return True
    except OSError:
        return False


def resolve_target_ip(hostname: str | None, ip_address: str | None) -> tuple[str | None, bool, bool]:
    """Trả về (ip, ip_changed, is_online)."""
    socket.setdefaulttimeout(2)
    target_ip = None
    ip_changed = False
    is_online = True

    if hostname:
        try:
            resolved = socket.gethostbyname(hostname)
            if ip_address != resolved:
                ip_changed = True
            target_ip = resolved
        except OSError:
            is_online = False
            if ip_address:
                target_ip = str(ip_address)

    if not target_ip and ip_address:
        target_ip = str(ip_address)

    return target_ip, ip_changed, is_online


def scan_target_entry(
    *,
    target_id: str,
    hostname: str | None,
    ip_address: str | None,
    username: str,
    password: str,
) -> dict:
    """Quét một mục tiêu — payload cho portal."""
    target_ip, ip_changed, is_online = resolve_target_ip(hostname, ip_address)
    result = {
        'id': target_id,
        'ip_updated': ip_changed,
        'wmi_updated': False,
        'qr_redrawn': False,
        'ip_address': target_ip,
        'is_online': is_online,
        'hostname': hostname,
        'probe': None,
    }

    if target_ip and username and password and port_135_open(target_ip):
        probe = probe_ip(target_ip, username=username, password=password)
        if probe:
            result['wmi_updated'] = True
            result['probe'] = probe
            result['hostname'] = probe.get('hostname') or hostname
            result['ip_address'] = probe.get('ip') or target_ip
            result['is_online'] = True

    return result


def resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ip


def parse_ip_range(start_ip: str, end_ip: str, *, max_hosts: int = 255) -> list[str]:
    start = ipaddress.IPv4Address(start_ip.strip())
    end = ipaddress.IPv4Address(end_ip.strip())
    if int(end) < int(start):
        raise ValueError('IP kết thúc phải lớn hơn hoặc bằng IP bắt đầu.')
    if int(end) - int(start) > max_hosts:
        raise ValueError(f'Chỉ quét tối đa {max_hosts} IP mỗi lần.')
    return [str(ipaddress.IPv4Address(i)) for i in range(int(start), int(end) + 1)]


def probe_ip(ip: str, *, username: str, password: str) -> dict | None:
    """Quét một IP — trả payload cho API agent-report hoặc None."""
    if not port_135_open(ip, timeout=0.5):
        return None
    info = get_info_via_powershell(ip, username, password)
    if not info or not info.get('serial') or is_bad_serial(info['serial']):
        return None
    hostname = resolve_hostname(ip)
    return {
        'serial': info['serial'],
        'hostname': hostname,
        'model': info.get('model') or '',
        'cpu': info.get('cpu') or '',
        'ram': info.get('ram') or '',
        'disk': info.get('disk') or '',
        'ip': ip,
    }
