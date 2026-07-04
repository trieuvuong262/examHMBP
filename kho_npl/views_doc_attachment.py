"""Xóa chứng từ đính kèm phiếu kho NPL."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from assessment.decorators import module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.choices import DOC_STATUS_POSTED
from kho_npl.doc_attachment import add_doc_attachments, can_replace_doc_attachment, delete_doc_attachment, doc_attachments_for
from kho_npl.forms import DocAttachmentReplaceForm
from kho_npl.models import (
    NplDocAttachment,
    StockAdjustment,
    StockDisposal,
    StockIssue,
    StockReceipt,
    Stocktake,
    StockTransfer,
)
from kho_npl.services.adjustments import adjustment_attachment_editable_after_approve, adjustment_is_editable
from kho_npl.services.disposals import disposal_is_editable
from kho_npl.services.issues import issue_is_editable
from kho_npl.services.receipts import receipt_is_editable
from kho_npl.services.stocktakes import stocktake_attachment_editable_after_close, stocktake_is_editable
from kho_npl.services.transfers import transfer_attachment_editable_after_send, transfer_is_editable
from kho_npl.view_utils import perm_context

PARENT_MODEL_CONFIG = {
    StockIssue: ('issues', issue_is_editable, lambda o: o.status == DOC_STATUS_POSTED, 'kho_npl:issue_detail'),
    StockReceipt: ('receipts', receipt_is_editable, lambda o: o.status == DOC_STATUS_POSTED, 'kho_npl:receipt_detail'),
    StockTransfer: ('transfers', transfer_is_editable, transfer_attachment_editable_after_send, 'kho_npl:transfer_detail'),
    StockAdjustment: ('adjustments', adjustment_is_editable, adjustment_attachment_editable_after_approve, 'kho_npl:adjustment_detail'),
    Stocktake: ('stocktakes', stocktake_is_editable, stocktake_attachment_editable_after_close, 'kho_npl:stocktake_detail'),
    StockDisposal: ('disposals', disposal_is_editable, lambda o: o.status == DOC_STATUS_POSTED, 'kho_npl:disposal_detail'),
}


def parent_doc_attachment_allowed(parent, user) -> bool:
    config = PARENT_MODEL_CONFIG.get(type(parent))
    if not config:
        return False
    menu, is_editable_fn, posted_editable_fn, _ = config
    perms = perm_context(user, menu)
    return can_replace_doc_attachment(
        is_editable=is_editable_fn(parent),
        posted_editable=posted_editable_fn(parent),
        can_update=perms.get('can_update'),
    )


def redirect_for_doc_parent(parent):
    config = PARENT_MODEL_CONFIG.get(type(parent))
    if not config:
        return reverse('kho_npl:hub')
    return reverse(config[3], args=[parent.pk])


def _attachment_required_after_delete(parent) -> bool:
    return isinstance(parent, (StockIssue, StockReceipt, StockTransfer))


def doc_attachment_count_after_delete(parent, deleting_pk: int) -> int:
    return sum(1 for att in doc_attachments_for(parent) if getattr(att, 'pk', None) != deleting_pk)


def doc_attachment_delete_from_post(request, *, parent, redirect_url: str):
    raw = (request.POST.get('attachment_id') or '').strip()
    if not raw.isdigit():
        messages.error(request, 'Chứng từ không hợp lệ.')
        return redirect(redirect_url)
    attachment = get_object_or_404(NplDocAttachment, pk=int(raw))
    if attachment.content_object != parent:
        messages.error(request, 'Chứng từ không thuộc phiếu này.')
        return redirect(redirect_url)
    if not parent_doc_attachment_allowed(parent, request.user):
        messages.error(request, 'Không thể xóa chứng từ phiếu này.')
        return redirect(redirect_url)
    if _attachment_required_after_delete(parent) and doc_attachment_count_after_delete(parent, attachment.pk) == 0:
        messages.error(request, 'Phiếu cần ít nhất một chứng từ — không thể xóa file cuối.')
        return redirect(redirect_url)
    delete_doc_attachment(attachment, parent=parent)
    messages.success(request, 'Đã xóa chứng từ.')
    return redirect(redirect_url)


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def doc_attachment_delete(request, pk):
    attachment = get_object_or_404(NplDocAttachment, pk=pk)
    parent = attachment.content_object
    if parent is None:
        messages.error(request, 'Không tìm thấy phiếu gốc.')
        return redirect('kho_npl:hub')
    if not parent_doc_attachment_allowed(parent, request.user):
        messages.error(request, 'Không thể xóa chứng từ phiếu này.')
        return redirect(redirect_for_doc_parent(parent))
    if _attachment_required_after_delete(parent) and doc_attachment_count_after_delete(parent, attachment.pk) == 0:
        messages.error(request, 'Phiếu cần ít nhất một chứng từ — không thể xóa file cuối.')
        return redirect(redirect_for_doc_parent(parent))
    delete_doc_attachment(attachment, parent=parent)
    messages.success(request, 'Đã xóa chứng từ.')
    return redirect(redirect_for_doc_parent(parent))


def handle_doc_attachment_replace_post(request, parent, *, redirect_url: str, doc_label: str = 'phiếu'):
    if request.POST.get('attachment_id'):
        return doc_attachment_delete_from_post(request, parent=parent, redirect_url=redirect_url)
    if not parent_doc_attachment_allowed(parent, request.user):
        messages.error(request, 'Không thể thay chứng từ phiếu này.')
        return redirect(redirect_url)
    form = DocAttachmentReplaceForm(request.POST, request.FILES)
    if form.is_valid():
        count = add_doc_attachments(
            parent,
            form.cleaned_data['attachment_files'],
            uploaded_by=request.user,
        )
        messages.success(request, f'Đã thêm {count} chứng từ vào {doc_label}.')
    else:
        errs = form.errors.get('attachments') or form.non_field_errors()
        err = next(iter(errs), None) if errs else None
        messages.error(request, err or 'Không lưu được chứng từ — kiểm tra lại file.')
    return redirect(redirect_url)
