from django.contrib.auth.models import User
from django.utils import timezone
from audit.login_security import unlock_ip_block
from audit.models import IpLoginBlock

admin = User.objects.filter(is_superuser=True).first()
now = timezone.now()
qs = list(
    IpLoginBlock.objects.filter(blocked_at__isnull=False, unlocked_at__isnull=True).order_by("-blocked_at")[:30]
)
print("BLOCKED_COUNT", len(qs))
for row in qs:
    print("IP", row.ip_address, "at", row.blocked_at, "sample", (row.sample_usernames or [])[:3])

targets = {"127.0.0.1", "::1", "103.90.224.203"}
for row in IpLoginBlock.objects.filter(ip_address__in=targets, blocked_at__isnull=False):
    unlock_ip_block(block=row, admin_user=admin)
    print("UNLOCKED", row.ip_address)
print("UNLOCK_DONE")
