"""Chặn IP spam đã thấy trên log VPS 09–10/06/2026."""
from audit.login_security import block_ip_for_form_spam, is_ip_blocked

SPAM_IPS = (
    '34.31.88.250',
    '45.198.224.22',
)

for ip in SPAM_IPS:
    block_ip_for_form_spam(ip, sample_fields=['manual-vps-audit'])
    print(ip, 'blocked=', is_ip_blocked(ip))
