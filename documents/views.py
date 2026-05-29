from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from assessment.decorators import admin_only
from hrm.permissions import is_portal_admin

from .forms import DocumentCategoryForm, DocumentForm
from .models import Document, DocumentCategory


def _active_categories():
    active_docs = Document.objects.filter(is_active=True).order_by('sort_order', 'title')
    return DocumentCategory.objects.filter(is_active=True).prefetch_related(
        Prefetch('documents', queryset=active_docs),
    ).order_by('sort_order', 'name')


def _resolve_selected_document(categories, category_slug=None, doc_slug=None):
    selected_category = None
    selected_document = None

    if category_slug:
        selected_category = next(
            (c for c in categories if c.slug == category_slug),
            None,
        )
        if selected_category and doc_slug:
            selected_document = next(
                (
                    d for d in selected_category.documents.all()
                    if d.is_active and d.slug == doc_slug
                ),
                None,
            )
        elif selected_category:
            selected_document = next(
                (d for d in selected_category.documents.all() if d.is_active),
                None,
            )
    else:
        for category in categories:
            doc = next((d for d in category.documents.all() if d.is_active), None)
            if doc:
                selected_category = category
                selected_document = doc
                break

    return selected_category, selected_document


@login_required
def browse(request, category_slug=None, doc_slug=None):
    categories = _active_categories()
    selected_category, selected_document = _resolve_selected_document(
        categories, category_slug, doc_slug
    )

    context = {
        'categories': categories,
        'selected_category': selected_category,
        'selected_document': selected_document,
        'is_admin': is_portal_admin(request.user),
    }
    return render(request, 'documents/browse.html', context)


@admin_only
def admin_hub(request):
    categories = DocumentCategory.objects.prefetch_related('documents').order_by(
        'sort_order', 'name'
    )
    doc_count = Document.objects.count()
    return render(request, 'documents/admin/hub.html', {
        'categories': categories,
        'doc_count': doc_count,
    })


@admin_only
def admin_category_list(request):
    categories = DocumentCategory.objects.all().order_by('sort_order', 'name')
    return render(request, 'documents/admin/category_list.html', {
        'categories': categories,
    })


@admin_only
def admin_category_create(request):
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã tạo nhóm tài liệu.')
            return redirect('documents:admin_categories')
    else:
        form = DocumentCategoryForm()
    return render(request, 'documents/admin/category_form.html', {
        'form': form,
        'title': 'Thêm nhóm tài liệu',
    })


@admin_only
def admin_category_edit(request, pk):
    category = get_object_or_404(DocumentCategory, pk=pk)
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật nhóm tài liệu.')
            return redirect('documents:admin_categories')
    else:
        form = DocumentCategoryForm(instance=category)
    return render(request, 'documents/admin/category_form.html', {
        'form': form,
        'title': 'Sửa nhóm tài liệu',
        'category': category,
    })


@admin_only
def admin_category_delete(request, pk):
    category = get_object_or_404(DocumentCategory, pk=pk)
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'Đã xóa nhóm "{name}".')
        return redirect('documents:admin_categories')
    return render(request, 'documents/admin/category_confirm_delete.html', {
        'category': category,
    })


@admin_only
def admin_document_list(request):
    documents = Document.objects.select_related('category').order_by(
        'category__sort_order', 'sort_order', 'title'
    )
    return render(request, 'documents/admin/document_list.html', {
        'documents': documents,
    })


@admin_only
def admin_document_create(request):
    initial = {}
    cat_id = request.GET.get('category')
    if cat_id:
        initial['category'] = cat_id
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.created_by = request.user
            doc.save()
            messages.success(request, 'Đã tạo tài liệu.')
            return redirect(
                'documents:browse_document',
                category_slug=doc.category.slug,
                doc_slug=doc.slug,
            )
    else:
        form = DocumentForm(initial=initial)
    return render(request, 'documents/admin/document_form.html', {
        'form': form,
        'title': 'Thêm tài liệu',
    })


@admin_only
def admin_document_edit(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            doc = form.save()
            messages.success(request, 'Đã cập nhật tài liệu.')
            return redirect(
                'documents:browse_document',
                category_slug=doc.category.slug,
                doc_slug=doc.slug,
            )
    else:
        form = DocumentForm(instance=document)
    return render(request, 'documents/admin/document_form.html', {
        'form': form,
        'title': 'Sửa tài liệu',
        'document': document,
    })


@admin_only
def admin_document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        title = document.title
        document.delete()
        messages.success(request, f'Đã xóa tài liệu "{title}".')
        return redirect('documents:admin_documents')
    return render(request, 'documents/admin/document_confirm_delete.html', {
        'document': document,
    })
