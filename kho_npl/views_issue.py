from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.user_search import search_issue_recipients
from kho_npl.material_search import apply_smart_search
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.forms import (
    StockIssueForm,
    StockIssueLineFormSet,
    StockIssueLineNotesFormSet,
    StockIssueNotesForm,
)
from kho_npl.models import StockIssue
from kho_npl.doc_attachment import can_replace_doc_attachment, doc_attachments_for
from kho_npl.views_doc_attachment import handle_doc_attachment_replace_post
from kho_npl.services.doc_numbers import next_issue_number
from kho_npl.services.issues import (
    IssueWorkflowError,
    cancel_stock_issue,
    issue_is_editable,
    post_stock_issue,
)
from kho_npl.doc_list_columns import (
    ISSUE_LIST_COLUMNS,
    ISSUE_LIST_SORT_FIELDS,
    ISSUE_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.doc_list_utils import ISSUE_STATUS_FILTER_CHOICES, doc_list_sort, doc_status_filter
from kho_npl.doc_prefill import (
    issue_line_prefill_from_bom,
    issue_line_prefill_initial,
    parse_doc_location_id,
    parse_doc_material_id,
)
from kho_npl.view_utils import nav_context, perm_context


def _save_issue_form(request, issue, *, is_create: bool):
    form = StockIssueForm(request.POST, request.FILES, instance=issue, operator=request.user)
    formset = StockIssueLineFormSet(request.POST, instance=issue, prefix='lines')
    if not (form.is_valid() and formset.is_valid()):
        return form, formset, None

    with transaction.atomic():
        doc = form.save(commit=False)
        if is_create:
            doc.number = next_issue_number()
            doc.created_by = request.user
            doc.status = DOC_STATUS_DRAFT
        doc.save()
        form.save_doc_attachments(doc, user=request.user)
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def product_code_search(request):
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_product_codes(q)})


@module_perm_required(MODULE_KHO_NPL, 'view')
def recipient_search(request):
    q = (request.GET.get('q') or '').strip()
    limit = 1000 if not q else 50
    return JsonResponse({'results': search_issue_recipients(q, limit=limit)})


@module_perm_required(MODULE_KHO_NPL, 'view')
def issue_list(request):
    search_query = get_search_query(request)
    status = doc_status_filter(request, choices=ISSUE_STATUS_FILTER_CHOICES)
    sort_key, sort_dir, order = doc_list_sort(request, ISSUE_LIST_SORT_FIELDS, default_key='issue_date')
    qs = StockIssue.objects.select_related('issued_by', 'created_by', 'recipient', 'recipient__profile')
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = apply_smart_search(
            qs,
            search_query,
            (
                'number',
                'recipient_name',
                'recipient__username',
                'recipient__profile__full_name',
                'recipient__profile__employee_code',
            ),
        )
    qs = qs.order_by(order, '-pk')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/issue_list.html', {
        **nav_context('issues', user=request.user),
        **perm_context(request.user, 'issues'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': ISSUE_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status),
        'list_columns': ISSUE_LIST_COLUMNS,
        'total_col_weight': ISSUE_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
    })


def issue_notes_editable(issue: StockIssue) -> bool:
    return issue.status == DOC_STATUS_POSTED


