"""Đồng bộ thư viện công đoạn IE + SxProcessName từ mẫu progress_template."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError

from san_xuat.ie_models import SxOperation, SxOperationGroup, SxProcessStage
from san_xuat.services.process_catalog import ensure_process_name
from san_xuat.services.progress_template import (
    GROUPS,
    WC_SEED,
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
    """Upsert SxProcessStage / SxOperationGroup / SxOperation / SxProcessName từ mẫu.

    - op_code = KEY viết hoa (vd. MAY_RAP_VAI)
    - name_vi = nhãn chuẩn
    - status = approved
    - purge_missing: xoá mọi OP không còn trong mẫu (fallback retire nếu bị PROTECT)
    - retire_missing: chỉ đánh dấu retired (không xoá)
    """
    from san_xuat.models import SxProcessName
    from san_xuat.services.order_progress_sheet import ensure_progress_work_centers

    ensure_progress_work_centers()

    stats = {
        'stages': 0,
        'groups': 0,
        'ops_created': 0,
        'ops_updated': 0,
        'ops_retired': 0,
        'ops_deleted': 0,
        'process_names': 0,
        'process_names_deactivated': 0,
    }

    group_by_key: dict[str, SxOperationGroup] = {}
    for i, grp in enumerate(GROUPS):
        code, stage_code = _GROUP_META[grp.key]
        stage = _ensure_stage(stage_code, grp.label, sort_order=(i + 1) * 10)
        stats['stages'] += 1
        wc_code = grp.work_center_code
        # Prefer WC_SEED display name for group name short form
        wc_name = next((n for c, n, _t in WC_SEED if c == wc_code), grp.label)
        og = _ensure_group(
            code=code,
            name=wc_name,
            stage=stage,
            wc_code=wc_code,
            sort_order=(i + 1) * 10,
        )
        group_by_key[grp.key] = og
        stats['groups'] += 1

    keep_codes: set[str] = set()
    keep_labels: set[str] = set()
    for step in progress_steps():
        og = group_by_key[step.group]
        op_code = step.key.upper()
        keep_codes.add(op_code)
        keep_labels.add(step.label.casefold())
        stage_label = next((g.label for g in GROUPS if g.key == step.group), '')
        defaults = {
            'group': og,
            'name_vi': step.label[:200],
            'process_stage_label': stage_label[:100],
            'base_smv_min': Decimal('0'),
            'status': SxOperation.STATUS_APPROVED,
            'notes': 'Đồng bộ từ mẫu công đoạn chuẩn',
            'revision_reason': 'Sync progress template',
        }
        op = (
            SxOperation.objects.filter(op_code=op_code)
            .order_by('-updated_at', '-pk')
            .first()
        )
        if op is None:
            SxOperation.objects.create(op_code=op_code, op_rev='R01', **defaults)
            stats['ops_created'] += 1
        else:
            changed = False
            for field, value in defaults.items():
                if getattr(op, field) != value:
                    setattr(op, field, value)
                    changed = True
            if changed:
                op.save()
                stats['ops_updated'] += 1
            # Xoá bản trùng cùng op_code (rev khác)
            extras = SxOperation.objects.filter(op_code=op_code).exclude(pk=op.pk)
            if extras.exists():
                if purge_missing:
                    deleted, _ = extras.delete()
                    stats['ops_deleted'] += deleted
                else:
                    stats['ops_retired'] += extras.exclude(
                        status=SxOperation.STATUS_RETIRED,
                    ).update(status=SxOperation.STATUS_RETIRED)

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

    return stats
