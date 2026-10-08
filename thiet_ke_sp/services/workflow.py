"""Luồng nghiệp vụ hồ sơ thiết kế sản phẩm.

Mọi thay đổi trạng thái đi qua module này để luôn: kiểm tra quyền + điều kiện chặn,
đóng/mở công việc theo bước, ghi nhật ký và gửi thông báo trong portal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from thiet_ke_sp import permissions as perms
from thiet_ke_sp.models import (
    DOSSIER_ROLE_FIELDS,
    FINAL_STATUSES,
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
    DossierSequence,
    EvaluationItem,
    EvaluatorRole,
    Handover,
    HandoverReceipt,
    MaterialLine,
    ProductDevelopment,
    ReceivingDepartment,
    Role,
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


def _step_tasks(dossier: ProductDevelopment, status: str) -> list[StepTask]:
    dv = dossier.current_design_version()
    sv = dossier.current_sample_version()
    dv_label = dv.label if dv else ''
    sv_label = sv.label if sv else ''
    mapping = {
        Status.BRIEF_PENDING: [StepTask(Role.APPROVER, 'Duyệt đề bài', fallback_owner=False)],
        Status.BRIEF_NEEDS_INFO: [StepTask(Role.PROPOSER, 'Bổ sung đề bài theo yêu cầu')],
        Status.DESIGNING: [StepTask(Role.DESIGNER, f'Thiết kế phiên bản {dv_label}')],
        Status.DESIGN_REVISE: [StepTask(Role.DESIGNER, f'Chỉnh thiết kế — phiên bản {dv_label}')],
        Status.DESIGN_PENDING: [StepTask(Role.APPROVER, f'Duyệt thiết kế {dv_label}', fallback_owner=False)],
        Status.SAMPLING: [
            StepTask(Role.SAMPLE_MAKER, f'Làm mẫu {sv_label}'),
            StepTask(Role.TECHNICIAN, f'Lập thông số kỹ thuật & BOM mẫu {sv_label}', is_main=False),
        ],
        Status.SAMPLE_REVISE: [
            StepTask(Role.SAMPLE_MAKER, f'Sửa mẫu — lần {sv_label}'),
            StepTask(Role.TECHNICIAN, f'Cập nhật thông số kỹ thuật & BOM mẫu {sv_label}', is_main=False),
        ],
        Status.SAMPLE_EVAL_PENDING: [
            StepTask(Role.OWNER, f'Tổng hợp đánh giá mẫu {sv_label} và trình duyệt mẫu chuẩn'),
            StepTask(Role.QA, f'Đánh giá mẫu {sv_label} (QA/QC)', is_main=False, fallback_owner=False),
            StepTask(Role.COSTING, f'Đánh giá giá thành mẫu {sv_label}', is_main=False, fallback_owner=False),
        ],
        Status.MASTER_PENDING: [StepTask(Role.APPROVER, f'Duyệt mẫu chuẩn {sv_label}', fallback_owner=False)],
        Status.APPROVED: [StepTask(Role.OWNER, 'Bàn giao hồ sơ cho sản xuất')],
        Status.HANDED_OVER: [StepTask(Role.OWNER, 'Theo dõi xác nhận nhận bàn giao và đóng hồ sơ')],
    }
    return mapping.get(status, [])


def _role_assignee(dossier: ProductDevelopment, role: str, fallback_owner: bool):
    if role == Role.PROPOSER:
        return dossier.proposer
    user = dossier.role_user(role)
    if user is None and fallback_owner:
        user = dossier.owner
    return user


def _task_notify_kind(role: str, revision: bool) -> str:
    if role == Role.APPROVER:
        return nt.KIND_APPROVAL_REQUEST
    return nt.KIND_REVISION if revision else nt.KIND_TASK


def _create_task(dossier, *, step, role, title, assignee, due_at, is_main=True, actor=None,
                 notify_kind=nt.KIND_TASK, receipt=None, condition=None) -> Task:
    task = Task.objects.create(
        dossier=dossier, step=step, role=role, title=title, is_main=is_main,
        assignee=assignee, due_at=due_at, receipt=receipt, condition=condition,
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
        if assignee is None and not spec.is_main:
            continue
        created.append(_create_task(
            dossier, step=status, role=spec.role, title=spec.title, assignee=assignee,
            due_at=due_at, is_main=spec.is_main, actor=actor,
            notify_kind=_task_notify_kind(spec.role, revision),
        ))
    return created


def _close_step_tasks(dossier: ProductDevelopment, step: str, actor) -> None:
    now = timezone.now()
    open_tasks = dossier.tasks.filter(step=step, state=Task.STATE_OPEN, receipt__isnull=True, condition__isnull=True)
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


def current_main_task(dossier: ProductDevelopment) -> Task | None:
    return (
        dossier.tasks.filter(state=Task.STATE_OPEN, is_main=True, receipt__isnull=True, condition__isnull=True)
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
    ('product_type', 'loại sản phẩm'),
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
            dossier.owner = user
        dossier.save()
        log(dossier, user, 'created', f'{_name(user)} tạo đề xuất sản phẩm.', to_status=Status.DRAFT)
        if submit:
            submit_brief(dossier, user)
    return dossier


def update_brief(dossier: ProductDevelopment, user, *, fields: dict) -> None:
    _require(perms.can_edit_brief(dossier, user), 'Chỉ sửa đề bài khi hồ sơ còn nháp hoặc đang được yêu cầu bổ sung.')
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
    _require(perms.can_edit_brief(dossier, user), 'Chỉ người đề xuất hoặc người phụ trách được gửi duyệt đề bài.')
    missing = [label for field, label in BRIEF_REQUIRED if not getattr(dossier, field, None)]
    _require(not missing, 'Chưa đủ thông tin đề bài: ' + ', '.join(missing) + '.')
    _require(perms.has_approve_permission(dossier.approver), 'Người duyệt được chọn không có quyền duyệt hồ sơ.')
    with transaction.atomic():
        dossier.submitted_at = timezone.now()
        resubmit = dossier.status == Status.BRIEF_NEEDS_INFO
        _transition(
            dossier, Status.BRIEF_PENDING, user, 'brief_submitted',
            f'{_name(user)} {"gửi lại" if resubmit else "gửi"} đề bài chờ duyệt.', due_at=due_at,
        )


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

def _require_design_editable(dossier, dv: DesignVersion, user) -> None:
    _require(dv.dossier_id == dossier.pk, 'Phiên bản không thuộc hồ sơ.')
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


def add_colorway(dv: DesignVersion, user, *, name: str, color_codes: str, note: str = '') -> Colorway:
    _require_design_editable(dv.dossier, dv, user)
    order = dv.colorways.count() + 1
    cw = Colorway.objects.create(
        design_version=dv, name=_require_text(name, 'tên phối màu'),
        color_codes=_require_text(color_codes, 'mã màu'), note=note, sort_order=order,
    )
    log(dv.dossier, user, 'colorway_added', f'{_name(user)} thêm colorway «{cw.name}» vào {dv.label}.')
    return cw


def delete_colorway(cw: Colorway, user) -> None:
    dv = cw.design_version
    _require_design_editable(dv.dossier, dv, user)
    Attachment.objects.filter(colorway=cw, is_deleted=False).update(
        is_deleted=True, deleted_by=user, deleted_at=timezone.now(),
    )
    log(dv.dossier, user, 'colorway_deleted', f'{_name(user)} xóa colorway «{cw.name}» khỏi {dv.label}.')
    cw.delete()


def _live(qs):
    return qs.filter(is_deleted=False, is_current=True)


def design_checklist(dv: DesignVersion | None) -> list[tuple[str, bool]]:
    """Quy tắc 1: điều kiện gửi duyệt thiết kế."""
    if dv is None:
        return [('Có phiên bản thiết kế', False)]
    atts = _live(dv.attachments.all())
    kinds = set(atts.values_list('kind', flat=True))
    colorways = list(dv.colorways.all())
    with_image = set(atts.filter(kind=AttachmentKind.COLORWAY).values_list('colorway_id', flat=True))
    return [
        ('Ảnh mặt trước', AttachmentKind.FRONT in kinds),
        ('Ảnh mặt sau', AttachmentKind.BACK in kinds),
        ('Ít nhất một colorway có mã màu', bool(colorways) and all(c.color_codes.strip() for c in colorways)),
        ('Mỗi colorway có ảnh', bool(colorways) and all(c.pk in with_image for c in colorways)),
        ('File thiết kế gốc', AttachmentKind.DESIGN_SOURCE in kinds),
    ]


def submit_design(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    _require(dossier.status in (Status.DESIGNING, Status.DESIGN_REVISE), 'Hồ sơ không ở bước thiết kế.')
    dv = dossier.current_design_version()
    _require(dv is not None, 'Chưa có phiên bản thiết kế.')
    _require_design_editable(dossier, dv, user)
    missing = [label for label, ok in design_checklist(dv) if not ok]
    _require(not missing, 'Chưa đủ điều kiện gửi duyệt thiết kế: ' + ', '.join(missing) + '.')
    if dv.version_no > 1:
        _require(bool(dv.change_note.strip()), 'Nhập nội dung thay đổi so với phiên bản trước.')
    with transaction.atomic():
        dv.state = DesignVersion.STATE_SUBMITTED
        dv.save(update_fields=['state', 'updated_at'])
        _transition(dossier, Status.DESIGN_PENDING, user, 'design_submitted',
                    f'{_name(user)} gửi duyệt thiết kế {dv.label}.', due_at=due_at, version=dv.label)


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


def _new_design_version(dossier, source: DesignVersion, user) -> DesignVersion:
    source_qs = DesignVersion.objects.filter(dossier=dossier)
    source_qs.update(is_current=False)
    new = DesignVersion.objects.create(
        dossier=dossier,
        version_no=(source_qs.order_by('-version_no').values_list('version_no', flat=True).first() or 0) + 1,
        style_description=source.style_description,
        pattern_description=source.pattern_description,
        logo_placement=source.logo_placement,
        materials=source.materials,
        highlights=source.highlights,
        created_by=user,
    )
    colorway_map = {}
    for cw in source.colorways.all():
        colorway_map[cw.pk] = Colorway.objects.create(
            design_version=new, name=cw.name, color_codes=cw.color_codes, note=cw.note, sort_order=cw.sort_order,
        )
    _clone_attachments(source.attachments.all(), dossier=dossier, design_version=new, colorway_map=colorway_map)
    return new


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
            for field in ('size_spec', 'cutting_req', 'sewing_req', 'decoration_req', 'finishing_req', 'packing_req'):
                setattr(pack, field, getattr(old_pack, field))
            pack.save()
            MaterialLine.objects.bulk_create([
                MaterialLine(
                    tech_pack=pack, material_name=line.material_name, is_main=line.is_main, spec=line.spec,
                    consumption=line.consumption, unit=line.unit, unit_price=line.unit_price,
                    sort_order=line.sort_order,
                )
                for line in old_pack.material_lines.all()
            ])
        _clone_attachments(
            source.attachments.filter(kind=AttachmentKind.TECH_SPEC), dossier=dossier, sample_version=new,
        )
    return new


def decide_design(dossier: ProductDevelopment, user, *, decision: str, comment: str = '', due_at=None) -> None:
    _require(dossier.status == Status.DESIGN_PENDING, 'Hồ sơ không ở bước chờ duyệt thiết kế.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    dv = dossier.current_design_version()
    with transaction.atomic():
        if decision == ApprovalDecision.APPROVED:
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.DESIGN, decision=decision,
                                    comment=comment, design_version=dv, decided_by=user)
            dv.state = DesignVersion.STATE_APPROVED
            dv.save(update_fields=['state', 'updated_at'])
            dossier.approved_design_version = dv
            _new_sample_version(dossier, dv, user)
            _transition(dossier, Status.SAMPLING, user, 'design_approved',
                        f'{_name(user)} duyệt thiết kế {dv.label}, chuyển sang làm mẫu.',
                        due_at=due_at, version=dv.label, comment=comment)
            nt.notify_many([dossier.owner, dossier.designer, dossier.proposer], dossier, nt.KIND_APPROVED,
                           f'Thiết kế {dv.label} đã được duyệt', f'{dossier.code} — {dossier.name}', actor=user)
        elif decision == ApprovalDecision.REQUEST_CHANGE:
            comment = _require_text(comment, 'nội dung yêu cầu chỉnh sửa')
            Approval.objects.create(dossier=dossier, stage=ApprovalStage.DESIGN, decision=decision,
                                    comment=comment, design_version=dv, decided_by=user)
            Comment.objects.create(dossier=dossier, design_version=dv, author=user, body=comment,
                                   is_revision_request=True)
            dv.state = DesignVersion.STATE_REJECTED
            dv.save(update_fields=['state', 'updated_at'])
            new = _new_design_version(dossier, dv, user)
            _transition(dossier, Status.DESIGN_REVISE, user, 'design_returned',
                        f'{_name(user)} yêu cầu chỉnh thiết kế {dv.label} → mở {new.label}: {comment}',
                        due_at=due_at, revision=True, version=new.label)
        else:
            raise WorkflowError('Quyết định không hợp lệ.')


# ---------------------------------------------------------------------------
# Bước 5–6: làm mẫu, hồ sơ kỹ thuật, đánh giá mẫu
# ---------------------------------------------------------------------------

def _require_sample_editable(dossier, sv: SampleVersion, user, *roles) -> None:
    _require(sv.dossier_id == dossier.pk, 'Mẫu không thuộc hồ sơ.')
    _require(dossier.status in (Status.SAMPLING, Status.SAMPLE_REVISE) and sv.is_editable,
             'Mẫu này đã gửi đánh giá hoặc đã lưu trữ — không sửa được.')
    _require(perms.can_work_as(dossier, user, *roles), 'Bạn không phụ trách phần việc này trên hồ sơ.')


def save_sample(sv: SampleVersion, user, *, fields: dict) -> None:
    dossier = sv.dossier
    _require_sample_editable(dossier, sv, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
    for key, value in fields.items():
        setattr(sv, key, value)
    sv.save()
    log(dossier, user, 'sample_saved', f'{_name(user)} cập nhật tiến độ mẫu {sv.label}.')


def save_tech_pack(sv: SampleVersion, user, *, fields: dict, lines: list[dict]) -> None:
    dossier = sv.dossier
    _require_sample_editable(dossier, sv, user, Role.TECHNICIAN, Role.OWNER)
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
    _require(dossier.status in (Status.SAMPLING, Status.SAMPLE_REVISE), 'Hồ sơ không ở bước làm mẫu.')
    sv = dossier.current_sample_version()
    _require(sv is not None, 'Chưa có phiên bản mẫu.')
    _require_sample_editable(dossier, sv, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
    _require(_live(sv.attachments.filter(kind=AttachmentKind.SAMPLE_PHOTO)).exists(),
             'Tải lên ít nhất một ảnh mẫu thực tế trước khi gửi đánh giá.')
    if sv.version_no > 1:
        _require(bool(sv.change_note.strip()), 'Nhập nội dung sửa so với lần mẫu trước.')
    with transaction.atomic():
        sv.state = SampleVersion.STATE_SUBMITTED
        sv.completed_date = sv.completed_date or timezone.localdate()
        sv.save(update_fields=['state', 'completed_date', 'updated_at'])
        _transition(dossier, Status.SAMPLE_EVAL_PENDING, user, 'sample_submitted',
                    f'{_name(user)} hoàn thành mẫu {sv.label}, gửi đánh giá.', due_at=due_at, version=sv.label)


def evaluator_roles_for(dossier: ProductDevelopment, user) -> list[str]:
    if perms.is_admin(user):
        return list(EvaluatorRole.values)
    roles = perms.user_roles(dossier, user)
    result = []
    if Role.QA in roles:
        result.append(EvaluatorRole.QA)
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
    _require(dossier.status == Status.SAMPLE_EVAL_PENDING, 'Hồ sơ không ở bước đánh giá mẫu.')
    _require(perms.can_update(user), 'Bạn không có quyền cập nhật hồ sơ.')
    _require(role in evaluator_roles_for(dossier, user), 'Bạn không được đánh giá mẫu với vai trò này.')
    sv = dossier.current_sample_version()
    _require(sv is not None and sv.state == SampleVersion.STATE_SUBMITTED, 'Không có mẫu đang chờ đánh giá.')
    if result == SampleEvaluation.RESULT_FAIL:
        defects = _require_text(defects, 'lỗi / nội dung phải chỉnh')
    with transaction.atomic():
        ev = SampleEvaluation.objects.create(
            sample_version=sv, role=role, evaluator=user, result=result, conclusion=conclusion,
            defects=defects, fix_owner=fix_owner, fix_due=fix_due,
        )
        EvaluationItem.objects.bulk_create([
            EvaluationItem(evaluation=ev, criterion=criterion, result=res, note=note)
            for criterion, (res, note) in items.items()
        ])
        task_role = {EvaluatorRole.QA: Role.QA, EvaluatorRole.COSTING: Role.COSTING}.get(role)
        if task_role:
            _complete_user_tasks(dossier, user, step=Status.SAMPLE_EVAL_PENDING, role=task_role)
        log(dossier, user, 'sample_evaluated',
            f'{_name(user)} đánh giá mẫu {sv.label} ({EvaluatorRole(role).label}): {ev.get_result_display()}.')
    if dossier.owner_id and dossier.owner_id != user.pk:
        nt.notify(dossier.owner, dossier, nt.KIND_INFO, f'Có đánh giá mới cho mẫu {sv.label}',
                  f'{_name(user)} — {ev.get_result_display()}', actor=user)
    return ev


def request_sample_fix(dossier: ProductDevelopment, user, *, comment: str, due_at=None) -> None:
    if dossier.status == Status.SAMPLE_EVAL_PENDING:
        _require(perms.can_work_as(dossier, user, Role.OWNER), 'Chỉ người phụ trách chính được yêu cầu sửa mẫu.')
    elif dossier.status == Status.MASTER_PENDING:
        _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    else:
        raise WorkflowError('Hồ sơ không ở bước đánh giá / duyệt mẫu.')
    comment = _require_text(comment, 'nội dung cần sửa mẫu')
    sv = dossier.current_sample_version()
    with transaction.atomic():
        if dossier.status == Status.MASTER_PENDING:
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


def master_checklist(dossier: ProductDevelopment) -> list[tuple[str, bool]]:
    """Quy tắc 2: điều kiện trình duyệt mẫu chuẩn."""
    sv = dossier.current_sample_version()
    if sv is None:
        return [('Có mẫu', False)]
    pack = getattr(sv, 'tech_pack', None)
    atts = _live(sv.attachments.all())
    evaluations = list(sv.evaluations.all())
    return [
        ('Bảng thông số kỹ thuật', bool(pack and pack.size_spec.strip())
         or atts.filter(kind=AttachmentKind.TECH_SPEC).exists()),
        ('BOM có nguyên phụ liệu chính', bool(pack and pack.material_lines.filter(is_main=True).exists())),
        ('Ảnh mẫu thực tế', atts.filter(kind=AttachmentKind.SAMPLE_PHOTO).exists()),
        ('QA/QC đánh giá Đạt', any(e.role == EvaluatorRole.QA and e.result == SampleEvaluation.RESULT_PASS
                                   for e in evaluations)),
        ('Không còn đánh giá Không đạt', not any(e.result == SampleEvaluation.RESULT_FAIL for e in evaluations)),
        ('Giá thành dự kiến hoặc sau mẫu', dossier.estimated_cost is not None or dossier.post_sample_cost is not None),
    ]


def submit_master(dossier: ProductDevelopment, user, *, due_at=None) -> None:
    _require(dossier.status == Status.SAMPLE_EVAL_PENDING, 'Hồ sơ không ở bước đánh giá mẫu.')
    _require(perms.can_work_as(dossier, user, Role.OWNER), 'Chỉ người phụ trách chính được trình duyệt mẫu chuẩn.')
    missing = [label for label, ok in master_checklist(dossier) if not ok]
    _require(not missing, 'Chưa đủ điều kiện trình duyệt mẫu chuẩn: ' + ', '.join(missing) + '.')
    sv = dossier.current_sample_version()
    with transaction.atomic():
        _transition(dossier, Status.MASTER_PENDING, user, 'master_submitted',
                    f'{_name(user)} trình duyệt mẫu chuẩn {sv.label}.', due_at=due_at, version=sv.label)


# ---------------------------------------------------------------------------
# Bước 7: duyệt mẫu chuẩn (có điều kiện)
# ---------------------------------------------------------------------------

def official_code_conflict(code: str, *, exclude_dossier_id=None) -> str:
    from san_xuat.models import ProductTechDoc

    code = (code or '').strip()
    if not code:
        return ''
    if ProductTechDoc.objects.filter(product_code__iexact=code).exists():
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
    _require(dossier.status == Status.MASTER_PENDING, 'Hồ sơ không ở bước chờ duyệt mẫu chuẩn.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được ra quyết định.')
    code = _require_text(official_code, 'mã sản phẩm chính thức').upper()
    conflict = official_code_conflict(code, exclude_dossier_id=dossier.pk)
    _require(not conflict, conflict)
    conditions = conditions or []
    for cond in conditions:
        _require(bool(cond.content.strip()) and cond.assignee is not None and cond.due_at is not None,
                 'Mỗi điều kiện cần nội dung, người xử lý và hạn.')
    sv = dossier.current_sample_version()
    decision = ApprovalDecision.APPROVED_CONDITIONAL if conditions else ApprovalDecision.APPROVED
    with transaction.atomic():
        approval = Approval.objects.create(
            dossier=dossier, stage=ApprovalStage.MASTER, decision=decision, comment=comment,
            design_version=sv.design_version, sample_version=sv, decided_by=user,
        )
        sv.state = SampleVersion.STATE_PASSED
        sv.save(update_fields=['state', 'updated_at'])
        dossier.official_product_code = code
        dossier.final_sample_version = sv
        dossier.approved_design_version = sv.design_version
        dossier.approved_at = timezone.now()
        dossier.is_locked = True
        summary = f'{_name(user)} duyệt mẫu chuẩn {sv.label} — mã chính thức {code}'
        if conditions:
            summary += f', kèm {len(conditions)} điều kiện'
        _transition(dossier, Status.APPROVED, user, 'master_approved', summary + '.', due_at=due_at,
                    official_code=code, comment=comment)
        for cond in conditions:
            obj = ApprovalCondition.objects.create(
                dossier=dossier, approval=approval, content=cond.content.strip(),
                assignee=cond.assignee, due_at=cond.due_at,
            )
            _create_task(dossier, step=Status.APPROVED, role=Role.CONDITION,
                         title=f'Điều kiện duyệt: {obj.content}', assignee=obj.assignee, due_at=obj.due_at,
                         is_main=False, actor=user, condition=obj)
    nt.notify_many([dossier.owner, dossier.designer, dossier.technician, dossier.proposer], dossier,
                   nt.KIND_APPROVED, f'Mẫu chuẩn {sv.label} đã được duyệt sản xuất',
                   f'{dossier.code} — {dossier.name} · Mã {code}', actor=user)


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
    nt.notify(dossier.owner, dossier, nt.KIND_INFO, 'Điều kiện duyệt đã hoàn thành', cond.content, actor=user)


# ---------------------------------------------------------------------------
# Bước 8: bàn giao sản xuất
# ---------------------------------------------------------------------------

def handover_checklist(dossier: ProductDevelopment) -> list[tuple[str, bool]]:
    """Quy tắc 3: điều kiện bàn giao sản xuất."""
    return [
        ('Đã duyệt mẫu chuẩn', dossier.status in (Status.APPROVED, Status.HANDED_OVER, Status.CLOSED)),
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
    source = list(_live(dv.attachments.all()).order_by('kind', 'pk')) + list(
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


def handover(dossier: ProductDevelopment, user, *, receivers: dict[str, object], note: str = '', due_at=None):
    from san_xuat.models import ProductTechDoc

    _require(dossier.status == Status.APPROVED, 'Hồ sơ chưa được duyệt sản xuất hoặc đã bàn giao.')
    _require(perms.can_work_as(dossier, user, Role.OWNER, Role.TECHNICIAN),
             'Chỉ người phụ trách chính hoặc Kỹ thuật được bàn giao.')
    missing = [label for label, ok in handover_checklist(dossier) if not ok]
    _require(not missing, 'Chưa đủ điều kiện bàn giao: ' + ', '.join(missing) + '.')
    missing_dept = [ReceivingDepartment(d).label for d in ReceivingDepartment.values if not receivers.get(d)]
    _require(not missing_dept, 'Chọn người nhận cho: ' + ', '.join(missing_dept) + '.')
    conflict = official_code_conflict(dossier.official_product_code, exclude_dossier_id=dossier.pk)
    _require(not conflict, conflict)
    pack = getattr(dossier.final_sample_version, 'tech_pack', None)
    main_material = ''
    if pack:
        main_line = pack.material_lines.filter(is_main=True).first()
        main_material = main_line.material_name if main_line else ''
    due_at = due_at or sla.due_at_for(Status.HANDED_OVER)
    with transaction.atomic():
        tech_doc = ProductTechDoc.objects.create(
            product_code=dossier.official_product_code,
            product_name=dossier.name,
            season=dossier.collection[:80],
            main_material=main_material[:120],
            description=_tech_doc_description(dossier),
            created_by=user,
        )
        copied = _copy_files_to_tech_doc(dossier, tech_doc, user)
        record = Handover.objects.create(
            dossier=dossier, product_code=dossier.official_product_code,
            design_version=dossier.approved_design_version, sample_version=dossier.final_sample_version,
            tech_doc=tech_doc, note=note, handed_by=user,
        )
        _transition(dossier, Status.HANDED_OVER, user, 'handed_over',
                    f'{_name(user)} bàn giao sản xuất — tạo hồ sơ kỹ thuật SX {tech_doc.product_code} '
                    f'({copied} tệp).', due_at=due_at, tech_doc_id=tech_doc.pk)
        for dept in ReceivingDepartment.values:
            receipt = HandoverReceipt.objects.create(handover=record, department=dept, receiver=receivers[dept])
            _create_task(dossier, step=Status.HANDED_OVER, role=Role.RECEIVER,
                         title=f'Xác nhận nhận bàn giao ({ReceivingDepartment(dept).label})',
                         assignee=receipt.receiver, due_at=due_at, is_main=False, actor=user,
                         notify_kind=nt.KIND_HANDOVER, receipt=receipt)
    return record


def confirm_receipt(receipt: HandoverReceipt, user, *, note: str = '') -> None:
    dossier = receipt.handover.dossier
    _require(not receipt.is_confirmed, 'Bộ phận này đã xác nhận.')
    _require(dossier.status == Status.HANDED_OVER, 'Hồ sơ không ở bước chờ xác nhận bàn giao.')
    _require(receipt.receiver_id == user.pk or perms.is_admin(user), 'Chỉ người nhận được chỉ định mới xác nhận.')
    with transaction.atomic():
        receipt.confirmed_at = timezone.now()
        receipt.confirmed_by = user
        receipt.note = note.strip()[:255]
        receipt.save()
        receipt.tasks.filter(state=Task.STATE_OPEN).update(
            state=Task.STATE_DONE, completed_at=receipt.confirmed_at, completed_by=user,
        )
        nt.invalidate_badges(user)
        log(dossier, user, 'receipt_confirmed',
            f'{_name(user)} xác nhận nhận bàn giao ({receipt.get_department_display()}).')
    nt.notify(dossier.owner, dossier, nt.KIND_INFO,
              f'{receipt.get_department_display()} đã nhận bàn giao', f'{dossier.code} — {dossier.name}', actor=user)


def close_dossier(dossier: ProductDevelopment, user) -> None:
    _require(dossier.status == Status.HANDED_OVER, 'Chỉ đóng hồ sơ sau khi đã bàn giao.')
    _require(perms.can_work_as(dossier, user, Role.OWNER), 'Chỉ người phụ trách chính được đóng hồ sơ.')
    pending = dossier.handover.receipts.filter(confirmed_at__isnull=True)
    _require(not pending.exists(), 'Còn bộ phận chưa xác nhận nhận bàn giao: '
             + ', '.join(r.get_department_display() for r in pending) + '.')
    with transaction.atomic():
        dossier.closed_at = timezone.now()
        _transition(dossier, Status.CLOSED, user, 'closed', f'{_name(user)} đóng hồ sơ.', open_tasks=False)


# ---------------------------------------------------------------------------
# Tạm dừng / hủy / tiếp tục / thay đổi sau duyệt
# ---------------------------------------------------------------------------

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
    nt.notify_many([dossier.owner, dossier.proposer], dossier, nt.KIND_INFO, 'Hồ sơ bị tạm dừng', reason, actor=user)


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


def cancel(dossier: ProductDevelopment, user, *, reason: str, stage: str = ApprovalStage.STOP) -> None:
    _require(dossier.status not in (*FINAL_STATUSES, Status.DRAFT, Status.HANDED_OVER),
             'Không hủy được hồ sơ ở trạng thái này.')
    _require(perms.is_dossier_approver(dossier, user), 'Chỉ người duyệt của hồ sơ được hủy.')
    reason = _require_text(reason, 'lý do hủy')
    with transaction.atomic():
        Approval.objects.create(dossier=dossier, stage=stage, decision=ApprovalDecision.CANCELLED,
                                comment=reason, decided_by=user)
        _cancel_all_open_tasks(dossier)
        dossier.stop_reason = reason
        dossier.is_locked = True
        dossier.closed_at = timezone.now()
        _transition(dossier, Status.CANCELLED, user, 'cancelled', f'{_name(user)} hủy hồ sơ: {reason}',
                    open_tasks=False)
    nt.notify_many([dossier.owner, dossier.proposer], dossier, nt.KIND_INFO, 'Hồ sơ đã bị hủy', reason, actor=user)


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
            open_tasks = list(dossier.tasks.filter(state=Task.STATE_OPEN, role=role))
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
            if old_user is not None:
                nt.invalidate_badges(old_user)
        if changed:
            dossier.save()
            log(dossier, user, 'roles_updated', f'{_name(user)} đổi nhân sự: ' + '; '.join(changed) + '.')


COSTING_FIELDS = ('estimated_cost', 'post_sample_cost', 'proposed_wholesale_price', 'proposed_retail_price', 'cost_note')


def update_costing(dossier: ProductDevelopment, user, *, fields: dict) -> None:
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
    if not perms.can_update(user):
        return 'Bạn không có quyền cập nhật hồ sơ.'
    if design_version is not None:
        if not design_version.is_editable or dossier.status not in (Status.DESIGNING, Status.DESIGN_REVISE):
            return 'Phiên bản thiết kế đã gửi duyệt hoặc lưu trữ — không thêm tệp được.'
        return '' if perms.has_role(dossier, user, Role.DESIGNER, Role.OWNER) else 'Chỉ Thiết kế / R&D tải tệp thiết kế.'
    if sample_version is not None:
        if not sample_version.is_current:
            return 'Mẫu đã lưu trữ — không thêm tệp được.'
        if kind == AttachmentKind.EVALUATION:
            if dossier.status != Status.SAMPLE_EVAL_PENDING:
                return 'Chỉ tải biên bản đánh giá khi mẫu đang chờ đánh giá.'
            return '' if evaluator_roles_for(dossier, user) else 'Bạn không tham gia đánh giá mẫu.'
        if not sample_version.is_editable or dossier.status not in (Status.SAMPLING, Status.SAMPLE_REVISE):
            return 'Mẫu đã gửi đánh giá — không thêm ảnh / tài liệu kỹ thuật được.'
        roles = (Role.TECHNICIAN, Role.OWNER) if kind == AttachmentKind.TECH_SPEC else (
            Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
        return '' if perms.has_role(dossier, user, *roles) else 'Bạn không phụ trách phần việc này.'
    if kind == AttachmentKind.REFERENCE:
        if dossier.status not in (Status.DRAFT, Status.BRIEF_NEEDS_INFO, Status.BRIEF_PENDING):
            return 'Chỉ bổ sung tài liệu tham khảo ở bước đề xuất.'
        return '' if perms.has_role(dossier, user, Role.PROPOSER, Role.OWNER) else 'Chỉ người đề xuất / phụ trách.'
    if kind == AttachmentKind.COST:
        if dossier.is_locked:
            return 'Hồ sơ đã khóa sau duyệt.'
        return '' if perms.has_role(dossier, user, Role.COSTING, Role.OWNER) else 'Chỉ Kế hoạch / Giá thành.'
    return '' if perms.is_participant(dossier, user) else 'Chỉ người tham gia hồ sơ được tải tệp.'


def can_upload(dossier, user, kind: str, design_version=None, sample_version=None) -> bool:
    return not _upload_allowed(dossier, user, kind, design_version, sample_version)


def upload_attachment(dossier: ProductDevelopment, user, *, uploaded_file, kind: str, design_version=None,
                      sample_version=None, colorway=None, note: str = '') -> Attachment:
    _require(kind in AttachmentKind.values, 'Loại tệp không hợp lệ.')
    reason = _upload_allowed(dossier, user, kind, design_version, sample_version)
    _require(not reason, reason)
    if kind == AttachmentKind.COLORWAY:
        _require(colorway is not None and design_version is not None and colorway.design_version_id == design_version.pk,
                 'Chọn colorway cho ảnh.')
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


def add_comment(dossier: ProductDevelopment, user, *, body: str, design_version=None, sample_version=None) -> Comment:
    _require(perms.can_view_module(user), 'Bạn không có quyền xem hồ sơ.')
    body = _require_text(body, 'nội dung trao đổi')
    comment = Comment.objects.create(dossier=dossier, author=user, body=body,
                                     design_version=design_version, sample_version=sample_version)
    recipients = [dossier.owner]
    task = current_main_task(dossier)
    if task and task.assignee:
        recipients.append(task.assignee)
    nt.notify_many(recipients, dossier, nt.KIND_COMMENT, f'{_name(user)} trao đổi trên {dossier.code}',
                   body[:200], actor=user)
    return comment


def accept_task(task: Task, user) -> None:
    _require(task.state == Task.STATE_OPEN, 'Công việc đã đóng.')
    _require(task.assignee_id == user.pk, 'Chỉ người được giao mới nhận việc.')
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
    task.due_soon_notified_at = None
    task.overdue_notified_at = None
    task.save(update_fields=['due_at', 'due_soon_notified_at', 'overdue_notified_at'])
    log(dossier, user, 'task_due_changed',
        f'{_name(user)} đổi hạn «{task.title}»: {_fmt_due(old) or "—"} → {_fmt_due(due_at)}.')
    if task.assignee:
        nt.notify(task.assignee, dossier, nt.KIND_INFO, f'Đổi hạn: {task.title}', f'Hạn mới {_fmt_due(due_at)}',
                  actor=user)


def delete_draft(dossier: ProductDevelopment, user) -> None:
    _require(dossier.status == Status.DRAFT, 'Chỉ xóa được hồ sơ nháp.')
    _require(perms.can_delete(user) and perms.has_role(dossier, user, Role.PROPOSER, Role.OWNER),
             'Bạn không có quyền xóa hồ sơ nháp này.')
    dossier.delete()
