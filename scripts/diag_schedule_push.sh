#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay

echo "=== dry-run ==="
docker compose exec -T web python manage.py send_schedule_reminder_pushes --dry-run

echo "=== cron ==="
crontab -l 2>/dev/null | grep -i schedule || echo "NO_SCHEDULE_CRON"

echo "=== reminders & subs ==="
docker compose exec -T web python manage.py shell <<'PY'
from django.utils import timezone
from utilities.models import ScheduleReminder, MealPushSubscription, ScheduleReminderPushLog
from utilities.schedule_reminder_logic import should_fire_reminder
from utilities.push_service import webpush_configured

now = timezone.localtime()
print("webpush_configured:", webpush_configured())
print("now:", now)
print("active_reminders:", ScheduleReminder.objects.filter(is_active=True).count())
print("push_subscriptions:", MealPushSubscription.objects.count())
for r in ScheduleReminder.objects.filter(is_active=True).select_related("user")[:15]:
    fire = should_fire_reminder(r, now)
    subs = MealPushSubscription.objects.filter(user=r.user).count()
    print(
        f"  id={r.pk} user={r.user.username} mode={r.repeat_mode} "
        f"time={r.remind_time} wd={r.weekdays} once={r.once_date} "
        f"fire_now={fire} subs={subs}"
    )
print("push_logs_today:", ScheduleReminderPushLog.objects.filter(fire_date=now.date()).count())
PY

echo "=== recent log ==="
tail -20 /var/log/portal-schedule-reminder-push.log 2>/dev/null || echo "no log file"
