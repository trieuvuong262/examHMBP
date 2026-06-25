#!/usr/bin/env python3
import paramiko, sqlite3, tempfile, os

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo_cat(path):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S cat {path} 2>/dev/null", timeout=120)
    return (o.read()+e.read()).decode(errors='replace')

print('=== share_right.map (07_SAN) ===')
content = sudo_cat('/usr/syno/etc/share_right.map')
for line in content.splitlines():
    if '07_SAN' in line or 'SX' in line or line.startswith('#'):
        print(line)

print('\n=== smb.share.conf (07_SAN) ===')
smb = sudo_cat('/etc/samba/smb.share.conf')
in_block = False
for line in smb.splitlines():
    if '07_SAN_XUAT' in line:
        in_block = True
    if in_block:
        print(line)
        if line.strip() == '' and in_block and '07_SAN' not in line:
            break

print('\n=== synoshare --help ===')
_, o, _ = c.exec_command(f"echo '{PW}' | sudo -S /usr/syno/sbin/synoshare --help 2>&1", timeout=60)
print((o.read()).decode(errors='replace')[:2000])

for cmd in [
    '/usr/syno/sbin/synoshare --get 07_SAN_XUAT',
    '/usr/syno/sbin/synoshare --get 07_SAN_XUAT permission',
    '/usr/syno/sbin/synoshare --enum ALL',
]:
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd} 2>&1", timeout=60)
    out = (o.read()+e.read()).decode(errors='replace')
    print(f'\n=== {cmd} ===')
    print(out[:3000])

# download synoshare.db and query
sftp = c.open_sftp()
local = tempfile.mktemp(suffix='.db')
try:
    # copy via sudo to tmp readable
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S cp /usr/syno/etc/synoshare.db /tmp/synoshare.db && sudo chmod 644 /tmp/synoshare.db", timeout=60)
    o.read(); e.read()
    sftp.get('/tmp/synoshare.db', local)
    conn = sqlite3.connect(local)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print('\n=== synoshare.db tables ===', tables)
    for t in tables:
        try:
            cur.execute(f'PRAGMA table_info({t})')
            cols = [r[1] for r in cur.fetchall()]
            print('table', t, cols)
            if any('share' in c.lower() or 'name' in c.lower() for c in cols):
                cur.execute(f"SELECT * FROM {t} LIMIT 3")
                print(' sample', cur.fetchall()[:3])
        except Exception as ex:
            print('err', t, ex)
    # search SX in all text columns
    for t in tables:
        cur.execute(f'PRAGMA table_info({t})')
        cols = [r[1] for r in cur.fetchall()]
        for col in cols:
            try:
                cur.execute(f"SELECT * FROM {t} WHERE CAST({col} AS TEXT) LIKE '%07_SAN%' OR CAST({col} AS TEXT) LIKE '%SX%' LIMIT 5")
                rows = cur.fetchall()
                if rows:
                    print(f'rows {t}.{col}:', rows[:5])
            except Exception:
                pass
    conn.close()
finally:
    if os.path.exists(local):
        os.remove(local)
    sftp.close()
c.close()
