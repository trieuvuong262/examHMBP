from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.material_search import apply_smart_search
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import ADJUST_STATUS_PENDING
from kho_npl.forms import DocAttachmentReplaceForm, StockAdjustmentForm, StockAdjustmentLineFormSet
from kho_npl.models import StockAdjustment
from kho_npl.doc_attachment import can_replace_doc_attachment, replace_doc_attachment
from kho_npl.services.adjustments import (
    AdjustmentWorkflowError,
    adjustment_attachment_editable_after_approve,
    adjustment_is_editable,
    approve_stock_adjustment,
    reject_stock_adjustment,
)
from kho_npl.services.doc_numbers import next_adjustment_number
from kho_npl.view_utils import nav_context, perm_context


def _save_adjustment_form(request, adjustment, *, is_create: bool):
    form = StockAdjustmentForm(request.POST, request.FILES, instance=adjustment)
    formset = StockAdjustmentLineFormSet(request.POST, instance=adjustment, prefix='lines')
    if not (form.is_valid() and formset.is_valid()):
        return form, formset, None

    with transaction.atomic():
        doc = form.save(commit=False)
        if is_create:
            doc.number = next_adjustment_number()
            doc.proposed_by = request.user
            doc.status = ADJUST_STATUS_PENDING
        doc.save()
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def adjustment_list(request):
    search_query = get_search_query(request)
    qs = (
        StockAdjustment.objects
        .annotate(line_count=Count('lines'))
        .select_related('proposed_by', 'approved_by')
        .prefetch_related('lines__material__unit', 'lines__location')
    )
    if search_query:
        qs = apply_smart_search(
            qs,
            search_query,
            ('number', 'lines__material__name'),
        ).distinct()
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/adjustment_list.html', {
        **nav_context('adjustments', user=request.user),
        **perm_context(request.user, 'adjustments'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def adjustment_detail(request, pk):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related('proposed_by', 'approved_by').prefetch_related(
            'lines__material__unit', 'lines__location',
        ),
        pk=pk,
    )
    perms = perm_context(request.user, 'adjustments')
    is_editable = adjustment_is_editable(adjustment)
    can_replace_attachment = can_replace_doc_attachment(
        is_editable=is_editable,
        posted_editable=adjustment_attachment_editable_after_approve(adjustment),
        can_update=perms.get('can_update'),
    )
    return render(request, 'kho_npl/adjustment_detail.html', {
        **nav_context('adjustments', user=request.user),
        **perms,
        'adjustment': adjustment,
        'is_editable': is_editable,
        'can_replace_attachment': can_replace_attachment,
        'adjustment_replace_attachment_url': reverse('kho_npl:adjustment_replace_attachment', args=[adjustment.pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def adjustment_replace_attachment(request, pk):
    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:adjustment_detail', pk=pk)
    perms = perm_context(request.user, 'adjustments')
    if not can_replace_doc_attachment(
        is_editable=adjustment_is_editable(adjustment),
        posted_editable=adjustment_attachment_editable_after_approve(adjustment),
        can_update=perms.get('can_update'),
    ):
        messages.error(request, 'Không thể thay chứng từ phiếu này.')
        return redirect('kho_npl:adjustment_detail', pk=pk)
    form = DocAttachmentReplaceForm(request.POST, request.FILES)
    if form.is_valid():
        replace_doc_attachment(adjustment, form.cleaned_data['attachment'])
        messages.success(request, f'Đã cập nhật chứng từ phiếu {adjustment.number}.')
    else:
        err = next(iter(form.errors.get('attachment', [])), None)
        messages.error(request, err or 'Không lưu được chứng từ — kiểm tra lại file.')
    return redirect('kho_npl:adjustment_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def adjustment_create(request):
    adjustment = StockAdjustment()
    if request.method == 'POST':
        form, formset, doc = _save_adjustment_form(request, adjustment, is_create=True)
        if doc:
            messages.success(
                request,
                f'Đã tạo phiếu điều chỉnh {doc.number} ({doc.lines.count()} dòng) — chờ duyệt.',
            )
            return redirect('kho_npl:adjustment_detail', pk=doc.pk)
    else:
        form = StockAdjustmentForm(instance=adjustment)
        formset = StockAdjustmentLineFormSet(instance=adjustment, prefix='lines')
    return render(request, 'kho_npl/adjustment_form.html', {
        **nav_context('adjustments', user=request.user),
        **perm_context(request.user, 'adjustments'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:adjustment_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def adjustment_approve(request, pk):
    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            approve_stock_adjustment(adjustment, request.user)
            messages.success(request, f'Đã duyệt phiếu {adjustment.number} và cập nhật tồn.')
        except AdjustmentWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:adjustment_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def adjustment_reject(request, pk):
    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            reject_stock_adjustment(adjustment, request.user)
            messages.success(request, f'Đã từ chối phiếu {adjustment.number}.')
        except AdjustmentWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:adjustment_detail', pk=pk)
