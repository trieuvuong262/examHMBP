# -*- coding: utf-8 -*-
"""Tạo & hoàn thành demo giao việc cá nhân: Vuonglnt → long.tb."""
import os
from datetime import timedelta

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone

from tasks.models import WorkTask, WorkTaskLog
from tasks.utils import log_task_action

MGR_USER = 'Vuonglnt'
EMP_USER = 'long.tb'
TITLE = 'setup fleetd-base trên VPS'


def main():
    mgr = User.objects.get(username=MGR_USER)
    emp = User.objects.get(username=EMP_USER)
    today = timezone.localdate()
    due = today + timedelta(days=15)

    # Huỷ các bản demo chưa xong cùng tiêu đề
    open_qs = WorkTask.objects.filter(
        project__isnull=True,
        assigner=mgr,
        assignee=emp,
        title__icontains='fleetd-base',
    ).exclude(
        status__in=[
            WorkTask.STATUS_COMPLETED,
            WorkTask.STATUS_CANCELLED,
            WorkTask.STATUS_REASSIGNED,
        ],
    )
    for t in open_qs:
        if t.status == WorkTask.STATUS_PENDING_REVIEW:
            # hoàn tất bản đang chờ duyệt nếu có
            continue
        t.status = WorkTask.STATUS_CANCELLED
        t.save(update_fields=['status', 'updated_at'])
        log_task_action(t, mgr, WorkTaskLog.ACTION_CANCEL, 'Huỷ bản demo cũ')

    pending = WorkTask.objects.filter(
        project__isnull=True,
        assigner=mgr,
        assignee=emp,
        title__icontains='fleetd-base',
        status=WorkTask.STATUS_PENDING_REVIEW,
    ).order_by('-pk').first()

    if pending:
        task = pending
    else:
        task = WorkTask.objects.create(
            title=TITLE,
            description=(
                'Cài đặt và cấu hình fleetd-base trên VPS.\n'
                '- Kiểm tra OS/SSH\n'
                '- Cài fleetd-base\n'
                '- Cấu hình dịch vụ và xác nhận chạy OK\n'
                f'Thời hạn thực hiện: 15 ngày (hạn đến {due.strftime("%d/%m/%Y")}).'
            ),
            task_type=WorkTask.TYPE_GENERAL,
            priority=WorkTask.PRIORITY_HIGH,
            assigner=mgr,
            assignee=emp,
            due_date=due,
            status=WorkTask.STATUS_PENDING_ACK,
            skip_completion_review=False,
        )
        log_task_action(task, mgr, WorkTaskLog.ACTION_ASSIGNED, 'Demo hướng dẫn — giao việc cá nhân')

        task.status = WorkTask.STATUS_IN_PROGRESS
        task.acknowledged_at = timezone.now()
        task.save(update_fields=['status', 'acknowledged_at', 'updated_at'])
        log_task_action(task, emp, WorkTaskLog.ACTION_ACK, 'Xác nhận nhận việc')

        task.progress_percent = 50
        task.result_note = 'Đã SSH vào VPS, đang cài fleetd-base.'
        task.save(update_fields=['progress_percent', 'result_note', 'updated_at'])
        log_task_action(task, emp, WorkTaskLog.ACTION_PROGRESS, 'Tiến độ 50%')

        task.progress_percent = 100
        task.result_note = (
            f'Hoàn tất setup fleetd-base trên VPS ngày {today.strftime("%d/%m/%Y")}.\n'
            '- Dịch vụ fleetd-base đang chạy\n'
            '- Đã kiểm tra health/basic check OK'
        )
        task.submitted_at = timezone.now()
        task.status = WorkTask.STATUS_PENDING_REVIEW
        task.save(update_fields=[
            'progress_percent', 'result_note', 'submitted_at', 'status', 'updated_at',
        ])
        log_task_action(task, emp, WorkTaskLog.ACTION_SUBMIT, 'Nộp chờ duyệt')

    # Chuẩn hoá tiêu đề/mô tả + duyệt hoàn thành hôm nay
    task.title = TITLE
    task.due_date = due
    task.description = (
        'Cài đặt và cấu hình fleetd-base trên VPS.\n'
        '- Kiểm tra OS/SSH\n'
        '- Cài fleetd-base\n'
        '- Cấu hình dịch vụ và xác nhận chạy OK\n'
        f'Thời hạn thực hiện: 15 ngày (hạn đến {due.strftime("%d/%m/%Y")}).'
    )
    task.status = WorkTask.STATUS_COMPLETED
    task.review_note = 'Đã kiểm tra — fleetd-base OK trên VPS. Duyệt hoàn thành trong ngày.'
    task.completed_at = timezone.now()
    task.progress_percent = 100
    task.save(update_fields=[
        'title', 'description', 'due_date', 'status', 'review_note',
        'completed_at', 'progress_percent', 'updated_at',
    ])
    if not task.logs.filter(action=WorkTaskLog.ACTION_APPROVE).exists():
        log_task_action(task, mgr, WorkTaskLog.ACTION_APPROVE, task.review_note)

    task.refresh_from_db()
    print(f'OK pk={task.pk} status={task.status}')
    print(f'title={task.title}')
    print(f'due={task.due_date} completed={task.completed_at}')
    print(f'{task.assigner.username} -> {task.assignee.username}')
    for log in task.logs.order_by('created_at'):
        actor = log.actor.username if log.actor else '-'
        print(f'  {log.created_at:%Y-%m-%d %H:%M} {log.action:12} {actor}')


if __name__ == '__main__':
    main()
