"""Phân tích nhật ký spam trên VPS — chạy trong container web."""
from collections import Counter
from datetime import datetime

from django.db.models import Count
from django.utils import timezone

from audit.models import UserActivityLog

start = timezone.make_aware(datetime(2026, 6, 9, 17, 39, 14))
end = timezone.now()
qs = UserActivityLog.objects.filter(created_at__gte=start, created_at__lte=end)
print(f"RANGE {start} -> {end}")
print(f"TOTAL_LOGS {qs.count()}")

lf = qs.filter(action=UserActivityLog.ACTION_LOGIN_FAILED)
print(f"LOGIN_FAILED {lf.count()}")

print("TOP_IPS_LOGIN_FAILED")
for row in lf.values("ip_address").annotate(c=Count("id")).order_by("-c")[:25]:
    print(f"  {row['ip_address'] or '?'}: {row['c']}")

# POST khác /login với field lạ
other = qs.filter(method="POST").exclude(path__icontains="login")
print(f"POST_NON_LOGIN {other.count()}")

field_counter: Counter = Counter()
ip_field_ips: dict[str, set] = {}
for log in other.iterator(chunk_size=500):
    body = (log.request_data or {}).get("body") or {}
    if not body:
        continue
    keys = set(body.keys())
    strange = keys - {
        "csrfmiddlewaretoken",
        "username",
        "password",
        "next",
        "remember",
        "email",
        "q",
        "search",
        "page",
        "tab",
        "sort",
        "dir",
        "department",
        "division",
        "status",
        "position",
        "_method",
    }
    if strange:
        ip = log.ip_address or "?"
        field_counter.update(strange)
        ip_field_ips.setdefault(ip, set()).update(strange)

print("STRANGE_FIELD_KEYS (top)")
for key, cnt in field_counter.most_common(30):
    print(f"  {key}: {cnt}")

print("IPS_WITH_STRANGE_FIELDS")
for ip, keys in sorted(ip_field_ips.items(), key=lambda x: -len(x[1]))[:25]:
    print(f"  {ip}: {sorted(keys)[:12]}")

print("SAMPLE_STRANGE_LOGS")
shown = 0
for log in other.order_by("-created_at").iterator(chunk_size=200):
    body = (log.request_data or {}).get("body") or {}
    keys = set(body.keys())
    strange = keys - {
        "csrfmiddlewaretoken", "username", "password", "next", "remember",
        "email", "q", "search", "page", "tab", "sort", "dir",
        "department", "division", "status", "position", "_method",
    }
    if not strange and log.action != UserActivityLog.ACTION_LOGIN_FAILED:
        continue
    if log.action == UserActivityLog.ACTION_LOGIN_FAILED:
        continue
    print(
        f"  {log.created_at:%Y-%m-%d %H:%M:%S} | {log.ip_address} | {log.path} | "
        f"keys={sorted(keys)[:8]} | user={log.username or '-'}"
    )
    shown += 1
    if shown >= 20:
        break

print("SAMPLE_LOGIN_FAILED_USERNAMES")
for log in lf.order_by("-created_at")[:20]:
    uname = log.username or (log.request_data or {}).get("body", {}).get("username", "")
    print(f"  {log.created_at:%Y-%m-%d %H:%M:%S} | {log.ip_address} | [{uname}]")
