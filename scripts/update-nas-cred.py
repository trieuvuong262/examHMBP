#!/usr/bin/env python3
"""Cập nhật /root/.nas-cred và rclone remote (chạy trên VPS)."""
import subprocess
import sys

if len(sys.argv) != 2:
    print('Usage: update-nas-cred.py PASSWORD', file=sys.stderr)
    sys.exit(1)

password = sys.argv[1]
username = 'tailscale-justplay'

cred = f'username={username}\npassword={password}\ndomain=\n'
with open('/root/.nas-cred', 'w', encoding='utf-8') as f:
    f.write(cred)

subprocess.run(['chmod', '600', '/root/.nas-cred'], check=True)

obscured = subprocess.check_output(['rclone', 'obscure', password], text=True).strip()
subprocess.run(['rclone', 'config', 'delete', 'synology'], capture_output=True)
subprocess.run([
    'rclone', 'config', 'create', 'synology', 'smb',
    'host', '100.93.5.42',
    'user', username,
    'pass', obscured,
], check=True)

subprocess.run(['systemctl', 'restart', 'rclone-nas.service'], check=False)
print('OK: cred + rclone updated')
