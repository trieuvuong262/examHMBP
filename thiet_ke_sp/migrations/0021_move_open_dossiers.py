from django.db import migrations
from django.utils import timezone


def _due(status):
    from thiet_ke_sp.services.sla import due_at_for
    return due_at_for(status)


def _close_open_tasks(Task, dossier_id, step, actor_id, now):
    base = Task.objects.filter(
        dossier_id=dossier_id, step=step, state='open',
        receipt__isnull=True, condition__isnull=True, evaluation__isnull=True,
    )
    base.filter(is_main=True).update(state='done', completed_at=now, completed_by_id=actor_id)
    base.filter(is_main=False).update(state='cancelled', completed_at=now)


def _open_task(Task, dossier_id, step, role, title, assignee_id, due_at, is_main=True):
    if assignee_id is None and not is_main:
        return
    Task.objects.create(
        dossier_id=dossier_id, step=step, role=role, title=title, is_main=is_main,
        assignee_id=assignee_id, due_at=due_at, state='open',
    )


def _move(Task, AuditLog, dossier, new_status, actor_id, action, summary, tasks):
    now = timezone.now()
    old = dossier.status
    _close_open_tasks(Task, dossier.pk, old, actor_id, now)
    dossier.status = new_status
    dossier.status_changed_at = now
    dossier.save(update_fields=['status', 'status_changed_at'])
    AuditLog.objects.create(
        dossier_id=dossier.pk, actor_id=actor_id, action=action, summary=summary,
        from_status=old, to_status=new_status,
    )
    for role, title, assignee_id, due_at, is_main in tasks:
        _open_task(Task, dossier.pk, new_status, role, title, assignee_id, due_at, is_main)


def move_open_dossiers(apps, schema_editor):
    # Model lịch sử của 0020: chưa có co_designer và các cột thêm sau này.
    ProductDevelopment = apps.get_model('thiet_ke_sp', 'ProductDevelopment')
    DesignVersion = apps.get_model('thiet_ke_sp', 'DesignVersion')
    Task = apps.get_model('thiet_ke_sp', 'Task')
    AuditLog = apps.get_model('thiet_ke_sp', 'AuditLog')

    for dossier in ProductDevelopment.objects.filter(status='brief_pending'):
        if not DesignVersion.objects.filter(dossier_id=dossier.pk).exists():
            DesignVersion.objects.create(
                dossier_id=dossier.pk, version_no=1, option_no=1, created_by_id=dossier.proposer_id,
            )
        _move(
            Task, AuditLog, dossier, 'designing', dossier.proposer_id, 'brief_skipped',
            'Bỏ bước duyệt đề bài — chuyển sang thiết kế.',
            [('designer', 'Thiết kế phiên bản', dossier.designer_id or dossier.owner_id, _due('designing'), True)],
        )
    for dossier in ProductDevelopment.objects.filter(status='master_pending'):
        tasks = [('approver', 'Duyệt thiết kế', dossier.approver_id, _due('sample_eval_pending'), True)]
        if dossier.costing_user_id:
            tasks.append((
                'costing_user', 'Đánh giá giá thành mẫu', dossier.costing_user_id,
                _due('sample_eval_pending'), False,
            ))
        _move(
            Task, AuditLog, dossier, 'sample_eval_pending', dossier.approver_id or dossier.proposer_id,
            'step_merged', 'Gộp duyệt mẫu chuẩn vào bước Duyệt thiết kế.', tasks,
        )
    Task.objects.filter(step='handed_over', state='open').update(
        state='cancelled', completed_at=timezone.now(),
    )


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0020_workflow_five_steps'),
    ]

    operations = [
        migrations.RunPython(move_open_dossiers, noop),
    ]
