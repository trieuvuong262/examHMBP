from __future__ import annotations

import calendar
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from .models import WorkTask, WorkTaskLog, WorkTaskRecurrence

OPEN_RECURRENCE_STATUSES = {
    WorkTask.STATUS_PENDING_ACK,
    WorkTask.STATUS_IN_PROGRESS,
    WorkTask.STATUS_PENDING_REVIEW,
    WorkTask.STATUS_REVISION,
}


def compute_next_run_date(recurrence: WorkTaskRecurrence, after_date: date) -> date:
    interval = max(recurrence.interval, 1)
    frequency = recurrence.frequency

    if frequency == WorkTaskRecurrence.FREQ_DAILY:
        return after_date + timedelta(days=interval)

    if frequency == WorkTaskRecurrence.FREQ_WEEKLY:
        weekday = recurrence.weekday if recurrence.weekday is not None else after_date.weekday()
        candidate = after_date + timedelta(days=1)
        limit = after_date + timedelta(days=7 * interval + 14)
        while candidate <= limit:
            if candidate.weekday() == weekday:
                week_index = (candidate - recurrence.start_date).days // 7
                if week_index >= 0 and week_index % interval == 0:
                    return candidate
            candidate += timedelta(days=1)
        return after_date + timedelta(weeks=interval)

    target_month = after_date + relativedelta(months=interval)
    day = recurrence.day_of_month or after_date.day
    last_day = calendar.monthrange(target_month.year, target_month.month)[1]
    day = min(day, last_day)
    return target_month.replace(day=day)


def compute_task_due_date(recurrence: WorkTaskRecurrence, run_date: date) -> date | None:
    if recurrence.due_offset_days is None:
        return None
    return run_date + timedelta(days=recurrence.due_offset_days)


def has_open_recurrence_instance(recurrence: WorkTaskRecurrence) -> bool:
    return recurrence.instances.filter(status__in=OPEN_RECURRENCE_STATUSES).exists()


def spawn_task_from_recurrence(
    recurrence: WorkTaskRecurrence,
    *,
    run_date: date,
    actor,
    copy_attachments: bool = True,
) -> WorkTask | None:
    from .attachment_utils import copy_recurrence_attachments_to_task
    from .utils import log_task_action

    if not recurrence.is_active:
        return None
    if recurrence.end_date and run_date > recurrence.end_date:
        return None
    if has_open_recurrence_instance(recurrence):
        return None

    task = WorkTask.objects.create(
        title=recurrence.title,
        description=recurrence.description,
        task_type=recurrence.task_type,
        priority=recurrence.priority,
        skip_completion_review=recurrence.skip_completion_review,
        assigner=recurrence.assigner,
        assignee=recurrence.assignee,
        due_date=compute_task_due_date(recurrence, run_date),
        recurrence=recurrence,
    )
    if copy_attachments:
        copy_recurrence_attachments_to_task(recurrence, task, uploaded_by=actor)
    log_task_action(
        task,
        actor,
        WorkTaskLog.ACTION_ASSIGNED,
        f'Tự động lặp — chu kỳ #{recurrence.pk}',
    )
    return task


def create_recurrence_and_first_task(
    *,
    assigner,
    assignee,
    title,
    description,
    task_type,
    priority,
    skip_completion_review,
    frequency,
    interval,
    weekday,
    day_of_month,
    end_date,
    due_date,
    run_date: date | None = None,
    prepared_files=None,
    actor=None,
) -> tuple[WorkTaskRecurrence, WorkTask]:
    from .attachment_utils import save_recurrence_attachments

    run_date = run_date or timezone.localdate()
    due_offset = None
    if due_date is not None:
        due_offset = max((due_date - run_date).days, 0)

    recurrence = WorkTaskRecurrence.objects.create(
        assigner=assigner,
        assignee=assignee,
        title=title,
        description=description,
        task_type=task_type,
        priority=priority,
        skip_completion_review=skip_completion_review,
        frequency=frequency,
        interval=max(interval, 1),
        weekday=weekday,
        day_of_month=day_of_month,
        due_offset_days=due_offset,
        start_date=run_date,
        end_date=end_date,
        next_run_date=run_date,
        is_active=True,
    )

    if prepared_files:
        save_recurrence_attachments(recurrence, prepared_files, uploaded_by=actor or assigner)

    actor = actor or assigner
    task = spawn_task_from_recurrence(recurrence, run_date=run_date, actor=actor)
    recurrence.next_run_date = compute_next_run_date(recurrence, run_date)
    recurrence.last_generated_at = timezone.now()
    recurrence.save(update_fields=['next_run_date', 'last_generated_at', 'updated_at'])
    return recurrence, task


@transaction.atomic
def process_due_recurrences(*, for_date: date | None = None) -> int:
    today = for_date or timezone.localdate()
    created = 0

    recurrences = (
        WorkTaskRecurrence.objects.filter(is_active=True, next_run_date__lte=today)
        .select_for_update()
        .select_related('assigner', 'assignee')
    )

    for recurrence in recurrences:
        if recurrence.end_date and recurrence.end_date < today:
            recurrence.is_active = False
            recurrence.save(update_fields=['is_active', 'updated_at'])
            continue

        run_date = recurrence.next_run_date
        while run_date <= today:
            if recurrence.end_date and run_date > recurrence.end_date:
                recurrence.is_active = False
                recurrence.save(update_fields=['is_active', 'updated_at'])
                break

            if has_open_recurrence_instance(recurrence):
                break

            task = spawn_task_from_recurrence(
                recurrence,
                run_date=run_date,
                actor=recurrence.assigner,
            )
            if not task:
                break

            created += 1
            recurrence.last_generated_at = timezone.now()
            run_date = compute_next_run_date(recurrence, run_date)
            recurrence.next_run_date = run_date
            recurrence.save(update_fields=['next_run_date', 'last_generated_at', 'updated_at'])

    return created
