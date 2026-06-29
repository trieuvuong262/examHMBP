"""Tự động đồng bộ Portal + NAS khi lưu ACL thư mục riêng theo user."""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='nas_storage.NasUserFolderAcl')
def nas_user_folder_acl_saved(sender, instance, **kwargs):
    from nas_storage.user_folders import sync_user_folder_acl_grant

    sync_user_folder_acl_grant(instance)


@receiver(post_delete, sender='nas_storage.NasUserFolderAcl')
def nas_user_folder_acl_deleted(sender, instance, **kwargs):
    from nas_storage.nas_acl_apply import NasAclApplyError, nas_acl_ssh_configured, revoke_user_folder_acl

    if not nas_acl_ssh_configured():
        return
    try:
        revoke_user_folder_acl(instance)
    except NasAclApplyError:
        logger.exception('Không gỡ ACL NAS sau khi xóa %s', instance)
