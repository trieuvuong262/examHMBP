from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from PortalJustPlay.list_search import apply_combined_search, apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import (
    MODULE_AUDIT,
    MODULE_DOCUMENTS,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_update_module,
)

from .forms import DocumentCategoryForm, DocumentForm, LibraryQAConfigForm
from .models import Document, DocumentCategory, LibraryQAConfig
from .qa_config import is_qa_enabled, qa_config_source
from .qa_history import (
    clear_user_qa_history,
    get_user_qa_history,
    get_user_qa_history_for_display,
    save_qa_turn,
    users_with_qa_history,
)
from .qa_service import QAAssistantError, ask_portal_assistant, generate_followup_suggestions, generate_initial_suggestions

QA_RATE_LIMIT = 40
QA_RATE_WINDOW = 3600


def _documents_perm_context(user):
    return {
        'is_admin': user_can_edit_module(user, MODULE_DOCUMENTS),
        'can_create': user_can_create_module(user, MODULE_DOCUMENTS),
        'can_update': user_can_update_module(user, MODULE_DOCUMENTS),
        'can_delete': user_can_delete_module(user, MODULE_DOCUMENTS),
    }


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


def _get_active_document_or_404(pk):
    return get_object_or_404(
        Document.objects.select_related('category'),
        pk=pk,
        is_active=True,
        category__is_active=True,
    )


def _document_file_response(document, *, as_attachment=False):
    source = document.source_file
    if not source:
        raise Http404('Không có file gốc.')
    try:
        handle = source.open('rb')
    except FileNotFoundError as exc:
        raise Http404('File không tồn tại.') from exc

    filename = document.source_display_name or 'tai-lieu'
    response = FileResponse(handle, as_attachment=as_attachment, filename=filename)
    if not as_attachment and document.source_is_pdf:
        response['Content-Type'] = 'application/pdf'
    return response


@_documents_access_required
@require_GET
def document_file_view(request, pk):
    document = _get_active_document_or_404(pk)
    return _document_file_response(document, as_attachment=False)


@_documents_access_required
@require_GET
def document_file_download(request, pk):
    document = _get_active_document_or_404(pk)
    return _document_file_response(document, as_attachment=True)


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
        **_documents_perm_context(request.user),
    }
    return render(request, 'documents/browse.html', context)


@module_perm_required(MODULE_DOCUMENTS, 'edit')
def admin_hub(request):
    categories = DocumentCategory.objects.prefetch_related('documents').order_by(
        'sort_order', 'name'
    )
    doc_count = Document.objects.count()
    return render(request, 'documents/admin/hub.html', {
        'categories': categories,
        'doc_count': doc_count,
    })


@module_perm_required_methods(MODULE_AUDIT, get='view', post='export')
def admin_qa_settings(request):
    config = LibraryQAConfig.load()
    if request.method == 'POST':
        action = (request.POST.get('action') or 'save_config').strip()
        if action == 'clear_history':
            user_id = request.POST.get('history_user_id')
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                user_id = None
            if not user_id:
                messages.error(request, 'Vui lòng chọn người dùng cần xóa lịch sử.')
            else:
                from django.contrib.auth.models import User
                target = User.objects.filter(pk=user_id).select_related('profile').first()
                if not target:
                    messages.error(request, 'Không tìm thấy người dùng.')
                else:
                    deleted = clear_user_qa_history(user_id)
                    label = getattr(getattr(target, 'profile', None), 'full_name', '') or target.username
                    messages.success(
                        request,
                        f'Đã xóa {deleted} tin nhắn hỏi đáp của {label}.',
                    )
            return redirect('audit:qa_assistant')

        form = LibraryQAConfigForm(request.POST, instance=config)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            # Giữ key cũ nếu để trống ô nhập (không xóa nhầm)
            if not (form.cleaned_data.get('gemini_api_key') or '').strip():
                obj.gemini_api_key = config.gemini_api_key
            obj.save()
            messages.success(request, 'Đã lưu cấu hình Hỏi đáp AI.')
            return redirect('audit:qa_assistant')
    else:
        form = LibraryQAConfigForm(instance=config)

    history_users = []
    for user in users_with_qa_history():
        count = user.library_qa_messages.count()
        full_name = getattr(getattr(user, 'profile', None), 'full_name', '') or user.get_full_name()
        history_users.append({
            'id': user.id,
            'label': f'{full_name or user.username} (@{user.username}) — {count} tin',
        })

    return render(request, 'documents/admin/qa_settings.html', {
        'form': form,
        'qa_enabled': is_qa_enabled(),
        'qa_config_source': qa_config_source(),
        'has_stored_key': bool((config.gemini_api_key or '').strip()),
        'env_key_configured': bool((getattr(settings, 'GEMINI_API_KEY', '') or '').strip()),
        'history_users': history_users,
    })


@module_perm_required(MODULE_DOCUMENTS, 'edit')
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
        **_documents_perm_context(request.user),
    })


@module_perm_required(MODULE_DOCUMENTS, 'create')
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


@module_perm_required(MODULE_DOCUMENTS, 'update')
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


@module_perm_required(MODULE_DOCUMENTS, 'delete')
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


@module_perm_required(MODULE_DOCUMENTS, 'edit')
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
        **_documents_perm_context(request.user),
    })


@module_perm_required(MODULE_DOCUMENTS, 'create')
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


@module_perm_required(MODULE_DOCUMENTS, 'update')
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


@module_perm_required(MODULE_DOCUMENTS, 'delete')
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
    return render(request, 'documents/qa.html', {
        'qa_enabled': is_qa_enabled(),
        'can_configure_qa': user_can_access_menu(request.user, MODULE_AUDIT, 'qa_assistant'),
        **_documents_perm_context(request.user),
        'qa_history': get_user_qa_history_for_display(request.user),
    })


@_documents_access_required
def qa_suggest_initial(request):
    if not is_qa_enabled():
        return JsonResponse({'ok': True, 'suggestions': []})
    suggestions = generate_initial_suggestions(request.user, request=request)
    return JsonResponse({'ok': True, 'suggestions': suggestions})


@_documents_access_required
@require_POST
def qa_ask(request):
    import json

    if not _qa_rate_limit(request.user):
        return JsonResponse({
            'ok': False,
            'error': (
                f'Bạn hỏi dồn dập quá ({QA_RATE_LIMIT} câu/giờ)! '
                'Trợ lý cần thở — thử lại sau chút nhé.'
            ),
        }, status=429)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Dữ liệu không hợp lệ.'}, status=400)

    question = (payload.get('question') or '').strip()
    history = get_user_qa_history(request.user)

    try:
        answer = ask_portal_assistant(
            request.user, question, history=history, request=request,
        )
        save_qa_turn(request.user, question, answer)
        suggestions = generate_followup_suggestions(
            request.user,
            question,
            answer,
            history=history + [
                {'role': 'user', 'text': question},
                {'role': 'model', 'text': answer},
            ],
            request=request,
        )
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except QAAssistantError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=503)
    except RuntimeError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=503)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('qa_ask unexpected error')
        return JsonResponse({
            'ok': False,
            'error': 'Mạng với trợ lý AI đang "giật lag" một chút — thử refresh trang hoặc hỏi lại sau nhé.',
        }, status=502)

    return JsonResponse({'ok': True, 'answer': answer, 'suggestions': suggestions})
