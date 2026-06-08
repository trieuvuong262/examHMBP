#!/usr/bin/env bash
# Harden VPS: fail2ban (sshd) + SSH key-only + đóng Metabase public.
# Chạy trên VPS: bash scripts/vps-harden-security.sh
set -euo pipefail

echo "==> [1/4] Cài fail2ban"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq fail2ban

cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
banaction = iptables-multiport

[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 4
bantime  = 24h
EOF

systemctl enable fail2ban
systemctl start fail2ban
sleep 2
systemctl restart fail2ban
fail2ban-client status sshd 2>/dev/null || fail2ban-client status 2>/dev/null || true

echo "==> [2/4] SSH: chỉ publickey, root prohibit-password"
# File chính và cloud-init ghi đè Include — sửa trực tiếp
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
if [[ -f /etc/ssh/sshd_config.d/50-cloud-init.conf ]]; then
  sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config.d/50-cloud-init.conf
fi

cat > /etc/ssh/sshd_config.d/99-portal-hardening.conf <<'EOF'
# PortalJustPlay — hardening (override cloud-init)
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 4
LoginGraceTime 30
EOF

sshd -t
systemctl reload ssh
echo "    ssh reloaded OK"
sshd -T | grep -E 'passwordauthentication|permittrootlogin|pubkeyauthentication' || true

echo "==> [3/4] Metabase: ngừng expose 0.0.0.0:3000"
if docker ps -a --format '{{.Names}}' | grep -q '^portaljustplay-metabase-1$'; then
  docker update --restart=no portaljustplay-metabase-1 2>/dev/null || true
  docker stop portaljustplay-metabase-1 2>/dev/null || true
  echo "    Đã stop portaljustplay-metabase-1 (truy cập sau: SSH tunnel -L 3000:127.0.0.1:3000)"
else
  echo "    Không thấy container metabase — bỏ qua"
fi

echo "==> [4/4] Kiểm tra port đang mở"
ss -tlnp | grep -E ':22|:80|:443|:3000|:5432' || true

echo "==> Hoàn tất hardening"