@module_perm_required(MODULE_KHO_NPL, 'view')
def issue_detail(request, pk):
    issue = get_object_or_404(
        StockIssue.objects.select_related('issued_by', 'created_by', 'recipient', 'recipient__profile')
        .prefetch_related('lines__material', 'lines__location'),
        pk=pk,
    )
    perms = perm_context(request.user, 'issues')
    can_edit_notes = issue_notes_editable(issue) and perms.get('can_update')
    is_editable = issue_is_editable(issue)
    can_replace_attachment = can_replace_doc_attachment(
        is_editable=is_editable,
        posted_editable=issue_notes_editable(issue),
        can_update=perms.get('can_update'),
    )
    notes_form = StockIssueNotesForm(instance=issue) if can_edit_notes else None
    line_notes_formset = StockIssueLineNotesFormSet(instance=issue) if can_edit_notes else None
    return render(request, 'kho_npl/issue_detail.html', {
        **nav_context('issues', user=request.user),
        **perms,
        'issue': issue,
        'is_editable': is_editable,
        'can_edit_notes': can_edit_notes,
        'can_replace_attachment': can_replace_attachment,
        'attachments': doc_attachments_for(issue),
        'issue_replace_attachment_url': reverse('kho_npl:issue_replace_attachment', args=[issue.pk]),
        'notes_form': notes_form,
        'line_notes_formset': line_notes_formset,
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def issue_create(request):
    issue = StockIssue()
    bom_raw = (request.GET.get('bom') or '').strip()
    bom_id = int(bom_raw) if bom_raw.isdigit() else None
    bom_lines, product_code = issue_line_prefill_from_bom(bom_id)
    if product_code:
        issue.product_code = product_code

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_issue_form(request, issue, is_create=True)
        if doc:
            if product_code and not doc.product_code:
                doc.product_code = product_code
                doc.save(update_fields=['product_code'])
            if action == 'post':
                try:
                    post_stock_issue(doc, request.user)
                    messages.success(request, f'Phiếu {doc.number} đã xuất kho và trừ tồn.')
                except IssueWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:issue_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:issue_detail', pk=doc.pk)
    if request.method != 'POST':
        form_initial = {}
        initial_lines = bom_lines
        if product_code:
            form_initial['issue_type'] = f'Xuất theo BOM {product_code}'
            form_initial['notes'] = f'Prefill từ hồ sơ SX · BOM mã {product_code}'
        if not initial_lines:
            material_id = parse_doc_material_id(request)
            location_id = parse_doc_location_id(request, 'location')
            initial_lines = issue_line_prefill_initial(material_id, location_id)
        form = StockIssueForm(instance=issue, operator=request.user, initial=form_initial)
        from django.forms import inlineformset_factory
        from kho_npl.forms import BaseStockIssueLineFormSet, StockIssueLineForm
        from kho_npl.models import StockIssueLine
        LineFormSet = inlineformset_factory(
            StockIssue,
            StockIssueLine,
            form=StockIssueLineForm,
            formset=BaseStockIssueLineFormSet,
            extra=max(len(initial_lines), 1),
            can_delete=True,
        )
        formset = LineFormSet(
            instance=issue,
            prefix='lines',
            initial=initial_lines,
        )
    return render(request, 'kho_npl/issue_form.html', {
        **nav_context('issues', user=request.user),
        **perm_context(request.user, 'issues'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:issue_list'),
        'existing_attachments': [],
    })


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def issue_update_notes(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:issue_detail', pk=pk)
    if not issue_notes_editable(issue):
        messages.error(request, 'Chỉ phiếu đã xuất kho mới được sửa ghi chú tại đây.')
        return redirect('kho_npl:issue_detail', pk=pk)
    form = StockIssueNotesForm(request.POST, instance=issue)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.save(update_fields=['notes'])
        messages.success(request, f'Đã cập nhật ghi chú phiếu {issue.number}.')
    else:
        messages.error(request, 'Không lưu được ghi chú — kiểm tra lại nội dung.')
    return redirect('kho_npl:issue_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def issue_replace_attachment(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:issue_detail', pk=pk)
    return handle_doc_attachment_replace_post(
        request,
        issue,
        redirect_url=reverse('kho_npl:issue_detail', args=[pk]),
        doc_label=f'phiếu {issue.number}',
    )


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def issue_update_line_notes(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:issue_detail', pk=pk)
    if not issue_notes_editable(issue):
        messages.error(request, 'Chỉ phiếu đã xuất kho mới được sửa ghi chú dòng tại đây.')
        return redirect('kho_npl:issue_detail', pk=pk)
    formset = StockIssueLineNotesFormSet(request.POST, instance=issue)
    if formset.is_valid():
        formset.save()
        messages.success(request, f'Đã cập nhật ghi chú dòng phiếu {issue.number}.')
    else:
        messages.error(request, 'Không lưu được ghi chú dòng — kiểm tra lại nội dung.')
    return redirect('kho_npl:issue_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def issue_edit(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if not issue_is_editable(issue):
        messages.error(request, 'Phiếu đã xuất kho hoặc đã hủy — không thể sửa.')
        return redirect('kho_npl:issue_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_issue_form(request, issue, is_create=False)
        if doc:
            if action == 'post':
                try:
                    post_stock_issue(doc, request.user)
                    messages.success(request, f'Phiếu {doc.number} đã xuất kho và trừ tồn.')
                except IssueWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:issue_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:issue_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockIssueForm(instance=issue, operator=request.user)
        formset = StockIssueLineFormSet(instance=issue, prefix='lines')
    return render(request, 'kho_npl/issue_form.html', {
        **nav_context('issues', user=request.user),
        **perm_context(request.user, 'issues'),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'issue': issue,
        'cancel_url': reverse('kho_npl:issue_detail', args=[issue.pk]),
        'existing_attachments': doc_attachments_for(issue),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def issue_post(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_issue(issue, request.user)
            messages.success(request, f'Phiếu {issue.number} đã xuất kho.')
        except IssueWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:issue_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def issue_cancel(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method == 'POST':
        try:
            cancel_stock_issue(issue)
            messages.success(request, f'Đã hủy phiếu {issue.number}.')
            return redirect('kho_npl:issue_list')
        except IssueWorkflowError as exc:
            messages.error(request, str(exc))
            return redirect('kho_npl:issue_detail', pk=pk)
    return render(request, 'kho_npl/issue_confirm_cancel.html', {
        **nav_context('issues', user=request.user),
        **perm_context(request.user, 'issues'),
        'issue': issue,
    })
