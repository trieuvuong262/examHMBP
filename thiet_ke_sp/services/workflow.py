"""Luồng nghiệp vụ hồ sơ thiết kế sản phẩm.

Mọi thay đổi trạng thái đi qua module này để luôn: kiểm tra quyền + điều kiện chặn,
đóng/mở công việc theo bước, ghi nhật ký và gửi thông báo trong portal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from thiet_ke_sp import permissions as perms
from thiet_ke_sp.services.size_spec import filled_sizes
from thiet_ke_sp.models import (
    DOSSIER_ROLE_FIELDS,
    ROLE_PARTNER,
    APPROVER_DECIDE_STATUSES,
    DESIGN_APPROVAL_STATUSES,
    FINAL_STATUSES,
    IMAGE_EXTENSIONS,
    SINGLE_CURRENT_KINDS,
    Approval,
    ApprovalCondition,
    ApprovalDecision,
    ApprovalStage,
    Attachment,
    AttachmentKind,
    AuditLog,
    Colorway,
    Comment,
    DesignVersion,
    DossierMember,
    DossierSequence,
    EvaluationItem,
    EvaluatorRole,
    Handover,
    MaterialLine,
    MemberGroup,
    ProductDevelopment,
    Role,
    STEPS,
    SampleEvaluation,
    SampleVersion,
    Status,
    Task,
    TechnicalPack,
)
from thiet_ke_sp.services import notify as nt
from thiet_ke_sp.services import sla


class WorkflowError(Exception):
    """Thao tác bị chặn — message hiển thị thẳng cho người dùng."""


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def _require_text(value: str, label: str) -> str:
    text = (value or '').strip()
    _require(bool(text), f'Bắt buộc nhập {label}.')
    return text


def _name(user) -> str:
    return perms.display_name(user)


def log(dossier, actor, action: str, summary: str, *, from_status: str = '', to_status: str = '', **payload):
    return AuditLog.objects.create(
        dossier=dossier,
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        summary=summary,
        from_status=from_status,
        to_status=to_status,
        payload={k: v for k, v in payload.items() if v not in (None, '')},
    )


def next_code(year: int | None = None) -> str:
    year = year or timezone.localdate().year
    with transaction.atomic():
        seq, _ = DossierSequence.objects.select_for_update().get_or_create(year=year)
        seq.last_no += 1
        seq.save(update_fields=['last_no'])
        return f'PTSP-{year}-{seq.last_no:04d}'


def _fmt_due(due_at) -> str:
    return timezone.localtime(due_at).strftime('%H:%M %d/%m/%Y') if due_at else ''


# ---------------------------------------------------------------------------
# Công việc theo bước
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepTask:
    role: str
    title: str
    is_main: bool = True
    fallback_owner: bool = True


def design_scope_label(dossier: ProductDevelopment) -> str:
    dvs = dossier.current_design_versions()
    if len(dvs) > 1:
        return ', '.join(dv.tag for dv in dvs)
    return dvs[0].label if dvs else ''


def _step_tasks(dossier: ProductDevelopment, status: str) -> list[StepTask]:
    sv = dossier.current_sample_version()
    dv_label = design_scope_label(dossier)
    sv_label = sv.label if sv else ''
    mapping = {
        Status.BRIEF_PENDING: [StepTask(Role.APPROVER, 'Duyệt đề bài', fallback_owner=False)],
        Status.BRIEF_NEEDS_INFO: [StepTask(Role.PROPOSER, 'Bổ sung đề bài theo yêu cầu')],
        Status.DESIGNING: [StepTask(Role.DESIGNER, f'Thiết kế phiên bản {dv_label}')],
        Status.DESIGN_REVISE: [StepTask(Role.DESIGNER, f'Chỉnh thiết kế — phiên bản {dv_label}')],
        Status.DESIGN_PENDING: [StepTask(Role.APPROVER, f'Duyệt thiết kế {dv_label}', fallback_owner=False)],
        Status.TECHNICAL: [StepTask(Role.TECHNICIAN, 'Cập nhật rập, thông số kỹ thuật & BOM')],
        Status.TECHNICAL_REVISE: [StepTask(Role.TECHNICIAN, 'Chỉnh rập, thông số kỹ thuật & BOM')],
        Status.SAMPLING: [StepTask(Role.SAMPLE_MAKER, f'Làm mẫu {sv_label}')],
        Status.SAMPLE_REVISE: [StepTask(Role.SAMPLE_MAKER, f'Sửa mẫu — lần {sv_label}')],
        Status.SAMPLE_EVAL_PENDING: [
            StepTask(Role.APPROVER, f'Duyệt thiết kế {sv_label}', fallback_owner=False),
            StepTask(Role.COSTING, f'Đánh giá giá thành mẫu {sv_label}', is_main=False, fallback_owner=False),
        ],
        Status.MASTER_PENDING: [StepTask(Role.APPROVER, f'Duyệt thiết kế {sv_label}', fallback_owner=False)],
        Status.APPROVED: [StepTask(Role.OWNER, 'Thêm sản phẩm vào Thư viện')],
        Status.HANDED_OVER: [],
        Status.LIBRARY_REOPEN: [StepTask(Role.OWNER, 'Chỉnh công đoạn và gửi duyệt thiết kế')],
    }
    return mapping.get(status, [])


def _role_assignee(dossier: ProductDevelopment, role: str, fallback_owner: bool):
    if role == Role.PROPOSER:
        return dossier.proposer
    user = dossier.role_user(role)
    if user is None and fallback_owner:
        user = dossier.owner
    return user


def _owners(dossier: ProductDevelopment):
    people = []
    seen = set()
    for person in (dossier.owner, dossier.co_owner):
        if person is None or person.pk in seen:
            continue
        seen.add(person.pk)
        people.append(person)
    return people


def _task_notify_kind(role: str, revision: bool) -> str:
    if role == Role.APPROVER:
        return nt.KIND_APPROVAL_REQUEST
    return nt.KIND_REVISION if revision else nt.KIND_TASK


def _create_task(dossier, *, step, role, title, assignee, due_at, is_main=True, actor=None,
                 notify_kind=nt.KIND_TASK, receipt=None, condition=None, evaluation=None) -> Task:
    task = Task.objects.create(
        dossier=dossier, step=step, role=role, title=title, is_main=is_main,
        assignee=assignee, due_at=due_at, receipt=receipt, condition=condition, evaluation=evaluation,
    )
    if assignee is not None:
        body = f'{dossier.code} — {dossier.name}'
        if due_at:
            body += f' · Hạn {_fmt_due(due_at)}'
        nt.notify(assignee, dossier, notify_kind, title, body, actor=actor)
    return task


def open_step_tasks(dossier: ProductDevelopment, status: str, actor, *, due_at=None, revision=False) -> list[Task]:
    due_at = due_at or sla.due_at_for(status)
    created = []
    for spec in _step_tasks(dossier, status):
        assignee = _role_assignee(dossier, spec.role, spec.fallback_owner)
        if assignee is not None or spec.is_main:
            created.append(_create_task(
                dossier, step=status, role=spec.role, title=spec.title, assignee=assignee,
                due_at=due_at, is_main=spec.is_main, actor=actor,
                notify_kind=_task_notify_kind(spec.role, revision),
            ))
        partner_task = _open_partner_task(
            dossier, spec.role, actor=actor, due_at=due_at, revision=revision, title=spec.title,
        )
        if partner_task is not None:
            created.append(partner_task)
    return created


def backfill_partner_tasks() -> int:
    """Mở việc phụ cho người thứ hai trên hồ sơ đang chạy, nếu chưa có."""
    created = 0
    qs = ProductDevelopment.objects.exclude(status__in=(
        Status.DRAFT, Status.PAUSED, Status.CANCELLED, Status.CLOSED, Status.HANDED_OVER,
    ))
    for dossier in qs.iterator():
        for spec in _step_tasks(dossier, dossier.status):
            task = _open_partner_task(
                dossier, spec.role, actor=dossier.proposer,
                due_at=sla.due_at_for(dossier.status), revision=False, title=spec.title,
            )
            if task is not None:
                created += 1
    return created


def _open_partner_task(dossier, role: str, *, actor, due_at, revision: bool, title: str):
    """Việc phụ cho người thứ hai. Việc chính vẫn một người."""
    field = ROLE_PARTNER.get(role)
    partner = getattr(dossier, field, None) if field else None
    if partner is None:
        return None
    primary = _role_assignee(dossier, role, fallback_owner=True)
    if primary is not None and primary.pk == partner.pk:
        return None
    if dossier.tasks.filter(state=Task.STATE_OPEN, role=role, assignee=partner).exists():
        return None
    return _create_task(
        dossier, step=dossier.status, role=role, title=title, assignee=partner,
        due_at=due_at, is_main=False, actor=actor,
        notify_kind=_task_notify_kind(role, revision),
    )


def _close_step_tasks(dossier: ProductDevelopment, step: str, actor) -> None:
    now = timezone.now()
    open_tasks = dossier.tasks.filter(
        step=step, state=Task.STATE_OPEN, receipt__isnull=True, condition__isnull=True, evaluation__isnull=True,
    )
    affected = {t.assignee for t in open_tasks if t.assignee_id}
    open_tasks.filter(is_main=True).update(
        state=Task.STATE_DONE, completed_at=now, completed_by=actor if actor and actor.is_authenticated else None,
    )
    open_tasks.filter(is_main=False).update(state=Task.STATE_CANCELLED, completed_at=now)
    for user in affected:
        nt.invalidate_badges(user)


def _cancel_all_open_tasks(dossier: ProductDevelopment) -> None:
    open_tasks = dossier.tasks.filter(state=Task.STATE_OPEN)
    affected = {t.assignee for t in open_tasks if t.assignee_id}
    open_tasks.update(state=Task.STATE_CANCELLED, completed_at=timezone.now())
    for user in affected:
        nt.invalidate_badges(user)


def _complete_user_tasks(dossier, user, *, step: str, role: str) -> None:
    tasks = dossier.tasks.filter(step=step, role=role, state=Task.STATE_OPEN, assignee=user)
    if tasks.update(state=Task.STATE_DONE, completed_at=timezone.now(), completed_by=user):
        nt.invalidate_badges(user)


def _transition(dossier: ProductDevelopment, new_status: str, actor, action: str, summary: str,
                *, due_at=None, revision=False, open_tasks=True, **payload) -> None:
    old_status = dossier.status
    _close_step_tasks(dossier, old_status, actor)
    dossier.status = new_status
    dossier.status_changed_at = timezone.now()
    dossier.save()
    log(dossier, actor, action, summary, from_status=old_status, to_status=new_status, **payload)
    if open_tasks:
        open_step_tasks(dossier, new_status, actor, due_at=due_at, revision=revision)
    nt.notify_many(
        dossier.followers.all(), dossier, nt.KIND_INFO,
        f'{dossier.code} chuyển sang {Status(new_status).label}',
        summary, actor=actor,
    )


def current_main_task(dossier: ProductDevelopment) -> Task | None:
    return (
        dossier.tasks.filter(
            state=Task.STATE_OPEN, is_main=True, receipt__isnull=True, condition__isnull=True, evaluation__isnull=True,
        )
        .select_related('assignee__profile')
        .order_by('due_at', 'pk')
        .first()
    )


# ---------------------------------------------------------------------------
# Bước 1–2: đề xuất & duyệt đề bài
# ---------------------------------------------------------------------------

BRIEF_REQUIRED = (
    ('name', 'tên sản phẩm'),
    ('product_group', 'nhóm sản phẩm'),
    ('product_type', 'loại mã'),
    ('target_customer', 'khách hàng mục tiêu'),
    ('usage_need', 'nhu cầu sử dụng'),
    ('launch_date', 'ngày dự kiến ra mắt'),
    ('priority', 'mức độ ưu tiên'),
    ('owner', 'người phụ trách chính'),
    ('approver', 'người duyệt'),
)


def create_dossier(user, *, fields: dict, submit: bool = False) -> ProductDevelopment:
    _require(perms.can_create(user), 'Bạn không có quyền tạo đề xuất sản phẩm.')
    with transaction.atomic():
        dossier = ProductDevelopment(code=next_code(), proposer=user, **fields)
        if dossier.owner_id is None:
            allowed_owners = set(sla.configured_role_ids().get(Role.OWNER) or [])
            if not allowed_owners or user.pk in allowed_owners:
                dossier.owner = user
        dossier.save()
        log(dossier, user, 'created', f'{_name(user)} tạo đề xuất sản phẩm.', to_status=Status.DRAFT)
        if submit:
            submit_brief(dossier, user)
    return dossier


def update_brief(dossier: ProductDevelopment, user, *, fields: dict) -> None:
    _require(
        perms.can_edit_brief(dossier, user) or perms.can_edit_overview_fields(dossier, user),
        'Chỉ sửa tên, khách hàng mục tiêu và đề bài khi hồ sơ đang ở Tổng quan.',
    )
    if dossier.status == Status.LIBRARY_REOPEN:
        _require(allows_reopen_overview(dossier), 'Công đoạn đang mở không phải Tổng quan — không sửa đề bài được.')
    changed = []
    for key, value in fields.items():
        if getattr(dossier, key) != value:
            setattr(dossier, key, value)
            changed.append(key)
    if changed:
        dossier.save()
        log(dossier, user, 'brief_updated', f'{_name(user)} cập nhật đề bài.', fields=changed)


def submit_brief(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    _require(dossier.status in (Status.DRAFT, Status.BRIEF_NEEDS_INFO), 'Hồ sơ không ở bước đề xuất.')
    _require(perms.can_edit_brief(dossier, user), 'Chỉ người đề xuất hoặc người phụ trách được chuyển sang thiết kế.')
    missing = [label for field, label in BRIEF_REQUIRED if not getattr(dossier, field, None)]
    _require(not missing, 'Chưa đủ thông tin đề bài: ' + ', '.join(missing) + '.')
    _require(perms.has_approve_permission(dossier.approver), 'Người duyệt được chọn không có quyền duyệt hồ sơ.')
    first_submit = dossier.submitted_at is None
    with transaction.atomic():
        dossier.submitted_at = timezone.now()
        if not dossier.design_versions.exists():
            DesignVersion.objects.create(dossier=dossier, version_no=1, created_by=user)
        _transition(
            dossier, Status.DESIGNING, user, 'brief_submitted',
            f'{_name(user)} gửi đề xuất, chuyển sang thiết kế.', due_at=due_at,
        )
    if first_submit:
        _notify_assigned_roles(dossier, user, [r for r in DOSSIER_ROLE_FIELDS if r != Role.APPROVER])


def _notify_assigned_roles(dossier: ProductDevelopment, actor, roles) -> None:
    """Báo cho từng người được gán vai trò trên hồ sơ (gộp nhiều vai trò của cùng một người)."""
    per_user: dict[int, tuple[object, list[str]]] = {}

    def _add(person, label: str) -> None:
        if person is None:
            return
        labels = per_user.setdefault(person.pk, (person, []))[1]
        if label not in labels:
            labels.append(label)

    for role in roles:
        label = Role(role).label
        _add(dossier.role_user(role), label)
        partner = ROLE_PARTNER.get(role)
        if partner:
            _add(getattr(dossier, partner, None), label)
        if role == Role.OWNER:
            _add(dossier.co_owner, label)
    for person, labels in per_user.values():
        nt.notify(person, dossier, nt.KIND_ASSIGNED, f'Bạn được giao: {", ".join(labels)}',
                  f'{dossier.code} — {dossier.name}', actor=actor)


def decide_brief(dossier: ProductDevelopment, user, *, decision: str, comment: str = '', due_at=None) -> None:
    _require(dossier.status == Status.BRIEF_PENDING, 'Hồ sơ không ở bước chờ duyệt đề bài.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    with transaction.atomic():
        if decision == ApprovalDecision.APPROVED:
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.BRIEF, decision=decision,
                                    comment=comment, decided_by=user)
            if not dossier.design_versions.exists():
                DesignVersion.objects.create(dossier=dossier, version_no=1, created_by=user)
            _transition(dossier, Status.DESIGNING, user, 'brief_approved',
                        f'{_name(user)} duyệt đề bài, chuyển sang thiết kế.', due_at=due_at, comment=comment)
        elif decision == ApprovalDecision.REQUEST_CHANGE:
            comment = _require_text(comment, 'nội dung cần bổ sung')
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.BRIEF, decision=decision,
                                    comment=comment, decided_by=user)
            _transition(dossier, Status.BRIEF_NEEDS_INFO, user, 'brief_returned',
                        f'{_name(user)} yêu cầu bổ sung đề bài: {comment}', due_at=due_at, revision=True)
        elif decision == ApprovalDecision.CANCELLED:
            cancel(dossier, user, reason=comment, stage=ApprovalStage.BRIEF)
        else:
            raise WorkflowError('Quyết định không hợp lệ.')


# ---------------------------------------------------------------------------
# Bước 3–4: thiết kế & duyệt thiết kế
# ---------------------------------------------------------------------------

def test_edit_after_approval(dossier: ProductDevelopment) -> bool:
    """Trạng thái test: hồ sơ đã duyệt sản xuất vẫn sửa được, không cần yêu cầu thay đổi."""
    return dossier.status == Status.APPROVED and bool(sla.get_settings().test_mode)


def _approved_design_editable(dossier, dv: DesignVersion) -> bool:
    return (
        test_edit_after_approval(dossier)
        and dv.is_current
        and dv.state == DesignVersion.STATE_APPROVED
    )


def _approved_sample_editable(dossier, sv: SampleVersion) -> bool:
    return (
        test_edit_after_approval(dossier)
        and sv.is_current
        and sv.state == SampleVersion.STATE_PASSED
    )


def _require_design_editable(dossier, dv: DesignVersion, user) -> None:
    _require(dv.dossier_id == dossier.pk, 'Phiên bản không thuộc hồ sơ.')
    if not _approved_design_editable(dossier, dv) and not design_reopened(dossier, dv):
        if dossier.status == Status.LIBRARY_REOPEN:
            _require(allows_reopen_design(dossier) and dv.is_editable,
                     'Công đoạn đang mở không phải Thiết kế — không sửa được.')
        else:
            _require(dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE) and dv.is_editable,
                     'Phiên bản thiết kế này đã gửi duyệt hoặc đã lưu trữ — không sửa được.')
    _require(perms.can_work_as(dossier, user, Role.DESIGNER, Role.OWNER),
             'Chỉ Thiết kế / R&D hoặc người phụ trách được cập nhật thiết kế.')


def save_design_version(dv: DesignVersion, user, *, fields: dict) -> None:
    dossier = dv.dossier
    _require_design_editable(dossier, dv, user)
    for key, value in fields.items():
        setattr(dv, key, value)
    dv.updated_by = user
    dv.save()
    log(dossier, user, 'design_saved', f'{_name(user)} cập nhật nội dung thiết kế {dv.label}.')


def add_colorway(dv: DesignVersion, user, *, name: str, color_codes: str = '', note: str = '',
                 uploaded_file=None) -> Colorway:
    """Thêm một phối màu ở tab Thiết kế."""
    created = add_colorways(dv, user, rows=[{
        'name': name, 'color_codes': color_codes, 'note': note, 'uploaded_file': uploaded_file,
    }])
    return created[0]


def add_colorways(dv: DesignVersion, user, *, rows: list[dict]) -> list[Colorway]:
    """Thêm nhiều phối màu ở tab Thiết kế trong một lần lưu. Ảnh lưu lên NAS."""
    _require_design_editable(dv.dossier, dv, user)
    _require(bool(rows), 'Thêm ít nhất một phối màu.')
    prepared = []
    for index, row in enumerate(rows, start=1):
        name = _require_text(row.get('name'), f'tên phối màu (dòng {index})')
        uploaded_file = row.get('uploaded_file')
        _require(uploaded_file is not None, f'Chọn file ảnh phối màu (dòng {index}).')
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        _require(ext in IMAGE_EXTENSIONS, f'Ảnh phối màu phải là tệp ảnh (dòng {index}).')
        prepared.append({
            'name': name,
            'color_codes': (row.get('color_codes') or '').strip(),
            'note': (row.get('note') or '').strip(),
            'uploaded_file': uploaded_file,
        })
    created: list[Colorway] = []
    with transaction.atomic():
        order = dv.colorways.count()
        for row in prepared:
            order += 1
            cw = Colorway.objects.create(
                design_version=dv, name=row['name'],
                color_codes=row['color_codes'], note=row['note'], sort_order=order,
            )
            upload_attachment(
                dv.dossier, user, uploaded_file=row['uploaded_file'], kind=AttachmentKind.COLORWAY,
                design_version=dv, colorway=cw, tab='design',
            )
            created.append(cw)
        labels = ', '.join(f'«{cw.name}»' for cw in created)
        log(
            dv.dossier, user, 'colorway_added',
            f'{_name(user)} thêm {len(created)} colorway vào {dv.label}: {labels}.',
        )
    return created


def delete_colorway(cw: Colorway, user) -> None:
    dv = cw.design_version
    _require_design_editable(dv.dossier, dv, user)
    _delete_colorway(cw, user, 'khỏi ' + dv.label)


def add_technical_colorway(sv: SampleVersion, user, *, name: str, color_codes: str, note: str = '') -> Colorway:
    """Thêm màu ở bước kỹ thuật vào phương án thiết kế của mẫu."""
    dossier = sv.dossier
    _require_tech_editable(dossier, sv, user)
    dv = sv.design_version
    _require(dv is not None, 'Mẫu chưa gắn phương án thiết kế.')
    order = dv.colorways.count() + 1
    cw = Colorway.objects.create(
        design_version=dv, name=_require_text(name, 'tên phối màu'),
        color_codes=_require_text(color_codes, 'mã màu'), note=note, sort_order=order,
    )
    log(dossier, user, 'colorway_added', f'{_name(user)} thêm màu «{cw.name}» ở bước kỹ thuật.')
    return cw


def delete_technical_colorway(sv: SampleVersion, cw: Colorway, user) -> None:
    dossier = sv.dossier
    _require_tech_editable(dossier, sv, user)
    _require(cw.design_version_id == sv.design_version_id, 'Màu không thuộc thiết kế của mẫu này.')
    _delete_colorway(cw, user, 'ở bước kỹ thuật')


def _delete_colorway(cw: Colorway, user, where: str) -> None:
    dv = cw.design_version
    Attachment.objects.filter(colorway=cw, is_deleted=False).update(
        is_deleted=True, deleted_by=user, deleted_at=timezone.now(),
    )
    log(dv.dossier, user, 'colorway_deleted', f'{_name(user)} xóa màu «{cw.name}» {where}.')
    cw.delete()


def _live(qs):
    return qs.filter(is_deleted=False, is_current=True)


def design_checklist(dv: DesignVersion | None) -> list[tuple[str, bool]]:
    """Điều kiện của phương án được chọn trước khi chuyển kỹ thuật.

    Trạng thái test bật: không bắt ảnh 2 mặt, ảnh phối màu và file thiết kế gốc.
    """
    if sla.get_settings().test_mode:
        return []
    if dv is None:
        return [('Có phiên bản thiết kế', False)]
    atts = _live(dv.attachments.all())
    kinds = set(atts.values_list('kind', flat=True))
    colorways = list(dv.colorways.all())
    with_image = set(atts.filter(
        kind=AttachmentKind.COLORWAY, colorway_id__isnull=False,
    ).values_list('colorway_id', flat=True))
    return [
        ('Ảnh 2 mặt', AttachmentKind.FRONT in kinds),
        ('Ảnh phối màu', bool(colorways) and all(
            cw.pk in with_image or (cw.color_codes or '').strip() for cw in colorways
        )),
        ('File thiết kế gốc', AttachmentKind.DESIGN_SOURCE in kinds),
    ]


def design_checklist_all(dossier: ProductDevelopment) -> list[tuple[str, bool]]:
    """Quy tắc 1 cho mọi phương án đang trình — mỗi phương án đều phải đủ."""
    dvs = dossier.current_design_versions()
    if len(dvs) <= 1:
        return design_checklist(dvs[0] if dvs else None)
    return [(f'PA {dv.option_letter}: {label}', ok) for dv in dvs for label, ok in design_checklist(dv)]


def submit_design(dossier: ProductDevelopment, user, *, due_at=None, option_id=None) -> None:
    """Chọn một phương án rồi chuyển sang kỹ thuật. Phương án còn lại đóng."""
    _require(dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE), 'Hồ sơ không ở bước thiết kế.')
    dvs = dossier.current_design_versions()
    _require(bool(dvs), 'Chưa có phiên bản thiết kế.')
    if len(dvs) == 1:
        chosen = dvs[0]
    else:
        chosen = next((dv for dv in dvs if str(dv.pk) == str(option_id or '')), None)
        _require(chosen is not None, 'Chọn một phương án để chuyển kỹ thuật.')
    _require_design_editable(dossier, chosen, user)
    missing = [label for label, ok in design_checklist(chosen) if not ok]
    _require(not missing, 'Chưa đủ điều kiện chuyển kỹ thuật: ' + ', '.join(missing) + '.')
    if needs_change_note(chosen) and not chosen.change_note.strip():
        _require(False, f'Nhập nội dung thay đổi so với phiên bản trước: {chosen.tag}.')
    others = [dv for dv in dvs if dv.pk != chosen.pk]
    with transaction.atomic():
        chosen.state = DesignVersion.STATE_APPROVED
        chosen.save(update_fields=['state', 'updated_at'])
        _retire_design_versions(others, DesignVersion.STATE_NOT_SELECTED)
        dossier.approved_design_version = chosen
        previous_sample = dossier.sample_versions.order_by('-version_no').first()
        _new_sample_version(dossier, chosen, user, source=previous_sample)
        label = chosen.tag if len(dvs) > 1 else chosen.label
        _transition(dossier, Status.TECHNICAL, user, 'design_to_technical',
                    f'{_name(user)} chọn {label}, chuyển sang kỹ thuật.',
                    due_at=due_at, version=label)
        nt.notify_many(
            [dossier.owner, dossier.co_owner, dossier.technician, dossier.co_technician, dossier.proposer],
                       dossier, nt.KIND_TASK, f'{label} chuyển sang kỹ thuật',
                       f'{dossier.code} — {dossier.name}', actor=user)


def needs_change_note(dv: DesignVersion) -> bool:
    """Phương án có bản trước (đã trình duyệt) mới cần ghi nội dung thay đổi."""
    return dv.dossier.design_versions.filter(option_no=dv.option_no, version_no__lt=dv.version_no).exists()


MAX_DESIGN_OPTIONS = 5


def add_design_option(dossier: ProductDevelopment, user, *, copy_from: DesignVersion | None = None) -> DesignVersion:
    _require(dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE), 'Hồ sơ không ở bước thiết kế.')
    _require(perms.can_work_as(dossier, user, Role.DESIGNER, Role.OWNER),
             'Chỉ Thiết kế / R&D hoặc người phụ trách được thêm phương án.')
    current = dossier.current_design_versions()
    _require(len(current) < MAX_DESIGN_OPTIONS, f'Tối đa {MAX_DESIGN_OPTIONS} phương án cùng lúc.')
    if copy_from is not None:
        _require(copy_from.dossier_id == dossier.pk and copy_from.is_current, 'Phương án nguồn không hợp lệ.')
    all_dvs = DesignVersion.objects.filter(dossier=dossier)
    option_no = (all_dvs.order_by('-option_no').values_list('option_no', flat=True).first() or 0) + 1
    with transaction.atomic():
        new = DesignVersion.objects.create(
            dossier=dossier,
            option_no=option_no,
            version_no=(all_dvs.order_by('-version_no').values_list('version_no', flat=True).first() or 0) + 1,
            created_by=user,
        )
        if copy_from is not None:
            _copy_design_content(copy_from, new)
        source = f' (sao chép từ PA {copy_from.option_letter})' if copy_from else ''
        log(dossier, user, 'design_option_added', f'{_name(user)} thêm {new.option_label}{source}.', version=new.tag)
    return new


def drop_design_option(dv: DesignVersion, user) -> None:
    dossier = dv.dossier
    _require_design_editable(dossier, dv, user)
    _require(len(dossier.current_design_versions()) > 1, 'Hồ sơ phải còn ít nhất một phương án.')
    dv.state = DesignVersion.STATE_DROPPED
    dv.is_current = False
    dv.updated_by = user
    dv.save(update_fields=['state', 'is_current', 'updated_by', 'updated_at'])
    log(dossier, user, 'design_option_dropped', f'{_name(user)} bỏ {dv.option_label} ({dv.label}).', version=dv.tag)


def _clone_attachments(source_qs, *, dossier, design_version=None, sample_version=None, colorway_map=None):
    for att in _live(source_qs):
        Attachment.objects.create(
            dossier=dossier,
            design_version=design_version,
            sample_version=sample_version,
            colorway=(colorway_map or {}).get(att.colorway_id),
            kind=att.kind,
            file=att.file.name,
            original_name=att.original_name,
            size=att.size,
            note=att.note,
            uploaded_by=att.uploaded_by,
        )


DESIGN_CONTENT_FIELDS = ('style_description', 'pattern_description', 'logo_placement', 'materials', 'highlights')


def _copy_design_content(source: DesignVersion, target: DesignVersion) -> None:
    for field in DESIGN_CONTENT_FIELDS:
        setattr(target, field, getattr(source, field))
    target.save()
    colorway_map = {}
    for cw in source.colorways.all():
        colorway_map[cw.pk] = Colorway.objects.create(
            design_version=target, name=cw.name, color_codes=cw.color_codes, note=cw.note, sort_order=cw.sort_order,
        )
    _clone_attachments(source.attachments.all(), dossier=target.dossier, design_version=target,
                       colorway_map=colorway_map)


def _new_design_version(dossier, source: DesignVersion, user) -> DesignVersion:
    """Phiên bản kế tiếp của cùng phương án — bản cũ giữ nguyên để xem lại."""
    all_dvs = DesignVersion.objects.filter(dossier=dossier)
    all_dvs.filter(option_no=source.option_no).update(is_current=False)
    new = DesignVersion.objects.create(
        dossier=dossier,
        option_no=source.option_no,
        version_no=(all_dvs.order_by('-version_no').values_list('version_no', flat=True).first() or 0) + 1,
        created_by=user,
    )
    _copy_design_content(source, new)
    return new


def _retire_design_versions(dvs, state: str) -> None:
    if dvs:
        DesignVersion.objects.filter(pk__in=[dv.pk for dv in dvs]).update(
            state=state, is_current=False, updated_at=timezone.now(),
        )


def _new_sample_version(dossier, design_version: DesignVersion, user, source: SampleVersion | None = None):
    qs = SampleVersion.objects.filter(dossier=dossier)
    qs.update(is_current=False)
    new = SampleVersion.objects.create(
        dossier=dossier,
        version_no=(qs.order_by('-version_no').values_list('version_no', flat=True).first() or 0) + 1,
        design_version=design_version,
        maker=dossier.sample_maker,
        assigned_date=timezone.localdate(),
        created_by=user,
    )
    pack = TechnicalPack.objects.create(sample_version=new, updated_by=user)
    if source is not None:
        old_pack = getattr(source, 'tech_pack', None)
        if old_pack is not None:
            for field in ('pattern_note', 'size_spec', 'cutting_req', 'sewing_req', 'decoration_req', 'finishing_req', 'packing_req'):
                setattr(pack, field, getattr(old_pack, field))
            pack.save()
            MaterialLine.objects.bulk_create([
                MaterialLine(
                    tech_pack=pack, material_id=line.material_id, line_unit_id=line.line_unit_id,
                    material_name=line.material_name, is_main=line.is_main, spec=line.spec,
                    consumption=line.consumption, unit=line.unit, unit_price=line.unit_price,
                    sort_order=line.sort_order,
                )
                for line in old_pack.material_lines.all()
            ])
        _clone_attachments(
            source.attachments.filter(kind__in=(AttachmentKind.TECH_SPEC, AttachmentKind.PATTERN)),
            dossier=dossier, sample_version=new,
        )
    return new


def decide_design(dossier: ProductDevelopment, user, *, decision: str, comment: str = '', due_at=None,
                  option_id=None, keep_ids=None) -> None:
    """Duyệt: chọn đúng một phương án. Yêu cầu chỉnh: chọn các phương án giữ lại, mỗi phương án mở phiên bản mới."""
    _require(dossier.status == Status.DESIGN_PENDING, 'Hồ sơ không ở bước chờ duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    submitted = [dv for dv in dossier.current_design_versions() if dv.state == DesignVersion.STATE_SUBMITTED]
    _require(bool(submitted), 'Không có phương án thiết kế đang chờ duyệt.')
    by_pk = {str(dv.pk): dv for dv in submitted}
    multi = len(submitted) > 1
    with transaction.atomic():
        if decision == ApprovalDecision.APPROVED:
            dv = by_pk.get(str(option_id or '')) if multi else submitted[0]
            _require(dv is not None, 'Chọn một phương án để duyệt.')
            others = [o for o in submitted if o.pk != dv.pk]
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.DESIGN, decision=decision,
                                    comment=comment, design_version=dv, decided_by=user)
            dv.state = DesignVersion.STATE_APPROVED
            dv.save(update_fields=['state', 'updated_at'])
            _retire_design_versions(others, DesignVersion.STATE_NOT_SELECTED)
            dossier.approved_design_version = dv
            previous_sample = dossier.sample_versions.order_by('-version_no').first()
            _new_sample_version(dossier, dv, user, source=previous_sample)
            label = dv.tag if multi else dv.label
            _transition(dossier, Status.TECHNICAL, user, 'design_approved',
                        f'{_name(user)} duyệt thiết kế {label}, chuyển sang kỹ thuật.',
                        due_at=due_at, version=label, comment=comment)
            nt.notify_many(
            [dossier.owner, dossier.co_owner, dossier.technician, dossier.co_technician, dossier.proposer], dossier, nt.KIND_APPROVED,
                           f'Thiết kế {label} đã được duyệt', f'{dossier.code} — {dossier.name}', actor=user)
        elif decision == ApprovalDecision.REQUEST_CHANGE:
            comment = _require_text(comment, 'nội dung yêu cầu chỉnh sửa')
            if multi:
                keep = [by_pk[k] for k in dict.fromkeys(str(k) for k in (keep_ids or [])) if k in by_pk]
                _require(bool(keep), 'Chọn ít nhất một phương án giữ lại để chỉnh.')
            else:
                keep = submitted
            dropped = [o for o in submitted if o not in keep]
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.DESIGN, decision=decision,
                                    comment=comment, design_version=keep[0] if len(keep) == 1 else None,
                                    decided_by=user)
            new_labels = []
            for dv in keep:
                Comment.objects.create(dossier=dossier, design_version=dv, author=user, body=comment,
                                       is_revision_request=True)
                dv.state = DesignVersion.STATE_REJECTED
                dv.save(update_fields=['state', 'updated_at'])
                new = _new_design_version(dossier, dv, user)
                new_labels.append(new.tag if multi else new.label)
            _retire_design_versions(dropped, DesignVersion.STATE_NOT_SELECTED)
            summary = f'{_name(user)} yêu cầu chỉnh thiết kế → mở {", ".join(new_labels)}'
            if dropped:
                summary += f'; bỏ {", ".join("PA " + o.option_letter for o in dropped)}'
            _transition(dossier, Status.DESIGN_REVISE, user, 'design_returned', f'{summary}: {comment}',
                        due_at=due_at, revision=True, version=', '.join(new_labels))
        elif decision == ApprovalDecision.CANCELLED:
            cancel(dossier, user, reason=comment, stage=ApprovalStage.DESIGN)
        else:
            raise WorkflowError('Quyết định không hợp lệ.')


# ---------------------------------------------------------------------------
# Bước 5–6: làm mẫu, hồ sơ kỹ thuật, đánh giá mẫu
# ---------------------------------------------------------------------------

TECH_EDIT_STATUSES = (
    Status.TECHNICAL,
    Status.TECHNICAL_REVISE,
    Status.SAMPLING,
    Status.SAMPLE_REVISE,
    Status.LIBRARY_REOPEN,
)


def _require_tech_editable(dossier, sv: SampleVersion, user) -> None:
    _require(sv.dossier_id == dossier.pk, 'Mẫu không thuộc hồ sơ.')
    if not _approved_sample_editable(dossier, sv) and not tech_reopened(dossier, sv):
        if dossier.status == Status.LIBRARY_REOPEN:
            _require(allows_reopen_technical(dossier) and sv.is_editable,
                     'Công đoạn đang mở không phải Kỹ thuật — không sửa được.')
        else:
            _require(dossier.status in TECH_EDIT_STATUSES and sv.is_editable,
                     'Hồ sơ kỹ thuật đã khóa hoặc đã lưu trữ — không sửa được.')
    _require(perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER),
             'Chỉ Kỹ thuật / Tài liệu kỹ thuật hoặc người phụ trách được cập nhật.')


def _require_sample_editable(dossier, sv: SampleVersion, user, *roles) -> None:
    _require(sv.dossier_id == dossier.pk, 'Mẫu không thuộc hồ sơ.')
    if not _approved_sample_editable(dossier, sv) and not sample_reopened(dossier, sv):
        if dossier.status == Status.LIBRARY_REOPEN:
            _require(allows_reopen_sample(dossier) and sv.is_editable,
                     'Công đoạn đang mở không phải May mẫu — không sửa được.')
        else:
            _require(dossier.status in (Status.SAMPLING, Status.SAMPLE_REVISE) and sv.is_editable,
                     'Mẫu này đã gửi đánh giá hoặc đã lưu trữ — không sửa được.')
    _require(perms.can_work_as(dossier, user, *roles), 'Bạn không phụ trách phần việc này trên hồ sơ.')


def save_sample(sv: SampleVersion, user, *, fields: dict) -> None:
    dossier = sv.dossier
    _require_sample_editable(dossier, sv, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
    if 'maker' in fields:
        maker_id = getattr(fields.get('maker'), 'pk', None)
        allowed = {pk for pk in (dossier.sample_maker_id, dossier.co_sample_maker_id) if pk}
        if not perms.can_work_as(dossier, user, Role.OWNER) or maker_id not in allowed:
            raise WorkflowError('Chỉ người phụ trách chính được đổi người làm, trong danh sách May mẫu của hồ sơ.')
    for key, value in fields.items():
        setattr(sv, key, value)
    sv.save()
    log(dossier, user, 'sample_saved', f'{_name(user)} cập nhật tiến độ mẫu {sv.label}.')


def save_tech_pack(sv: SampleVersion, user, *, fields: dict, lines: list[dict]) -> None:
    dossier = sv.dossier
    _require_tech_editable(dossier, sv, user)
    pack, _ = TechnicalPack.objects.get_or_create(sample_version=sv)
    with transaction.atomic():
        for key, value in fields.items():
            setattr(pack, key, value)
        pack.updated_by = user
        pack.save()
        pack.material_lines.all().delete()
        MaterialLine.objects.bulk_create([
            MaterialLine(tech_pack=pack, sort_order=i, **line) for i, line in enumerate(lines, start=1)
        ])
    log(dossier, user, 'tech_pack_saved', f'{_name(user)} cập nhật hồ sơ kỹ thuật & BOM mẫu {sv.label}.')


def submit_sample(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    """May mẫu xong thì dừng ở cột Duyệt thiết kế. Người duyệt chốt ở bước đó."""
    _require(dossier.status in (Status.SAMPLING, Status.SAMPLE_REVISE), 'Hồ sơ không ở bước làm mẫu.')
    _require(perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER),
             'Chỉ May mẫu, Kỹ thuật hoặc người phụ trách được gửi duyệt thiết kế.')
    sv = dossier.current_sample_version()
    _require(sv is not None, 'Chưa có mẫu để gửi duyệt.')
    with transaction.atomic():
        if sv.state != SampleVersion.STATE_SUBMITTED:
            sv.state = SampleVersion.STATE_SUBMITTED
            sv.save(update_fields=['state', 'updated_at'])
        _transition(dossier, Status.SAMPLE_EVAL_PENDING, user, 'sample_submitted',
                    f'{_name(user)} gửi duyệt thiết kế {sv.label}.',
                    due_at=due_at, version=sv.label)


def submit_technical(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    """Kỹ thuật tự chốt rập, thông số và BOM rồi chuyển làm mẫu. Không bắt đủ file."""
    _require(dossier.status in (Status.TECHNICAL, Status.TECHNICAL_REVISE), 'Hồ sơ không ở bước kỹ thuật.')
    _require(perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER),
             'Chỉ Kỹ thuật / Tài liệu kỹ thuật hoặc người phụ trách được chuyển làm mẫu.')
    sv = dossier.current_sample_version()
    with transaction.atomic():
        if sv is None:
            dv = dossier.approved_design_version or dossier.current_design_version()
            _require(dv is not None, 'Chưa có thiết kế để làm mẫu.')
            sv = _new_sample_version(dossier, dv, user)
        elif sv.state != SampleVersion.STATE_IN_PROGRESS:
            sv.state = SampleVersion.STATE_IN_PROGRESS
            sv.save(update_fields=['state', 'updated_at'])
        _transition(dossier, Status.SAMPLING, user, 'technical_to_sample',
                    f'{_name(user)} chuyển sang làm mẫu {sv.label}.',
                    due_at=due_at, version=sv.label)
        nt.notify_many(
            [dossier.owner, dossier.co_owner, dossier.sample_maker, dossier.co_sample_maker, dossier.proposer],
                       dossier, nt.KIND_TASK, f'Chuyển làm mẫu {sv.label}',
                       f'{dossier.code} — {dossier.name}', actor=user)


def evaluator_roles_for(dossier: ProductDevelopment, user) -> list[str]:
    roles = perms.user_roles(dossier, user)
    result = []
    if Role.COSTING in roles:
        result.append(EvaluatorRole.COSTING)
    if Role.TECHNICIAN in roles:
        result.append(EvaluatorRole.TECHNICAL)
    if roles & {Role.OWNER, Role.DESIGNER}:
        result.append(EvaluatorRole.RND)
    if roles & {Role.SAMPLE_MAKER, Role.APPROVER, Role.PROPOSER} and not result:
        result.append(EvaluatorRole.OTHER)
    return result


def add_evaluation(dossier: ProductDevelopment, user, *, role: str, result: str, conclusion: str = '',
                   defects: str = '', fix_owner=None, fix_due=None, items: dict[str, tuple[str, str]]) -> SampleEvaluation:
    _require(dossier.status in DESIGN_APPROVAL_STATUSES, 'Hồ sơ không ở bước làm mẫu hoặc duyệt thiết kế.')
    _require(perms.can_act(dossier, user), 'Bạn không có quyền cập nhật hồ sơ.')
    _require(role in evaluator_roles_for(dossier, user), 'Bạn không được đánh giá mẫu với vai trò này.')
    sv = dossier.current_sample_version()
    _require(
        sv is not None and sv.state in (SampleVersion.STATE_IN_PROGRESS, SampleVersion.STATE_SUBMITTED),
        'Không có mẫu đang làm để đánh giá.',
    )
    if result == SampleEvaluation.RESULT_FAIL or fix_owner is not None:
        defects = _require_text(defects, 'lỗi / nội dung phải chỉnh')
    if fix_owner is not None:
        _require(fix_due is not None, 'Nhập hạn sửa cho người chịu trách nhiệm sửa.')
    with transaction.atomic():
        ev = SampleEvaluation.objects.create(
            sample_version=sv, role=role, evaluator=user, result=result, conclusion=conclusion,
            defects=defects, fix_owner=fix_owner, fix_due=fix_due,
        )
        EvaluationItem.objects.bulk_create([
            EvaluationItem(evaluation=ev, criterion=criterion, result=res, note=note)
            for criterion, (res, note) in items.items()
        ])
        task_role = {EvaluatorRole.COSTING: Role.COSTING}.get(role)
        if task_role:
            _complete_user_tasks(dossier, user, step=Status.SAMPLE_EVAL_PENDING, role=task_role)
        if ev.needs_fix:
            _open_fix_task(dossier, ev, actor=user)
        log(dossier, user, 'sample_evaluated',
            f'{_name(user)} đánh giá mẫu {sv.label} ({EvaluatorRole(role).label}): {ev.get_result_display()}.')
    nt.notify_many(_owners(dossier), dossier, nt.KIND_INFO, f'Có đánh giá mới cho mẫu {sv.label}',
                   f'{_name(user)} — {ev.get_result_display()}', actor=user)
    return ev


def _fix_due_at(ev: SampleEvaluation):
    hour = min(max(int(sla.get_settings().due_hour or sla.DEFAULT_DUE_HOUR), 0), 23)
    return timezone.make_aware(datetime.combine(ev.fix_due, time(hour, 0))) if ev.fix_due else None


def _open_fix_task(dossier: ProductDevelopment, ev: SampleEvaluation, *, actor) -> Task:
    sv = ev.sample_version
    return _create_task(
        dossier, step=Status.SAMPLE_EVAL_PENDING, role=Role.FIX,
        title=f'Sửa lỗi mẫu {sv.label}: {ev.defects.strip()[:120]}', assignee=ev.fix_owner,
        due_at=_fix_due_at(ev), is_main=False, actor=actor, notify_kind=nt.KIND_REVISION, evaluation=ev,
    )


def complete_fix(ev: SampleEvaluation, user, *, note: str = '') -> None:
    dossier = ev.sample_version.dossier
    _require(ev.needs_fix, 'Lỗi này đã được xác nhận sửa.')
    _require(dossier.status not in FINAL_STATUSES, 'Hồ sơ đã đóng / hủy.')
    _require(ev.fix_owner_id == user.pk or perms.has_full_dossier_access(user),
             'Chỉ người chịu trách nhiệm sửa được xác nhận.')
    with transaction.atomic():
        ev.fix_done_at = timezone.now()
        ev.fix_done_by = user
        ev.fix_done_note = note.strip()[:500]
        ev.save(update_fields=['fix_done_at', 'fix_done_by', 'fix_done_note'])
        if ev.tasks.filter(state=Task.STATE_OPEN).update(
            state=Task.STATE_DONE, completed_at=ev.fix_done_at, completed_by=user,
        ):
            nt.invalidate_badges(user)
        log(dossier, user, 'fix_done',
            f'{_name(user)} xác nhận đã sửa lỗi mẫu {ev.sample_version.label}: {ev.defects.strip()[:200]}'
            + (f' — {ev.fix_done_note}' if ev.fix_done_note else ''))
    nt.notify_many(_owners(dossier), dossier, nt.KIND_INFO, f'Đã sửa lỗi mẫu {ev.sample_version.label}',
                   ev.defects.strip()[:200], actor=user)


def request_technical_change(dossier: ProductDevelopment, user, *, comment: str, due_at=None) -> None:
    """Duyệt thiết kế trả về bước kỹ thuật, giữ mẫu và BOM hiện tại."""
    _require(dossier.status in APPROVER_DECIDE_STATUSES, 'Hồ sơ chưa ở bước duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    comment = _require_text(comment, 'nội dung cần chỉnh kỹ thuật')
    sv = dossier.current_sample_version()
    _require(sv is not None, 'Chưa có hồ sơ kỹ thuật để chỉnh.')
    with transaction.atomic():
        Approval.objects.create(
            dossier=dossier, stage=ApprovalStage.MASTER, decision=ApprovalDecision.REQUEST_CHANGE,
            comment=comment, sample_version=sv, decided_by=user,
        )
        Comment.objects.create(dossier=dossier, sample_version=sv, author=user, body=comment, is_revision_request=True)
        if sv.state != SampleVersion.STATE_IN_PROGRESS:
            sv.state = SampleVersion.STATE_IN_PROGRESS
            sv.save(update_fields=['state', 'updated_at'])
        _transition(dossier, Status.TECHNICAL_REVISE, user, 'technical_returned',
                    f'{_name(user)} yêu cầu chỉnh kỹ thuật từ mẫu {sv.label}: {comment}',
                    due_at=due_at, revision=True, version=sv.label)


def request_design_change_from_sample(dossier: ProductDevelopment, user, *, comment: str, due_at=None) -> None:
    """Mẫu lộ lỗi thiết kế: quay về thiết kế, mở phiên bản mới từ thiết kế đang làm mẫu."""
    _require(dossier.status in APPROVER_DECIDE_STATUSES, 'Hồ sơ chưa ở bước duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    comment = _require_text(comment, 'nội dung cần chỉnh thiết kế')
    sv = dossier.current_sample_version()
    dv = sv.design_version
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=ApprovalStage.MASTER,
                                decision=ApprovalDecision.REQUEST_CHANGE, comment=comment,
                                design_version=dv, sample_version=sv, decided_by=user)
        Comment.objects.create(dossier=dossier, sample_version=sv, author=user, body=comment, is_revision_request=True)
        Comment.objects.create(dossier=dossier, design_version=dv, author=user, body=comment, is_revision_request=True)
        sv.state = SampleVersion.STATE_FAILED
        sv.save(update_fields=['state', 'updated_at'])
        new = _new_design_version(dossier, dv, user)
        dossier.approved_design_version = None
        _transition(dossier, Status.DESIGN_REVISE, user, 'design_returned',
                    f'{_name(user)} yêu cầu chỉnh thiết kế từ mẫu {sv.label} → mở {new.label}: {comment}',
                    due_at=due_at, revision=True, version=new.label)


def request_sample_fix(dossier: ProductDevelopment, user, *, comment: str, due_at=None) -> None:
    _require(dossier.status in APPROVER_DECIDE_STATUSES, 'Hồ sơ chưa ở bước duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    comment = _require_text(comment, 'nội dung cần sửa mẫu')
    sv = dossier.current_sample_version()
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=ApprovalStage.MASTER,
                                decision=ApprovalDecision.REQUEST_CHANGE, comment=comment,
                                sample_version=sv, decided_by=user)
        Comment.objects.create(dossier=dossier, sample_version=sv, author=user, body=comment, is_revision_request=True)
        sv.state = SampleVersion.STATE_FAILED
        sv.save(update_fields=['state', 'updated_at'])
        new = _new_sample_version(dossier, sv.design_version, user, source=sv)
        _transition(dossier, Status.SAMPLE_REVISE, user, 'sample_returned',
                    f'{_name(user)} yêu cầu sửa mẫu {sv.label} → mở {new.label}: {comment}',
                    due_at=due_at, revision=True, version=new.label)


def master_checklist(dossier: ProductDevelopment, user=None) -> list[tuple[str, bool]]:
    """Điều kiện duyệt thiết kế.

    Trạng thái test bật: không bắt bảng thông số, BOM, ảnh mẫu thực tế và giá thành.
    vuong-admin và ductn không bị chặn bởi ảnh mẫu thực tế.
    """
    sv = dossier.current_sample_version()
    if sv is None:
        return [('Có mẫu', False)]
    evaluations = list(sv.evaluations.all())
    items = [
        ('Không còn đánh giá Không đạt', not any(e.result == SampleEvaluation.RESULT_FAIL for e in evaluations)),
    ]
    if sla.get_settings().test_mode:
        return items
    pack = getattr(sv, 'tech_pack', None)
    atts = _live(sv.attachments.all())
    rows = [
        ('Bảng thông số kỹ thuật', bool(pack and pack.size_spec.strip())
         or atts.filter(kind=AttachmentKind.TECH_SPEC).exists()),
        ('BOM có nguyên phụ liệu chính', bool(pack and pack.material_lines.filter(is_main=True).exists())),
    ]
    if not (user is not None and perms.has_full_dossier_access(user)):
        rows.append(('Ảnh mẫu thực tế', atts.filter(kind=AttachmentKind.SAMPLE_PHOTO).exists()))
    rows.extend(items)
    rows.append(('Giá thành dự kiến hoặc sau mẫu', dossier.estimated_cost is not None or dossier.post_sample_cost is not None))
    return rows


def submit_master(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    raise WorkflowError('Duyệt thiết kế không còn bước trình riêng. Người duyệt chốt ngay trên hồ sơ.')


# ---------------------------------------------------------------------------
# Bước 7: duyệt mẫu chuẩn (có điều kiện)
# ---------------------------------------------------------------------------

def official_code_conflict(code: str, *, exclude_dossier_id=None) -> str:
    from san_xuat.models import ProductTechDoc

    from thiet_ke_sp.services.official_code import style_taken_in_catalog

    code = (code or '').strip()
    if not code:
        return ''
    own = bool(
        exclude_dossier_id
        and ProductDevelopment.objects.filter(
            pk=exclude_dossier_id, official_product_code__iexact=code,
        ).exists()
    )
    if not own:
        taken = style_taken_in_catalog(code)
        if taken:
            return taken
    docs = ProductTechDoc.objects.filter(product_code__iexact=code)
    if exclude_dossier_id:
        own_doc_ids = Handover.objects.filter(
            dossier_id=exclude_dossier_id, tech_doc__isnull=False,
        ).values('tech_doc_id')
        docs = docs.exclude(pk__in=own_doc_ids)
    if docs.exists():
        return f'Mã {code} đã có hồ sơ kỹ thuật bên Sản xuất.'
    other = ProductDevelopment.objects.filter(official_product_code__iexact=code).exclude(
        status=Status.CANCELLED,
    )
    if exclude_dossier_id:
        other = other.exclude(pk=exclude_dossier_id)
    hit = other.first()
    if hit:
        return f'Mã {code} đang được dùng cho hồ sơ {hit.code}.'
    return ''


@dataclass
class ConditionInput:
    content: str
    assignee: object
    due_at: datetime


def decide_master(dossier: ProductDevelopment, user, *, official_code: str, comment: str = '',
                  conditions: list[ConditionInput] | None = None, due_at=None) -> None:
    _require(dossier.status in APPROVER_DECIDE_STATUSES, 'Hồ sơ chưa ở bước duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    missing = [label for label, ok in master_checklist(dossier, user) if not ok]
    _require(not missing, 'Chưa đủ điều kiện duyệt thiết kế: ' + ', '.join(missing) + '.')
    code = _require_text(official_code, 'mã sản phẩm chính thức').upper()
    conflict = official_code_conflict(code, exclude_dossier_id=dossier.pk)
    _require(not conflict, conflict)
    conditions = conditions or []
    for cond in conditions:
        _require(bool(cond.content.strip()) and cond.assignee is not None and cond.due_at is not None,
                 'Mỗi điều kiện cần nội dung, người xử lý và hạn.')
    sv = dossier.current_sample_version()
    _require(sv is not None, 'Chưa có mẫu để duyệt thiết kế.')
    decision = ApprovalDecision.APPROVED_CONDITIONAL if conditions else ApprovalDecision.APPROVED
    with transaction.atomic():
        approval = Approval.objects.create(
            dossier=dossier, stage=ApprovalStage.MASTER, decision=decision, comment=comment,
            design_version=sv.design_version, sample_version=sv, decided_by=user,
        )
        sv.state = SampleVersion.STATE_PASSED
        sv.completed_date = sv.completed_date or timezone.localdate()
        sv.save(update_fields=['state', 'completed_date', 'updated_at'])
        dossier.official_product_code = code
        dossier.final_sample_version = sv
        dossier.approved_design_version = sv.design_version
        dossier.approved_at = timezone.now()
        dossier.is_locked = True
        dossier.reopen_edit_step = ''
        summary = f'{_name(user)} duyệt thiết kế {sv.label} — mã chính thức {code}'
        if conditions:
            summary += f', kèm {len(conditions)} điều kiện'
        style, seeded, _record = _publish_to_library(dossier, user, note=comment)
        summary += f'. Đưa vào Thư viện — Style {style.code}'
        if seeded and _library_sizes(dossier):
            summary += f', {seeded} SKU theo màu và size đã chọn'
        elif seeded:
            summary += f', {seeded} SKU theo màu thiết kế'
        _transition(dossier, Status.HANDED_OVER, user, 'master_approved', summary + '.', due_at=due_at,
                    open_tasks=False, official_code=code, comment=comment, style_code=style.code)
        for cond in conditions:
            obj = ApprovalCondition.objects.create(
                dossier=dossier, approval=approval, content=cond.content.strip(),
                assignee=cond.assignee, due_at=cond.due_at,
            )
            _create_task(dossier, step=Status.HANDED_OVER, role=Role.CONDITION,
                         title=f'Điều kiện duyệt: {obj.content}', assignee=obj.assignee, due_at=obj.due_at,
                         is_main=False, actor=user, condition=obj)
    nt.notify_many(
        [dossier.owner, dossier.co_owner, dossier.designer, dossier.co_designer,
         dossier.technician, dossier.co_technician, dossier.proposer], dossier,
                   nt.KIND_APPROVED, f'Đã duyệt thiết kế {sv.label}',
                   f'{dossier.code} — {dossier.name} · Mã {code} đã vào Thư viện', actor=user)


def complete_condition(cond: ApprovalCondition, user, *, note: str = '') -> None:
    dossier = cond.dossier
    _require(not cond.is_done, 'Điều kiện đã hoàn thành.')
    _require(dossier.status == Status.APPROVED, 'Hồ sơ không ở bước chờ bàn giao.')
    _require(cond.assignee_id == user.pk or perms.is_dossier_approver(dossier, user),
             'Chỉ người xử lý điều kiện hoặc người duyệt được xác nhận.')
    with transaction.atomic():
        cond.done_at = timezone.now()
        cond.done_by = user
        cond.done_note = note.strip()
        cond.save()
        if cond.tasks.filter(state=Task.STATE_OPEN).update(
            state=Task.STATE_DONE, completed_at=cond.done_at, completed_by=user,
        ) and cond.assignee:
            nt.invalidate_badges(cond.assignee)
        log(dossier, user, 'condition_done', f'{_name(user)} hoàn thành điều kiện duyệt: {cond.content}.')
    nt.notify_many(_owners(dossier), dossier, nt.KIND_INFO, 'Điều kiện duyệt đã hoàn thành', cond.content, actor=user)


# ---------------------------------------------------------------------------
# Bước 8: bàn giao sản xuất
# ---------------------------------------------------------------------------

def handover_checklist(dossier: ProductDevelopment) -> list[tuple[str, bool]]:
    """Điều kiện thêm Style vào Thư viện."""
    return [
        ('Đã duyệt thiết kế', dossier.status in (Status.APPROVED, Status.HANDED_OVER, Status.CLOSED)),
        ('Có mã sản phẩm chính thức', bool(dossier.official_product_code)),
        ('Có phiên bản thiết kế cuối', dossier.approved_design_version_id is not None),
        ('Có mẫu chuẩn cuối', dossier.final_sample_version_id is not None),
        ('Đã xử lý hết điều kiện duyệt', not dossier.conditions.filter(done_at__isnull=True).exists()),
    ]


def _copy_files_to_tech_doc(dossier: ProductDevelopment, tech_doc, user) -> int:
    from san_xuat.design_nas_storage import design_file_abs_path
    from san_xuat.models import TechDocDesignFile

    dv = dossier.approved_design_version
    sv = dossier.final_sample_version
    source = list(_live(dv.attachments.exclude(kind=AttachmentKind.BACK)).order_by('kind', 'pk')) + list(
        _live(sv.attachments.exclude(kind=AttachmentKind.EVALUATION)).order_by('kind', 'pk')
    )
    copied = 0
    for order, att in enumerate(source, start=1):
        path = design_file_abs_path(att)
        if not path or not os.path.isfile(path):
            raise WorkflowError(f'Không đọc được tệp «{att.display_name}» trên NAS — kiểm tra kết nối NAS rồi thử lại.')
        label = att.get_kind_display()
        if att.colorway_id:
            label = f'{label} — {att.colorway.name}'
        item = TechDocDesignFile(
            tech_doc=tech_doc,
            title=f'{label} ({dv.label if att.design_version_id else sv.label})'[:200],
            notes=f'Bàn giao từ hồ sơ {dossier.code}',
            purpose='gallery' if att.is_image else 'design',
            sort_order=order,
            uploaded_by=user,
        )
        with open(path, 'rb') as fh:
            item.file.save(att.display_name, File(fh), save=False)
        item.save()
        copied += 1
    return copied


def _tech_doc_description(dossier: ProductDevelopment) -> str:
    dv = dossier.approved_design_version
    parts = [f'Bàn giao từ hồ sơ thiết kế {dossier.code} ({dv.label} / {dossier.final_sample_version.label}).']
    for label, value in (
        ('Kiểu dáng', dv.style_description),
        ('Màu sắc / họa tiết', dv.pattern_description),
        ('Logo / họa tiết', dv.logo_placement),
        ('Điểm nổi bật', dv.highlights),
    ):
        if value.strip():
            parts.append(f'{label}: {value.strip()}')
    return '\n'.join(parts)


def handover_style_types(dossier: ProductDevelopment) -> list:
    """Loại mã có thể gán cho Style khi bàn giao (theo nhóm hàng của hồ sơ)."""
    from thiet_ke_sp import catalog

    return list(catalog.types_in_group(dossier.product_group))


def _library_style(dossier: ProductDevelopment, user):
    from kho_san_pham.catalog_models import ProductStyle
    from kho_san_pham.choices import STYLE_SOURCE_DESIGN, STYLE_SOURCE_KIOTVIET

    code = (dossier.official_product_code or '').strip().upper()
    style = ProductStyle.objects.filter(code__iexact=code).first()
    if style:
        _require(style.source != STYLE_SOURCE_KIOTVIET,
                 f'Mã {code} đã là Style đồng bộ từ KiotViet — đổi mã chính thức khác.')
        style.source = STYLE_SOURCE_DESIGN
        style.is_active = True
        if not style.name:
            style.name = dossier.name[:500]
        style.save()
        return style
    product_type = dossier.product_type if dossier.product_type_id else None
    types = handover_style_types(dossier)
    if product_type is None and len(types) == 1:
        product_type = types[0]
    _require(product_type is not None,
             f'Nhóm «{dossier.product_group or "—"}» '
             + ('chưa có loại mã trong Thiết lập mã.' if not types
                else 'có nhiều loại mã — chọn Loại mã trên đề xuất.'))
    _require(product_type in types, 'Loại mã không thuộc nhóm hàng của hồ sơ.')
    return ProductStyle.objects.create(
        code=code, product_type=product_type, name=dossier.name[:500], year=timezone.localdate().year,
        source=STYLE_SOURCE_DESIGN, is_active=True, created_by=user,
    )


def _colorway_code(name: str) -> str:
    """Mã màu ngắn từ tên phối màu thiết kế (bỏ dấu) để ghép SKU."""
    import unicodedata

    from san_xuat.services.sku_catalog import normalize_token

    folded = unicodedata.normalize('NFD', name or '')
    folded = ''.join(ch for ch in folded if unicodedata.category(ch) != 'Mn')
    folded = folded.replace('đ', 'd').replace('Đ', 'D')
    return normalize_token(folded, max_len=12)


def _library_sizes(dossier: ProductDevelopment) -> list[str]:
    """Size đã tick ở bảng thông số của mẫu cuối — đó là size đưa vào Thư viện."""
    sv = dossier.final_sample_version or dossier.current_sample_version()
    pack = getattr(sv, 'tech_pack', None) if sv is not None else None
    return filled_sizes(getattr(pack, 'size_spec', '') or '')


def preview_library_skus(dossier: ProductDevelopment, style_code: str) -> list[dict]:
    """SKU size sẽ vào Thư viện. Mã là {mã gốc}-{size}; màu là thuộc tính của mã gốc."""
    from kho_san_pham.models import Product
    from san_xuat.hub_models import SxColor
    from san_xuat.services.sku_catalog import SkuError, compose_sku_code

    style_code = (style_code or '').strip().upper()
    sv = dossier.current_sample_version()
    dv = sv.design_version if sv is not None else None
    if dv is None:
        return []
    sizes = _library_sizes(dossier)
    rows: list[dict] = []
    seen: set[str] = set()
    for cw in dv.colorways.all():
        label = (cw.name or '').strip() or (cw.color_codes or '').strip()
        if not label:
            continue
        known = SxColor.objects.filter(name__iexact=label).first()
        if known:
            color_code = known.code
            color_label = (known.name or label)[:80]
        else:
            base = _colorway_code(label) or 'MAU'
            color_code = base
            n = 2
            while color_code in seen or (
                style_code and Product.objects.filter(style_code=style_code, color_code=color_code).exists()
            ):
                color_code = f'{base[:10]}{n}'
                n += 1
            color_label = label[:80]
        if color_code in seen:
            continue
        seen.add(color_code)
        for size in (sizes or ['']):
            if size and style_code:
                try:
                    sku = compose_sku_code(style_code=style_code, color_code='', size_label=size)
                except SkuError:
                    continue
            else:
                sku = style_code
            code = (color_code or '').upper()
            rows.append({
                'sku': sku,
                'color': color_label,
                'color_code': code,
                'size': (size or '').upper(),
                'swatch': cw.color_codes or '',
                'prefix': style_code,
            })
    return rows


def seed_library_color_skus(dossier: ProductDevelopment, style, user) -> int:
    """Tạo SKU {mã gốc}-{size}. Mỗi màu là thuộc tính color_code của cùng mã gốc."""
    from kho_san_pham.choices import (
        PRODUCT_TYPE_THANH_PHAM,
        SYNC_SOURCE_MANUAL,
        goods_product_type,
    )
    from kho_san_pham.models import Product
    from kho_san_pham.services.barcode import allocate_barcode
    from san_xuat.hub_models import SxColor
    from san_xuat.services.sku_catalog import SkuError, compose_sku_code, ensure_color, ensure_size

    from thiet_ke_sp import catalog

    dv = dossier.approved_design_version
    if dv is None:
        return 0
    sizes = _library_sizes(dossier)
    type_code = style.product_type.code if style.product_type_id else ''
    product_type = goods_product_type(catalog_type_code=type_code) if type_code else PRODUCT_TYPE_THANH_PHAM
    category = catalog.group_label(catalog.group_code(type_code)) if type_code else ''
    description = _tech_doc_description(dossier)
    name = (style.name or dossier.name or style.code)[:500]
    created = 0
    seen_colors: set[str] = set()
    for cw in dv.colorways.all():
        label = (cw.name or '').strip() or (cw.color_codes or '').strip()
        if not label:
            continue
        known = SxColor.objects.filter(name__iexact=label).first()
        if known:
            color_code, color_label = known.code, (known.name or label)[:80]
        else:
            base = _colorway_code(label) or 'MAU'
            color_code = base
            n = 2
            while color_code in seen_colors or Product.objects.filter(
                style_code=style.code, color_code=color_code,
            ).exists():
                color_code = f'{base[:10]}{n}'
                n += 1
            ensure_color(code=color_code, name=label[:80], user=user)
            color_label = label[:80]
        if color_code in seen_colors:
            continue
        seen_colors.add(color_code)
        for size in (sizes or ['']):
            if Product.objects.filter(
                style_code=style.code, color_code=color_code, size_label=size,
            ).exists():
                continue
            if size:
                try:
                    sku_code = compose_sku_code(
                        style_code=style.code, color_code='', size_label=size,
                    )
                except SkuError:
                    continue
                ensure_size(code=size, name=size, user=user)
            else:
                sku_code = style.code
            Product.objects.create(
                product_type=product_type,
                catalog_type=style.product_type,
                style_code=style.code,
                color_code=color_code,
                color_label=color_label,
                size_label=size,
                code=sku_code,
                name=name,
                full_name=name,
                unit='Cái',
                category_name=category[:255],
                description=description,
                bar_code=allocate_barcode(),
                sync_source=SYNC_SOURCE_MANUAL,
                is_active=True,
                created_by=user if getattr(user, 'pk', None) else None,
            )
            created += 1
    return created


def _publish_to_library(dossier: ProductDevelopment, user, *, note: str = ''):
    """Tạo Style và SKU trong Thư viện theo mã gốc, màu và size đang có trên hồ sơ."""
    style = _library_style(dossier, user)
    seeded = seed_library_color_skus(dossier, style, user)
    try:
        record = dossier.handover
    except Handover.DoesNotExist:
        record = None
    if record is None:
        record = Handover.objects.create(
            dossier=dossier, product_code=style.code,
            design_version=dossier.approved_design_version, sample_version=dossier.final_sample_version,
            note=note, handed_by=user,
        )
    else:
        record.product_code = style.code
        record.design_version = dossier.approved_design_version
        record.sample_version = dossier.final_sample_version
        record.note = note
        record.handed_by = user
        record.handed_at = timezone.now()
        record.save()
    return style, seeded, record


def handover(dossier: ProductDevelopment, user, *, note: str = '', due_at=None):
    """Hồ sơ đã duyệt từ trước, còn chờ vào Thư viện. Luồng mới vào Thư viện ngay khi duyệt."""
    _require(dossier.status == Status.APPROVED, 'Hồ sơ chưa được duyệt hoặc đã thêm vào Thư viện.')
    _require(perms.can_work_as(dossier, user, Role.OWNER, Role.TECHNICIAN),
             'Chỉ người phụ trách chính hoặc Kỹ thuật được thêm vào Thư viện.')
    missing = [label for label, ok in handover_checklist(dossier) if not ok]
    _require(not missing, 'Chưa đủ điều kiện thêm vào Thư viện: ' + ', '.join(missing) + '.')
    conflict = official_code_conflict(dossier.official_product_code, exclude_dossier_id=dossier.pk)
    _require(not conflict, conflict)
    with transaction.atomic():
        style, seeded, record = _publish_to_library(dossier, user, note=note)
        text = f'{_name(user)} thêm vào Thư viện — Style {style.code}.'
        if seeded and _library_sizes(dossier):
            text += f' Tạo {seeded} SKU theo màu thiết kế và size đã nhập ở bảng thông số.'
        elif seeded:
            text += f' Tạo {seeded} SKU theo màu thiết kế — bổ sung size trước khi chuyển sản xuất.'
        elif record.tech_doc_id:
            text += ' Giữ SKU và hồ sơ sản xuất đã có.'
        _transition(dossier, Status.HANDED_OVER, user, 'handed_over', text,
                    open_tasks=False, style_code=style.code)
    return record


REOPEN_EDIT_STEPS = (
    ('overview', 'Tổng quan'),
    ('design', 'Thiết kế'),
    ('technical', 'Kỹ thuật'),
    ('sample', 'May mẫu'),
)


def reopen_edit_step(dossier: ProductDevelopment) -> str:
    """Công đoạn được mở sửa khi đang chỉnh sau hoàn thành (rỗng = chưa chọn / hồ sơ cũ)."""
    if dossier.status != Status.LIBRARY_REOPEN:
        return ''
    return (dossier.reopen_edit_step or '').strip()


def allows_reopen_overview(dossier: ProductDevelopment) -> bool:
    step = reopen_edit_step(dossier)
    return dossier.status == Status.LIBRARY_REOPEN and (not step or step == 'overview')


def allows_reopen_design(dossier: ProductDevelopment) -> bool:
    step = reopen_edit_step(dossier)
    return dossier.status == Status.LIBRARY_REOPEN and (not step or step == 'design')


def allows_reopen_technical(dossier: ProductDevelopment) -> bool:
    step = reopen_edit_step(dossier)
    return dossier.status == Status.LIBRARY_REOPEN and (not step or step == 'technical')


def allows_reopen_sample(dossier: ProductDevelopment) -> bool:
    step = reopen_edit_step(dossier)
    return dossier.status == Status.LIBRARY_REOPEN and (not step or step == 'sample')


def reopen_completion(dossier: ProductDevelopment, user, *, reason: str, edit_step: str) -> None:
    """Gỡ khỏi Thư viện, chỉ mở đúng một công đoạn để sửa rồi gửi duyệt thiết kế."""
    _require(dossier.status == Status.HANDED_OVER, 'Chỉ huỷ hoàn thành khi hồ sơ đã thêm vào Thư viện.')
    _require(perms.is_participant(dossier, user), 'Chỉ người tham gia hồ sơ được huỷ hoàn thành.')
    labels = dict(REOPEN_EDIT_STEPS)
    _require(edit_step in labels, 'Chọn công đoạn cần sửa.')
    reason = _require_text(reason, 'lý do mở lại')
    with transaction.atomic():
        if edit_step == 'design':
            for dv in dossier.design_versions.filter(is_current=True, state=DesignVersion.STATE_APPROVED):
                dv.state = DesignVersion.STATE_DRAFT
                dv.save(update_fields=['state', 'updated_at'])
        elif edit_step in ('technical', 'sample'):
            sv = dossier.current_sample_version()
            _require(sv is not None, 'Chưa có mẫu để mở công đoạn này.')
            if sv.state != SampleVersion.STATE_IN_PROGRESS:
                sv.state = SampleVersion.STATE_IN_PROGRESS
                sv.save(update_fields=['state', 'updated_at'])
        dossier.is_locked = False
        dossier.reopen_edit_step = edit_step
        _transition(
            dossier, Status.LIBRARY_REOPEN, user, 'completion_reopened',
            f'{_name(user)} huỷ hoàn thành, mở sửa «{labels[edit_step]}»: {reason}',
            revision=True, open_tasks=True, edit_step=edit_step,
        )
    nt.notify(
        dossier.approver, dossier, nt.KIND_INFO, 'Hồ sơ được mở lại sau khi vào Thư viện',
        f'{dossier.code} — sửa {labels[edit_step]}: {reason}', actor=user,
    )


def resubmit_after_reopen(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    """Chỉnh xong công đoạn đã chọn: chuyển thẳng sang Duyệt thiết kế."""
    _require(dossier.status == Status.LIBRARY_REOPEN, 'Hồ sơ không ở bước đang chỉnh sau hoàn thành.')
    _require(perms.is_participant(dossier, user), 'Chỉ người tham gia hồ sơ được gửi duyệt thiết kế.')
    step_label = dict(REOPEN_EDIT_STEPS).get(reopen_edit_step(dossier), 'hồ sơ')
    with transaction.atomic():
        current_designs = list(dossier.design_versions.filter(is_current=True))
        for dv in current_designs:
            if dv.state == DesignVersion.STATE_DRAFT:
                dv.state = DesignVersion.STATE_APPROVED
                dv.save(update_fields=['state', 'updated_at'])
        if dossier.approved_design_version_id is None and current_designs:
            dossier.approved_design_version = current_designs[0]
        for sv in dossier.sample_versions.filter(
            is_current=True,
            state__in=(SampleVersion.STATE_IN_PROGRESS, SampleVersion.STATE_PASSED),
        ):
            sv.state = SampleVersion.STATE_SUBMITTED
            sv.save(update_fields=['state', 'updated_at'])
        dossier.reopen_edit_step = ''
        _transition(
            dossier, Status.SAMPLE_EVAL_PENDING, user, 'reopen_submitted',
            f'{_name(user)} gửi duyệt thiết kế sau khi chỉnh «{step_label}».',
            due_at=due_at,
        )
    nt.notify(
        dossier.approver, dossier, nt.KIND_APPROVAL_REQUEST, 'Cần duyệt thiết kế',
        f'{dossier.code} — {dossier.name}', actor=user,
    )


def _library_doc_text(record: Handover, dossier: ProductDevelopment) -> tuple[str, str, str]:
    """Tên, mô tả và ảnh http lấy từ Thư viện tại thời điểm chuyển sản xuất."""
    from kho_san_pham.catalog_models import ProductStyle
    from kho_san_pham.models import Product

    style = ProductStyle.objects.filter(code__iexact=record.product_code).first()
    name = ((style.name if style else '') or dossier.name or record.product_code).strip()
    products = list(Product.objects.filter(style_code__iexact=record.product_code).order_by('pk'))
    parts = []
    image = ''
    for product in products:
        text = (product.description or '').strip()
        if text and text not in parts:
            parts.append(text)
        url = (product.image_url or '').strip()
        if not image and url.startswith('http'):
            image = url[:500]
    description = '\n\n'.join(parts) if parts else _tech_doc_description(dossier)
    return name[:255], description, image


def transfer_to_production(record: Handover, user):
    """Thư viện chuyển sản phẩm sang Sản xuất: tạo hồ sơ sản phẩm SX và sao tệp."""
    from kho_san_pham.library_release import style_transfer_block
    from san_xuat.models import ProductTechDoc

    dossier = record.dossier
    _require(dossier.status == Status.HANDED_OVER, 'Hồ sơ thiết kế không ở bước chờ chuyển sản xuất.')
    _require(not record.is_transferred, 'Sản phẩm đã được chuyển sang sản xuất.')
    block = style_transfer_block(record.product_code)
    _require(not block, block)
    _require(not ProductTechDoc.objects.filter(product_code__iexact=record.product_code).exists(),
             f'Mã {record.product_code} đã có hồ sơ sản phẩm bên Sản xuất.')
    pack = getattr(record.sample_version, 'tech_pack', None)
    main_material = ''
    if pack:
        main_line = pack.material_lines.filter(is_main=True).first()
        main_material = main_line.material_name if main_line else ''
    product_name, description, image_url = _library_doc_text(record, dossier)
    with transaction.atomic():
        tech_doc = ProductTechDoc.objects.create(
            product_code=record.product_code,
            product_name=product_name,
            product_image_url=image_url,
            season=dossier.collection[:80],
            main_material=main_material[:120],
            description=description,
            created_by=user,
        )
        copied = _copy_files_to_tech_doc(dossier, tech_doc, user)
        record.tech_doc = tech_doc
        record.transferred_at = timezone.now()
        record.transferred_by = user
        record.save(update_fields=['tech_doc', 'transferred_at', 'transferred_by'])
        log(dossier, user, 'transferred',
            f'{_name(user)} chuyển {record.product_code} từ Thư viện sang sản xuất — tạo hồ sơ sản phẩm SX '
            f'({copied} tệp).', tech_doc_id=tech_doc.pk)
        nt.notify_many(_owners(dossier), dossier, nt.KIND_INFO, f'{record.product_code} đã chuyển sang sản xuất',
                       f'{dossier.code} — {dossier.name}', actor=user)
    return tech_doc


def close_dossier(dossier: ProductDevelopment, user) -> None:
    _require(dossier.status == Status.HANDED_OVER, 'Chỉ đóng hồ sơ sau khi đã bàn giao.')
    _require(perms.can_work_as(dossier, user, Role.OWNER), 'Chỉ người phụ trách chính được đóng hồ sơ.')
    _require(dossier.handover.is_transferred, 'Sản phẩm chưa được chuyển sang sản xuất.')
    with transaction.atomic():
        dossier.closed_at = timezone.now()
        _transition(dossier, Status.CLOSED, user, 'closed', f'{_name(user)} đóng hồ sơ.', open_tasks=False)


# ---------------------------------------------------------------------------
# Tạm dừng / hủy / tiếp tục / thay đổi sau duyệt
# ---------------------------------------------------------------------------

# Quay lại các bước đã đi qua. Thứ tự đúng với nút trên hồ sơ.
REWIND_STEPS = (
    ('overview', 'Tổng quan', Status.DRAFT),
    ('design', 'Thiết kế', Status.DESIGNING),
    ('technical', 'Kỹ thuật', Status.TECHNICAL),
    ('sample', 'May mẫu', Status.SAMPLING),
)
_REWIND_RANK = {
    Status.DRAFT: 0,
    Status.BRIEF_NEEDS_INFO: 0,
    Status.BRIEF_PENDING: 0,
    Status.DESIGNING: 1,
    Status.DESIGN_REVISE: 1,
    Status.DESIGN_PENDING: 1,
    Status.TECHNICAL: 2,
    Status.TECHNICAL_REVISE: 2,
    Status.SAMPLING: 3,
    Status.SAMPLE_REVISE: 3,
    Status.SAMPLE_EVAL_PENDING: 4,
    Status.MASTER_PENDING: 4,
    Status.APPROVED: 4,
    Status.HANDED_OVER: 4,
    Status.LIBRARY_REOPEN: 4,
}


def _rewind_rank_seen(dossier: ProductDevelopment) -> int | None:
    """Bước xa nhất hồ sơ đã đứng, kể cả sau khi quay lại một bước trước."""
    ranks = []
    current = _REWIND_RANK.get(dossier.status)
    if current is not None:
        ranks.append(current)
    paused = _REWIND_RANK.get(getattr(dossier, 'paused_from_status', '') or '')
    if paused is not None:
        ranks.append(paused)
    if getattr(dossier, 'pk', None):
        seen = AuditLog.objects.filter(dossier=dossier).values_list('from_status', 'to_status')
        for origin, target in seen:
            for status in (origin, target):
                rank = _REWIND_RANK.get(status)
                if rank is not None:
                    ranks.append(rank)
    if not ranks:
        return None
    return max(ranks)


def backtrack_span(dossier: ProductDevelopment) -> tuple[int, int] | None:
    """Hồ sơ đã quay về bước trước: (bước hiện tại, bước xa nhất đã tới)."""
    cached = dossier.__dict__.get('_tk_backtrack')
    if cached is not None:
        return cached[0]
    current = _REWIND_RANK.get(dossier.status)
    furthest = _rewind_rank_seen(dossier)
    span = (current, furthest) if current is not None and furthest is not None and furthest > current else None
    dossier.__dict__['_tk_backtrack'] = (span,)
    return span


def design_reopened(dossier: ProductDevelopment, dv: DesignVersion) -> bool:
    """Quay về Tổng quan / Thiết kế thì mở lại phiên bản thiết kế đang nháp."""
    span = backtrack_span(dossier)
    if span is None or dv is None:
        return False
    current, _furthest = span
    return current <= 1 and dv.is_current and dv.is_editable


def tech_reopened(dossier: ProductDevelopment, sv: SampleVersion | None) -> bool:
    """Bước kỹ thuật đã tới, và hồ sơ đang đứng từ bước đó trở về trước."""
    span = backtrack_span(dossier)
    if span is None or sv is None:
        return False
    current, furthest = span
    return current <= 2 and furthest >= 2 and sv.is_editable


def sample_reopened(dossier: ProductDevelopment, sv: SampleVersion | None) -> bool:
    """Bước may mẫu đã tới, và hồ sơ đang đứng từ bước đó trở về trước."""
    span = backtrack_span(dossier)
    if span is None or sv is None:
        return False
    current, furthest = span
    return current <= 3 and furthest >= 3 and sv.is_editable


def rewind_choices(dossier: ProductDevelopment) -> list[tuple[str, str]]:
    """Chỉ các bước hồ sơ đã đi qua, trừ bước đang đứng.

    Chưa tới May mẫu thì không có mục May mẫu. Đã từng tới rồi quay về Thiết kế
    thì Kỹ thuật và May mẫu vẫn chọn được. Hồ sơ đã hoàn thành (Thư viện) không quay lại —
    dùng Huỷ hoàn thành và chọn đúng một công đoạn.
    """
    if dossier.status == Status.HANDED_OVER:
        return []
    current = _REWIND_RANK.get(dossier.status)
    furthest = _rewind_rank_seen(dossier)
    if current is None or furthest is None:
        return []
    return [
        (key, label)
        for index, (key, label, _status) in enumerate(REWIND_STEPS)
        if index <= furthest and index != current
    ]


def rewind_to(dossier: ProductDevelopment, user, *, step: str) -> None:
    """Đưa hồ sơ về một bước đã qua, mở lại phần đang khóa để sửa tiếp."""
    _require(perms.can_work_as(dossier, user, Role.OWNER), 'Chỉ người phụ trách chính được quay lại bước.')
    choices = dict(rewind_choices(dossier))
    _require(step in choices, 'Không quay lại được bước này.')
    try:
        handover = dossier.handover
    except Handover.DoesNotExist:
        handover = None
    if handover is not None and handover.is_transferred:
        raise WorkflowError('Sản phẩm đã chuyển sang sản xuất — không quay lại bước được.')
    target = next(status for key, _label, status in REWIND_STEPS if key == step)
    label = choices[step]
    with transaction.atomic():
        if step in ('overview', 'design'):
            dossier.design_versions.filter(
                is_current=True,
                state__in=(DesignVersion.STATE_APPROVED, DesignVersion.STATE_SUBMITTED),
            ).update(state=DesignVersion.STATE_DRAFT, updated_at=timezone.now())
            dossier.approved_design_version = None
        sv = dossier.current_sample_version()
        if step in ('technical', 'sample'):
            _require(sv is not None, 'Chưa có mẫu để quay lại bước này.')
        if sv is not None and sv.state != SampleVersion.STATE_IN_PROGRESS:
            sv.state = SampleVersion.STATE_IN_PROGRESS
            sv.save(update_fields=['state', 'updated_at'])
        dossier.is_locked = False
        dossier.approved_at = None
        dossier.final_sample_version = None
        _transition(
            dossier, target, user, 'rewound',
            f'{_name(user)} quay lại bước {label}.',
        )
        dossier.__dict__.pop('_tk_backtrack', None)


PAUSABLE = frozenset(Status.values) - {Status.DRAFT, Status.PAUSED, Status.HANDED_OVER, *FINAL_STATUSES}


def pause(dossier: ProductDevelopment, user, *, reason: str) -> None:
    _require(dossier.status in PAUSABLE, 'Không tạm dừng được hồ sơ ở trạng thái này.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được tạm dừng.')
    reason = _require_text(reason, 'lý do tạm dừng')
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=ApprovalStage.STOP, decision=ApprovalDecision.PAUSED,
                                comment=reason, decided_by=user)
        _cancel_all_open_tasks(dossier)
        dossier.paused_from_status = dossier.status
        dossier.stop_reason = reason
        _transition(dossier, Status.PAUSED, user, 'paused', f'{_name(user)} tạm dừng hồ sơ: {reason}',
                    open_tasks=False)
    nt.notify_many([dossier.owner, dossier.co_owner, dossier.proposer], dossier, nt.KIND_INFO, 'Hồ sơ bị tạm dừng', reason, actor=user)


def resume(dossier: ProductDevelopment, user, *, comment: str = '', due_at=None) -> None:
    _require(dossier.status == Status.PAUSED, 'Hồ sơ không ở trạng thái tạm dừng.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được cho tiếp tục.')
    target = dossier.paused_from_status or Status.DRAFT
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=ApprovalStage.STOP, decision=ApprovalDecision.RESUMED,
                                comment=comment, decided_by=user)
        dossier.paused_from_status = ''
        dossier.stop_reason = ''
        _transition(dossier, target, user, 'resumed',
                    f'{_name(user)} cho tiếp tục hồ sơ — quay lại «{Status(target).label}».', due_at=due_at)
        for cond in dossier.conditions.filter(done_at__isnull=True):
            _create_task(dossier, step=Status.APPROVED, role=Role.CONDITION, title=f'Điều kiện duyệt: {cond.content}',
                         assignee=cond.assignee, due_at=cond.due_at, is_main=False, actor=user, condition=cond)
        pending_fixes = SampleEvaluation.objects.filter(
            sample_version__dossier=dossier, fix_owner__isnull=False, fix_done_at__isnull=True,
        ).select_related('sample_version', 'fix_owner')
        for ev in pending_fixes:
            _open_fix_task(dossier, ev, actor=user)


def cancel(dossier: ProductDevelopment, user, *, reason: str, stage: str = ApprovalStage.STOP) -> None:
    raise WorkflowError('Hồ sơ không còn trạng thái hủy. Dùng Tạm dừng hoặc Xóa.')


CHANGE_TARGET_DESIGN = 'design'
CHANGE_TARGET_SAMPLE = 'sample'


def request_change_after_approval(dossier: ProductDevelopment, user, *, target: str, reason: str, due_at=None):
    """Quy tắc 4: hồ sơ đã duyệt chỉ sửa qua yêu cầu thay đổi — mở phiên bản mới, giữ nguyên bản đã duyệt."""
    _require(dossier.status == Status.APPROVED, 'Chỉ tạo yêu cầu thay đổi khi hồ sơ đã duyệt và chưa bàn giao.')
    _require(perms.is_dossier_approver(dossier, user) or perms.can_work_as(dossier, user, Role.OWNER),
             'Chỉ người phụ trách chính hoặc người duyệt được yêu cầu thay đổi.')
    reason = _require_text(reason, 'lý do thay đổi')
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=ApprovalStage.CHANGE, decision=ApprovalDecision.REQUEST_CHANGE,
                                comment=reason, design_version=dossier.approved_design_version,
                                sample_version=dossier.final_sample_version, decided_by=user)
        _cancel_all_open_tasks(dossier)
        dossier.is_locked = False
        dossier.approved_at = None
        if target == CHANGE_TARGET_DESIGN:
            new = _new_design_version(dossier, dossier.approved_design_version, user)
            new.change_note = ''
            new.save()
            dossier.approved_design_version = None
            dossier.final_sample_version = None
            new_status = Status.DESIGN_REVISE
        elif target == CHANGE_TARGET_SAMPLE:
            sv = dossier.final_sample_version
            new = _new_sample_version(dossier, sv.design_version, user, source=sv)
            dossier.final_sample_version = None
            new_status = Status.SAMPLE_REVISE
        else:
            raise WorkflowError('Chọn phần cần thay đổi: thiết kế hoặc mẫu.')
        dossier.conditions.filter(done_at__isnull=True).delete()
        _transition(dossier, new_status, user, 'change_requested',
                    f'{_name(user)} yêu cầu thay đổi sau duyệt → mở {new.label}: {reason}',
                    due_at=due_at, revision=True)


# ---------------------------------------------------------------------------
# Nhân sự, giá thành, tệp, trao đổi, công việc
# ---------------------------------------------------------------------------

def update_roles(dossier: ProductDevelopment, user, *, assignments: dict[str, object]) -> None:
    _require(perms.can_edit_roles(dossier, user), 'Chỉ người phụ trách chính hoặc người duyệt được đổi nhân sự.')
    assignments = dict(assignments)
    if 'owners' in assignments:
        people = list(assignments.pop('owners') or [])
        _require(people, 'Hồ sơ phải có người phụ trách chính.')
        _require(len(people) <= 2, 'Chỉ chọn tối đa 2 người phụ trách chính.')
        assignments[Role.OWNER] = people[0]
        assignments['co_owner'] = people[1] if len(people) > 1 else None
    for role, partner in ROLE_PARTNER.items():
        form_name = f'{role}s'
        if form_name not in assignments:
            continue
        people = list(assignments.pop(form_name) or [])
        _require(len(people) <= 2, f'Chỉ chọn tối đa 2 người cho {Role(role).label}.')
        assignments[role] = people[0] if people else None
        assignments[partner] = people[1] if len(people) > 1 else None
    new_approver = assignments.get(Role.APPROVER, dossier.approver)
    if new_approver is not None and new_approver != dossier.approver:
        _require(perms.has_approve_permission(new_approver), 'Người duyệt được chọn không có quyền duyệt hồ sơ.')
    if Role.OWNER in assignments:
        _require(assignments[Role.OWNER] is not None, 'Hồ sơ phải có người phụ trách chính.')
    changed = []
    with transaction.atomic():
        for role in DOSSIER_ROLE_FIELDS:
            if role not in assignments:
                continue
            new_user = assignments[role]
            old_user = getattr(dossier, role)
            if old_user == new_user:
                continue
            setattr(dossier, role, new_user)
            changed.append(f'{Role(role).label}: {_name(old_user) or "—"} → {_name(new_user) or "—"}')
            if new_user is None:
                continue
            open_tasks = [
                task for task in dossier.tasks.filter(state=Task.STATE_OPEN, role=role)
                if task.assignee_id is None or task.assignee_id == getattr(old_user, 'pk', None)
            ]
            if role == Role.OWNER and old_user is not None:
                unassigned_roles = [r for r in DOSSIER_ROLE_FIELDS if r != Role.OWNER
                                    and getattr(dossier, f'{r}_id') is None]
                open_tasks += list(dossier.tasks.filter(
                    state=Task.STATE_OPEN, role__in=unassigned_roles, assignee=old_user,
                ))
            for task in open_tasks:
                task.assignee = new_user
                task.accepted_at = None
                task.save(update_fields=['assignee', 'accepted_at'])
                nt.notify(new_user, dossier, _task_notify_kind(role, False), task.title,
                          f'{dossier.code} — {dossier.name} · Hạn {_fmt_due(task.due_at)}', actor=user)
            if not open_tasks and dossier.status != Status.DRAFT:
                nt.notify(new_user, dossier, nt.KIND_ASSIGNED, f'Bạn được giao: {Role(role).label}',
                          f'{dossier.code} — {dossier.name}', actor=user)
            if old_user is not None:
                nt.invalidate_badges(old_user)
        partner_labels = {'co_owner': 'Người phụ trách chính'}
        partner_labels.update({partner: Role(role).label for role, partner in ROLE_PARTNER.items()})
        for field, label in partner_labels.items():
            if field not in assignments:
                continue
            new_user = assignments[field]
            old_user = getattr(dossier, field)
            if old_user == new_user:
                continue
            setattr(dossier, field, new_user)
            changed.append(f'{label} (2): {_name(old_user) or "—"} → {_name(new_user) or "—"}')
            role = next((item for item, name in ROLE_PARTNER.items() if name == field), None)
            if role and old_user is not None and (new_user is None or old_user.pk != new_user.pk):
                if dossier.tasks.filter(
                    state=Task.STATE_OPEN, role=role, assignee=old_user, is_main=False,
                ).update(state=Task.STATE_CANCELLED, completed_at=timezone.now()):
                    nt.invalidate_badges(old_user)
            opened = None
            if role and new_user is not None and dossier.status not in (
                Status.DRAFT, Status.PAUSED, Status.HANDED_OVER, *FINAL_STATUSES,
            ):
                spec = next((item for item in _step_tasks(dossier, dossier.status) if item.role == role), None)
                if spec is not None:
                    due = dossier.tasks.filter(state=Task.STATE_OPEN, role=role).values_list('due_at', flat=True).first()
                    opened = _open_partner_task(
                        dossier, role, actor=user, due_at=due or sla.due_at_for(dossier.status),
                        revision=False, title=spec.title,
                    )
            if new_user is not None and dossier.status != Status.DRAFT and opened is None:
                nt.notify(new_user, dossier, nt.KIND_ASSIGNED, f'Bạn được giao: {label}',
                          f'{dossier.code} — {dossier.name}', actor=user)
            if old_user is not None:
                nt.invalidate_badges(old_user)
        if changed:
            dossier.save()
            log(dossier, user, 'roles_updated', f'{_name(user)} đổi nhân sự: ' + '; '.join(changed) + '.')
        if 'followers' in assignments:
            set_followers(dossier, assignments.get('followers'), user)


COSTING_FIELDS = ('estimated_cost', 'post_sample_cost', 'proposed_wholesale_price', 'proposed_retail_price', 'cost_note')


def update_costing(dossier: ProductDevelopment, user, *, fields: dict) -> None:
    if not test_edit_after_approval(dossier):
        _require(not dossier.is_locked, 'Hồ sơ đã khóa sau duyệt — thay đổi giá thành qua yêu cầu thay đổi.')
    _require(dossier.status not in (Status.DRAFT, *FINAL_STATUSES), 'Chưa cập nhật giá thành ở bước này.')
    _require(perms.can_work_as(dossier, user, Role.COSTING, Role.OWNER),
             'Chỉ Kế hoạch / Giá thành hoặc người phụ trách được cập nhật giá thành.')
    changed = []
    for key in COSTING_FIELDS:
        if key in fields and getattr(dossier, key) != fields[key]:
            setattr(dossier, key, fields[key])
            changed.append(key)
    if changed:
        dossier.save()
        log(dossier, user, 'costing_updated', f'{_name(user)} cập nhật giá thành.', fields=changed)


def _upload_allowed(dossier, user, kind: str, design_version, sample_version) -> str:
    """Trả về lý do chặn ('' = được phép)."""
    if dossier.status in FINAL_STATUSES:
        return 'Hồ sơ đã đóng / hủy.'
    if not perms.can_act(dossier, user):
        return 'Bạn không có quyền cập nhật hồ sơ.'
    if design_version is not None:
        if kind == AttachmentKind.COLORWAY:
            sv = dossier.current_sample_version()
            design_open = (
                _approved_design_editable(dossier, design_version)
                or design_reopened(dossier, design_version)
                or (
                    design_version.is_editable
                    and (
                        dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE)
                        or allows_reopen_design(dossier)
                    )
                )
            )
            tech_open = (
                sv is not None
                and sv.design_version_id == design_version.pk
                and sv.is_editable
                and (
                    (dossier.status in TECH_EDIT_STATUSES and dossier.status != Status.LIBRARY_REOPEN)
                    or allows_reopen_technical(dossier)
                    or _approved_sample_editable(dossier, sv)
                    or tech_reopened(dossier, sv)
                )
            )
            if design_open or tech_open:
                roles = []
                if design_open:
                    roles.extend((Role.DESIGNER, Role.OWNER))
                if tech_open:
                    roles.extend((Role.TECHNICIAN, Role.OWNER))
                return (
                    '' if perms.has_role(dossier, user, *roles)
                    else 'Chỉ người phụ trách thiết kế hoặc kỹ thuật được tải ảnh phối màu.'
                )
        if _approved_design_editable(dossier, design_version) or design_reopened(dossier, design_version):
            return '' if perms.has_role(dossier, user, Role.DESIGNER, Role.OWNER) else 'Chỉ Thiết kế / R&D tải tệp thiết kế.'
        design_status_ok = (
            dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE)
            or allows_reopen_design(dossier)
        )
        if not design_version.is_editable or not design_status_ok:
            return 'Phiên bản thiết kế đã gửi duyệt hoặc lưu trữ — không thêm tệp được.'
        return '' if perms.has_role(dossier, user, Role.DESIGNER, Role.OWNER) else 'Chỉ Thiết kế / R&D tải tệp thiết kế.'
    if sample_version is not None:
        if not sample_version.is_current:
            return 'Mẫu đã lưu trữ — không thêm tệp được.'
        tech_file = kind in (AttachmentKind.TECH_SPEC, AttachmentKind.PATTERN)
        if _approved_sample_editable(dossier, sample_version):
            if kind == AttachmentKind.EVALUATION:
                return 'Không thêm biên bản đánh giá sau khi hồ sơ đã duyệt.'
            roles = (Role.TECHNICIAN, Role.OWNER) if tech_file else (
                Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
            return '' if perms.has_role(dossier, user, *roles) else 'Bạn không phụ trách phần việc này.'
        if kind == AttachmentKind.EVALUATION:
            if dossier.status not in DESIGN_APPROVAL_STATUSES:
                return 'Chỉ tải biên bản đánh giá khi hồ sơ đang làm mẫu hoặc chờ duyệt thiết kế.'
            return '' if evaluator_roles_for(dossier, user) else 'Bạn không tham gia đánh giá mẫu.'
        if tech_file:
            allowed = dossier.status in TECH_EDIT_STATUSES and dossier.status != Status.LIBRARY_REOPEN
            reopen_ok = allows_reopen_technical(dossier)
        else:
            allowed = dossier.status in (Status.SAMPLING, Status.SAMPLE_REVISE)
            reopen_ok = allows_reopen_sample(dossier)
        reopened_file = tech_reopened(dossier, sample_version) if tech_file else sample_reopened(dossier, sample_version)
        if reopened_file or reopen_ok:
            roles = (Role.TECHNICIAN, Role.OWNER) if tech_file else (
                Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
            if reopen_ok and not sample_version.is_editable:
                return 'Mẫu đã gửi đánh giá — không thêm ảnh / tài liệu kỹ thuật được.'
            return '' if perms.has_role(dossier, user, *roles) else 'Bạn không phụ trách phần việc này.'
        if not sample_version.is_editable or not allowed:
            return 'Mẫu đã gửi đánh giá — không thêm ảnh / tài liệu kỹ thuật được.'
        roles = (Role.TECHNICIAN, Role.OWNER) if tech_file else (
            Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
        return '' if perms.has_role(dossier, user, *roles) else 'Bạn không phụ trách phần việc này.'
    if kind == AttachmentKind.REFERENCE:
        if dossier.status in (*FINAL_STATUSES, Status.HANDED_OVER):
            return 'Hồ sơ đã thêm vào Thư viện, hủy hoặc đóng — không bổ sung tài liệu tham khảo.'
        if dossier.status == Status.LIBRARY_REOPEN and not allows_reopen_overview(dossier):
            return 'Công đoạn đang mở không phải Tổng quan — không bổ sung tài liệu tham khảo.'
        return '' if perms.has_role(dossier, user, Role.PROPOSER, Role.OWNER) else 'Chỉ người đề xuất / phụ trách.'
    if kind == AttachmentKind.PRODUCT_PHOTO:
        if dossier.status in (*FINAL_STATUSES, Status.HANDED_OVER):
            return 'Hồ sơ đã thêm vào Thư viện, hủy hoặc đóng — không bổ sung ảnh sản phẩm.'
        if dossier.status == Status.LIBRARY_REOPEN and not allows_reopen_overview(dossier):
            return 'Công đoạn đang mở không phải Tổng quan — không bổ sung ảnh sản phẩm.'
        return '' if perms.is_participant(dossier, user) else 'Chỉ người tham gia hồ sơ được tải tệp.'
    if kind == AttachmentKind.COST:
        if dossier.is_locked and not test_edit_after_approval(dossier):
            return 'Hồ sơ đã khóa sau duyệt.'
        return '' if perms.has_role(dossier, user, Role.COSTING, Role.OWNER) else 'Chỉ Kế hoạch / Giá thành.'
    return '' if perms.is_participant(dossier, user) else 'Chỉ người tham gia hồ sơ được tải tệp.'


def can_upload(dossier, user, kind: str, design_version=None, sample_version=None) -> bool:
    return not _upload_allowed(dossier, user, kind, design_version, sample_version)


def upload_attachment(dossier: ProductDevelopment, user, *, uploaded_file, kind: str, design_version=None,
                      sample_version=None, colorway=None, note: str = '', tab: str = '') -> Attachment:
    from thiet_ke_sp.services.nas_layout import ensure_dossier_folders, folder_for_kind, folder_for_tab

    _require(kind in AttachmentKind.values, 'Loại tệp không hợp lệ.')
    reason = _upload_allowed(dossier, user, kind, design_version, sample_version)
    _require(not reason, reason)
    if kind == AttachmentKind.PRODUCT_PHOTO:
        _require(os.path.splitext(uploaded_file.name)[1].lower() in IMAGE_EXTENSIONS, 'Ảnh sản phẩm phải là tệp ảnh.')
    if kind == AttachmentKind.COLORWAY:
        _require(colorway is not None and design_version is not None and colorway.design_version_id == design_version.pk,
                 'Chọn colorway cho ảnh.')
    try:
        ensure_dossier_folders(dossier)
    except OSError:
        pass
    with transaction.atomic():
        if kind in SINGLE_CURRENT_KINDS:
            Attachment.objects.filter(
                dossier=dossier, design_version=design_version, sample_version=sample_version,
                kind=kind, is_current=True, is_deleted=False,
            ).update(is_current=False)
        att = Attachment(
            dossier=dossier, design_version=design_version, sample_version=sample_version,
            colorway=colorway, kind=kind, note=note[:255], uploaded_by=user,
            original_name=os.path.basename(uploaded_file.name)[:255], size=uploaded_file.size or 0,
        )
        att.nas_folder = folder_for_tab(tab) or folder_for_kind(kind)
        att.file.save(uploaded_file.name, uploaded_file, save=False)
        att.save()
        scope = design_version.label if design_version else (sample_version.label if sample_version else 'hồ sơ')
        log(dossier, user, 'file_uploaded',
            f'{_name(user)} tải lên {att.get_kind_display().lower()} «{att.display_name}» ({scope}).')
    return att


def delete_attachment(att: Attachment, user) -> None:
    dossier = att.dossier
    _require(not att.is_deleted, 'Tệp đã bị xóa.')
    reason = _upload_allowed(dossier, user, att.kind, att.design_version, att.sample_version)
    _require(not reason, reason)
    _require(att.uploaded_by_id == user.pk or perms.has_role(dossier, user, Role.OWNER),
             'Chỉ người tải lên hoặc người phụ trách được xóa tệp.')
    with transaction.atomic():
        att.is_deleted = True
        att.deleted_by = user
        att.deleted_at = timezone.now()
        att.save(update_fields=['is_deleted', 'deleted_by', 'deleted_at'])
        if att.kind in SINGLE_CURRENT_KINDS and att.is_current:
            previous = Attachment.objects.filter(
                dossier=dossier, design_version=att.design_version, sample_version=att.sample_version,
                kind=att.kind, is_deleted=False,
            ).exclude(pk=att.pk).order_by('-uploaded_at').first()
            if previous:
                previous.is_current = True
                previous.save(update_fields=['is_current'])
        log(dossier, user, 'file_deleted', f'{_name(user)} xóa tệp «{att.display_name}».')


def add_member(dossier: ProductDevelopment, user, *, member, group: str) -> DossierMember:
    _require(perms.can_edit_roles(dossier, user), 'Chỉ người phụ trách chính hoặc người duyệt được thêm thành viên.')
    _require(group in MemberGroup.values, 'Chọn nhóm thành viên.')
    _require(member is not None and member.is_active, 'Chọn người cần thêm.')
    label = MemberGroup(group).label
    with transaction.atomic():
        obj, created = DossierMember.objects.update_or_create(
            dossier=dossier, user=member, defaults={'group': group, 'added_by': user},
        )
        perms.reset_member_cache(dossier)
        log(dossier, user, 'member_added' if created else 'member_changed',
            f'{_name(user)} {"thêm" if created else "đổi nhóm"} thành viên {_name(member)} ({label}).')
    nt.invalidate_badges(member)
    nt.notify(member, dossier, nt.KIND_ASSIGNED, f'Bạn được thêm vào hồ sơ: {label}',
              f'{dossier.code} — {dossier.name}', actor=user)
    return obj


def remove_member(member: DossierMember, user) -> None:
    dossier = member.dossier
    _require(perms.can_edit_roles(dossier, user), 'Chỉ người phụ trách chính hoặc người duyệt được bớt thành viên.')
    with transaction.atomic():
        removed_user = member.user
        name, label = _name(removed_user), member.get_group_display()
        member.delete()
        perms.reset_member_cache(dossier)
        log(dossier, user, 'member_removed', f'{_name(user)} bớt thành viên {name} ({label}).')
    nt.invalidate_badges(removed_user)


STEP_KEYS = {key for key, _label, _statuses in STEPS}


def set_followers(dossier: ProductDevelopment, users, actor) -> None:
    """Gán nhiều người theo dõi. Chỉ những người có trong Thiết lập, cộng người đang theo dõi."""
    chosen = []
    seen = set()
    for person in users or []:
        if person is None or person.pk in seen:
            continue
        seen.add(person.pk)
        chosen.append(person)
    old = list(dossier.followers.select_related('profile'))
    old_ids = {person.pk for person in old}
    new_ids = {person.pk for person in chosen}
    if old_ids == new_ids:
        return
    allowed = set(sla.configured_role_ids().get(Role.FOLLOWER) or [])
    allowed.update(old_ids)
    blocked = [person for person in chosen if person.pk not in allowed]
    _require(not blocked, 'Có người theo dõi không nằm trong Thiết lập → Nhân sự phụ trách.')
    with transaction.atomic():
        dossier.followers.set(chosen)

        def _names(people) -> str:
            return ', '.join(_name(person) for person in people) or '—'

        log(dossier, actor, 'followers_updated',
            f'{_name(actor)} đổi người theo dõi: {_names(old)} → {_names(chosen)}.')
    added = [person for person in chosen if person.pk not in old_ids]
    removed = [person for person in old if person.pk not in new_ids]
    nt.notify_many(added, dossier, nt.KIND_ASSIGNED, 'Bạn được thêm theo dõi hồ sơ',
                   f'{dossier.code} — {dossier.name}', actor=actor)
    for person in removed:
        nt.invalidate_badges(person)


def add_comment(dossier: ProductDevelopment, user, *, body: str, design_version=None, sample_version=None,
                step: str = '') -> Comment:
    _require(perms.can_view_dossier(dossier, user), 'Bạn không có quyền xem hồ sơ.')
    _require(dossier.status not in FINAL_STATUSES, 'Hồ sơ đã hủy hoặc đóng — không trao đổi thêm.')
    body = _require_text(body, 'nội dung trao đổi')
    if design_version is not None or sample_version is not None:
        step = ''
    elif step:
        _require(step in STEP_KEYS, 'Bước trao đổi không hợp lệ.')
        from thiet_ke_sp.presenters import step_is_reached
        _require(step_is_reached(dossier, step), 'Chưa tới bước này.')
    comment = Comment.objects.create(
        dossier=dossier, author=user, body=body, design_version=design_version,
        sample_version=sample_version, step=step,
    )
    recipients = [dossier.owner, dossier.co_owner]
    task = current_main_task(dossier)
    if task and task.assignee:
        recipients.append(task.assignee)
    recipients.extend(dossier.followers.all())
    nt.notify_many(recipients, dossier, nt.KIND_COMMENT, f'{_name(user)} trao đổi trên {dossier.code}',
                   body[:200], actor=user)
    return comment


def accept_task(task: Task, user) -> None:
    _require(task.state == Task.STATE_OPEN, 'Công việc đã đóng.')
    _require(task.assignee_id == user.pk or perms.has_full_dossier_access(user),
             'Chỉ người được giao mới nhận việc.')
    if task.accepted_at is None:
        task.accepted_at = timezone.now()
        task.save(update_fields=['accepted_at'])
        log(task.dossier, user, 'task_accepted', f'{_name(user)} nhận việc «{task.title}».')


def set_delay_reason(task: Task, user, *, reason: str) -> None:
    _require(task.state == Task.STATE_OPEN, 'Công việc đã đóng.')
    _require(task.assignee_id == user.pk or perms.has_role(task.dossier, user, Role.OWNER),
             'Chỉ người được giao hoặc người phụ trách chính được cập nhật.')
    reason = _require_text(reason, 'nguyên nhân chậm')
    task.delay_reason = reason
    task.save(update_fields=['delay_reason'])
    log(task.dossier, user, 'task_delay', f'{_name(user)} ghi nhận nguyên nhân chậm «{task.title}»: {reason}')


def update_task_due(task: Task, user, *, due_at) -> None:
    dossier = task.dossier
    _require(task.state == Task.STATE_OPEN, 'Công việc đã đóng.')
    _require(perms.has_role(dossier, user, Role.OWNER) or perms.is_dossier_approver(dossier, user),
             'Chỉ người phụ trách chính hoặc người duyệt được đổi hạn.')
    _require(due_at is not None, 'Nhập hạn mới.')
    old = task.due_at
    task.due_at = due_at
    task.save(update_fields=['due_at'])
    log(dossier, user, 'task_due_changed',
        f'{_name(user)} đổi hạn «{task.title}»: {_fmt_due(old) or "—"} → {_fmt_due(due_at)}.')
    if task.assignee:
        nt.notify(task.assignee, dossier, nt.KIND_INFO, f'Đổi hạn: {task.title}', f'Hạn mới {_fmt_due(due_at)}',
                  actor=user)


def delete_draft(dossier: ProductDevelopment, user) -> None:
    _require(perms.can_delete_dossier(dossier, user), 'Bạn không có quyền xóa hồ sơ này.')
    dossier.delete()
