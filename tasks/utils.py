from .models import WorkTaskLog


def log_task_action(task, actor, action, message=''):
    WorkTaskLog.objects.create(
        task=task,
        actor=actor,
        action=action,
        message=message or '',
    )
