from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from PortalJustPlay.list_search import apply_combined_search, apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import admin_only
from hrm.module_permissions import MODULE_DOCUMENTS, user_can_access_module, user_can_edit_module

from .forms import DocumentCategoryForm, DocumentForm
from .models import Document, DocumentCategory
from .qa_service import ask_portal_assistant

QA_RATE_LIMIT = 40
QA_RATE_WINDOW = 3600


def _documents_access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_DOCUMENTS):
            messages.error(request, 'Bạn không có quyền truy cập Thư viện.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _qa_rate_limit(user) -> bool:
    key = f'library_qa_rate:{user.id}'
    count = cache.get(key, 0)
    if count >= QA_RATE_LIMIT:
        return False
    cache.set(key, count + 1, QA_RATE_WINDOW)
    return True


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


@_documents_access_required
def browse(request, category_slug=None, doc_slug=None):
    categories = _active_categories()
    selected_category, selected_document = _resolve_selected_document(
        categories, category_slug, doc_slug
    )

    context = {
        'categories': categories,
        'selected_category': selected_category,
        'selected_document': selected_document,
        'is_admin': user_can_edit_module(request.user, MODULE_DOCUMENTS),
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
    search_query = get_search_query(request)
    categories_qs = DocumentCategory.objects.all().order_by('sort_order', 'name')
    categories_qs = apply_term_search(
        categories_qs, search_query, 'name__icontains', 'slug__icontains', 'description__icontains',
    )
    page_obj, query_string = paginate_queryset(request, categories_qs)
    return render(request, 'documents/admin/category_list.html', {
        'categories': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
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
    search_query = get_search_query(request)
    documents_qs = Document.objects.select_related('category').order_by(
        'category__sort_order', 'sort_order', 'title'
    )
    documents_qs = apply_combined_search(documents_qs, search_query, lambda term: (
        Q(title__icontains=term)
        | Q(summary__icontains=term)
        | Q(slug__icontains=term)
        | Q(category__name__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, documents_qs)
    return render(request, 'documents/admin/document_list.html', {
        'documents': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
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


@_documents_access_required
def qa_chat(request):
    from django.conf import settings
    return render(request, 'documents/qa.html', {
        'is_admin': user_can_edit_module(request.user, MODULE_DOCUMENTS),
        'qa_enabled': bool(getattr(settings, 'GEMINI_API_KEY', '')),
    })


@_documents_access_required
@require_POST
def qa_ask(request):
    import json

    if not _qa_rate_limit(request.user):
        return JsonResponse({
            'ok': False,
            'error': f'Bạn đã hỏi quá nhiều ({QA_RATE_LIMIT} câu/giờ). Vui lòng thử lại sau.',
        }, status=429)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Dữ liệu không hợp lệ.'}, status=400)

    question = (payload.get('question') or '').strip()
    history = payload.get('history') or []
    if not isinstance(history, list):
        history = []

    try:
        answer = ask_portal_assistant(request.user, question, history=history)
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except RuntimeError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=503)
    except Exception:
        return JsonResponse({
            'ok': False,
            'error': 'Không kết nối được AI. Kiểm tra GEMINI_API_KEY hoặc thử lại sau.',
        }, status=502)

    return JsonResponse({'ok': True, 'answer': answer})
