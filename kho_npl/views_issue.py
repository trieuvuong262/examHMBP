from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT
from kho_npl.forms import StockIssueForm, StockIssueLineFormSet
from kho_npl.models import StockIssue
from kho_npl.services.doc_numbers import next_issue_number
from kho_npl.services.issues import (
    IssueWorkflowError,
    cancel_stock_issue,
    issue_is_editable,
    post_stock_issue,
)
from kho_npl.view_utils import nav_context, perm_context


def _save_issue_form(request, issue, *, is_create: bool):
    form = StockIssueForm(request.POST, instance=issue)
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
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def issue_list(request):
    search_query = get_search_query(request)
    qs = StockIssue.objects.select_related('issued_by', 'created_by')
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(production_order__icontains=search_query)
            | Q(product_code__icontains=search_query)
            | Q(recipient_name__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/issue_list.html', {
        **nav_context('issues'),
        **perm_context(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def issue_detail(request, pk):
    issue = get_object_or_404(
        StockIssue.objects.select_related('issued_by', 'created_by')
        .prefetch_related('lines__material', 'lines__location'),
        pk=pk,
    )
    return render(request, 'kho_npl/issue_detail.html', {
        **nav_context('issues'),
        **perm_context(request.user),
        'issue': issue,
        'is_editable': issue_is_editable(issue),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def issue_create(request):
    issue = StockIssue()
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_issue_form(request, issue, is_create=True)
        if doc:
            if action == 'post':
                try:
                    post_stock_issue(doc, request.user)
                    messages.success(request, f'Đã ghi sổ phiếu {doc.number} và trừ tồn kho.')
                except IssueWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:issue_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:issue_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockIssueForm(instance=issue)
        formset = StockIssueLineFormSet(instance=issue, prefix='lines')
    return render(request, 'kho_npl/issue_form.html', {
        **nav_context('issues'),
        **perm_context(request.user),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:issue_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def issue_edit(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if not issue_is_editable(issue):
        messages.error(request, 'Phiếu đã ghi sổ hoặc đã hủy — không thể sửa.')
        return redirect('kho_npl:issue_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_issue_form(request, issue, is_create=False)
        if doc:
            if action == 'post':
                try:
                    post_stock_issue(doc, request.user)
                    messages.success(request, f'Đã ghi sổ phiếu {doc.number} và trừ tồn kho.')
                except IssueWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:issue_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:issue_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockIssueForm(instance=issue)
        formset = StockIssueLineFormSet(instance=issue, prefix='lines')
    return render(request, 'kho_npl/issue_form.html', {
        **nav_context('issues'),
        **perm_context(request.user),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'issue': issue,
        'cancel_url': reverse('kho_npl:issue_detail', args=[issue.pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def issue_post(request, pk):
    issue = get_object_or_404(StockIssue, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_issue(issue, request.user)
            messages.success(request, f'Đã ghi sổ phiếu {issue.number}.')
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
        **nav_context('issues'),
        **perm_context(request.user),
        'issue': issue,
    })
