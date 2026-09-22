import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job

print('RUNNING', nas_acl_job_running('apply_nas_acl_all'))
print('SPAWN', spawn_nas_acl_batch_job('apply_nas_acl_all'))
