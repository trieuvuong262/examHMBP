"""Đồng bộ thư viện công đoạn IE + SxProcessName từ mẫu progress_template."""

from __future__ import annotations

from django.db import transaction
from django.db.models import ProtectedError

from san_xuat.ie_models import SxOperation, SxOperationGroup, SxProcessStage
from san_xuat.services.process_catalog import ensure_process_name
from san_xuat.services.progress_template import (
    GROUPS,
    progress_steps,
)


_GROUP_META: dict[str, tuple[str, str]] = {
    # group_key → (group_code, stage_code)
    'CAT': ('CAT', 'CAT'),
    'IN_EP': ('IN_EP', 'IN_EP'),
    'THEU': ('THEU', 'THEU'),
    'MAY': ('MAY', 'MAY'),
    'HOAN_THANH': ('HT', 'HT'),
    'GIAO_HANG': ('GH', 'GH'),
}


def _ensure_stage(code: str, name: str, sort_order: int) -> SxProcessStage:
    stage, created = SxProcessStage.objects.get_or_create(
        code=code,
        defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
    )
    if not created:
        fields: list[str] = []
        if stage.name != name:
            stage.name = name
            fields.append('name')
        if stage.sort_order != sort_order:
            stage.sort_order = sort_order
            fields.append('sort_order')
        if not stage.is_active:
            stage.is_active = True
            fields.append('is_active')
        if fields:
            stage.save(update_fields=fields)
    return stage


def _ensure_group(
    *,
    code: str,
    name: str,
    stage: SxProcessStage,
    wc_code: str,
    sort_order: int,
) -> SxOperationGroup:
    group, created = SxOperationGroup.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'process_stage': stage,
            'process_stage_label': name,
            'default_work_center_code': wc_code,
            'sort_order': sort_order,
            'is_active': True,
            'notes': 'Đồng bộ từ mẫu công đoạn chuẩn',
        },
    )
    if not created:
        fields: list[str] = []
        if group.name != name:
            group.name = name
            fields.append('name')
        if group.process_stage_id != stage.pk:
            group.process_stage = stage
            fields.append('process_stage')
        if (group.process_stage_label or '') != name:
            group.process_stage_label = name
            fields.append('process_stage_label')
        if (group.default_work_center_code or '') != wc_code:
            group.default_work_center_code = wc_code
            fields.append('default_work_center_code')
        if group.sort_order != sort_order:
            group.sort_order = sort_order
            fields.append('sort_order')
        if not group.is_active:
            group.is_active = True
            fields.append('is_active')
        if fields:
            group.save(update_fields=fields)
    return group


@transaction.atomic
def sync_standard_process_library(
    *,
    retire_missing: bool = False,
    purge_missing: bool = False,
) -> dict[str, int]:
    """Đồng bộ tên CĐ + tổ chuẩn cho tiến độ tổ.

    Không tạo/sửa ``SxOperation`` hay ``SxOperationGroup`` — thư viện IE tự quản
    (màn nhóm công đoạn / import Excel). Deploy không được tái tạo nhóm đã xóa.
    ``purge_missing`` / ``retire_missing`` chỉ áp dụng khi gọi chủ động với cờ đó.
    """
    from san_xuat.models import SxProcessName
    from san_xuat.services.order_progress_sheet import ensure_progress_work_centers

    ensure_progress_work_centers()

    stats = {
        'stages': 0,
        'groups': 0,
        'groups_deactivated': 0,
        'stages_deactivated': 0,
        'ops_created': 0,
        'ops_updated': 0,
        'ops_retired': 0,
        'ops_deleted': 0,
        'process_names': 0,
        'process_names_deactivated': 0,
        'work_centers_deactivated': 0,
    }

    # Nhóm công đoạn (SxOperationGroup) do IE tự quản trên /cong-doan/nhom/
    # hoặc import Excel — không seed/tái tạo khi deploy, kẻo nhóm đã xóa hiện lại.
    keep_group_codes: set[str] = set()
    keep_stage_codes: set[str] = set()
    for grp in GROUPS:
        code, stage_code = _GROUP_META[grp.key]
        keep_group_codes.add(code)
        keep_stage_codes.add(stage_code)

    keep_codes: set[str] = set()
    keep_labels: set[str] = set()
    for step in progress_steps():
        keep_codes.add(step.key.upper())
        keep_labels.add(step.label.casefold())
        # Không tạo/sửa SxOperation thư viện IE — thư viện do IE import Excel quản lý.
        ensure_process_name(step.label)
        stats['process_names'] += 1

    if purge_missing or retire_missing:
        stale = SxOperation.objects.exclude(op_code__in=keep_codes)
        if purge_missing:
            for op in list(stale):
                try:
                    op.delete()
                    stats['ops_deleted'] += 1
                except ProtectedError:
                    if op.status != SxOperation.STATUS_RETIRED:
                        op.status = SxOperation.STATUS_RETIRED
                        op.save(update_fields=['status'])
                        stats['ops_retired'] += 1
        else:
            stats['ops_retired'] += stale.exclude(
                status=SxOperation.STATUS_RETIRED,
            ).update(status=SxOperation.STATUS_RETIRED)

        # Tắt tên CD legacy không còn trong mẫu
        for pn in SxProcessName.objects.filter(is_active=True):
            if (pn.name or '').strip().casefold() not in keep_labels:
                pn.is_active = False
                pn.save(update_fields=['is_active'])
                stats['process_names_deactivated'] += 1

        # Chỉ giữ 6 nhóm chuẩn — tắt nhóm / khâu thừa
        stale_groups = SxOperationGroup.objects.exclude(code__in=keep_group_codes)
        for g in stale_groups:
            if purge_missing and not g.operations.exists():
                g.delete()
                stats['groups_deactivated'] += 1
            elif g.is_active:
                g.is_active = False
                g.save(update_fields=['is_active'])
                stats['groups_deactivated'] += 1

        stale_stages = SxProcessStage.objects.exclude(code__in=keep_stage_codes)
        for st in stale_stages:
            if purge_missing and not st.operation_groups.exists():
                st.delete()
                stats['stages_deactivated'] += 1
            elif st.is_active:
                st.is_active = False
                st.save(update_fields=['is_active'])
                stats['stages_deactivated'] += 1

        # Năng lực SX: chỉ giữ 6 tổ chuẩn đang dùng
        from san_xuat.hub_models import SxWorkCenter
        from san_xuat.services.progress_template import standard_work_center_codes

        ensure_progress_work_centers(deactivate_others=False)
        stale_wc = SxWorkCenter.objects.filter(is_demo=False, is_active=True).exclude(
            code__in=standard_work_center_codes(),
        )
        stats['work_centers_deactivated'] = stale_wc.update(is_active=False)

    return stats
