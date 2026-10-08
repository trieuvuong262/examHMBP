"""Nhắc việc sắp đến hạn / đã quá hạn (thông báo trong portal). Chạy định kỳ, ví dụ mỗi 30 phút."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from thiet_ke_sp.models import Status, Task
from thiet_ke_sp.permissions import display_name
from thiet_ke_sp.services import notify as nt
from thiet_ke_sp.services.workflow import _fmt_due

SKIP_STATUSES = (Status.PAUSED, Status.CANCELLED, Status.CLOSED)


class Command(BaseCommand):
    help = 'Gửi thông báo trong portal cho công việc thiết kế sản phẩm sắp đến hạn (24 giờ) và quá hạn.'

    def handle(self, *args, **options):
        now = timezone.now()
        base = Task.objects.filter(state=Task.STATE_OPEN, due_at__isnull=False).exclude(
            dossier__status__in=SKIP_STATUSES,
        ).select_related('dossier', 'dossier__owner', 'assignee')

        soon_count = 0
        for task in base.filter(due_at__gte=now, due_at__lt=now + timedelta(hours=24), due_soon_notified_at__isnull=True):
            nt.notify(task.assignee, task.dossier, nt.KIND_DUE_SOON, f'Sắp đến hạn: {task.title}',
                      f'{task.dossier.code} — hạn {_fmt_due(task.due_at)}')
            task.due_soon_notified_at = now
            task.save(update_fields=['due_soon_notified_at'])
            soon_count += 1

        late_count = 0
        for task in base.filter(due_at__lt=now, overdue_notified_at__isnull=True):
            body = f'{task.dossier.code} — hạn {_fmt_due(task.due_at)}'
            nt.notify(task.assignee, task.dossier, nt.KIND_OVERDUE, f'Quá hạn: {task.title}', body)
            owner = task.dossier.owner
            if owner and owner != task.assignee:
                nt.notify(owner, task.dossier, nt.KIND_OVERDUE,
                          f'Quá hạn: {task.title} ({display_name(task.assignee) or "chưa giao"})', body)
            task.overdue_notified_at = now
            task.save(update_fields=['overdue_notified_at'])
            late_count += 1

        self.stdout.write(self.style.SUCCESS(f'Đã nhắc {soon_count} việc sắp đến hạn, {late_count} việc quá hạn.'))
