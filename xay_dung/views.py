import re

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_XAY_DUNG,
    user_can_create_module,
    user_can_delete_module,
    user_can_update_module,
)
from nas_storage.upload_guard import UploadRejected, upload_audit
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import Model3DForm
from .models import Model3D

# CSP cho file HTML người dùng upload:
# - sandbox KHÔNG có allow-same-origin → chạy ở origin "null", không đọc được
#   cookie/session/CSRF của portal, không gọi được API portal bằng quyền người xem.
# - Cho phép script inline + CDN phổ biến (Three.js qua unpkg/jsdelivr).
RAW_CSP = '; '.join([
    'sandbox allow-scripts allow-downloads allow-pointer-lock allow-modals',
    "default-src 'none'",
    "script-src 'unsafe-inline' 'unsafe-eval' blob: https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
    "style-src 'unsafe-inline' https:",
    'img-src data: blob: https:',
    'font-src data: https:',
    'media-src data: blob: https:',
    'connect-src data: blob: https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com',
    'worker-src blob:',
    "form-action 'none'",
    "base-uri 'none'",
])

# Origin "null" ném SecurityError khi truy cập localStorage/sessionStorage —
# nhiều file 3D gọi localStorage ngay khi load nên script sẽ chết. Shim bộ nhớ
# tạm (mất khi tải lại trang) để file chạy bình thường.
STORAGE_SHIM = (
    b'<script>(function(){function mk(){var d={};return{'
    b'getItem:function(k){k=String(k);return Object.prototype.hasOwnProperty.call(d,k)?d[k]:null},'
    b'setItem:function(k,v){d[String(k)]=String(v)},'
    b'removeItem:function(k){delete d[String(k)]},'
    b'clear:function(){d={}},'
    b'key:function(i){var a=Object.keys(d);return i<a.length?a[i]:null},'
    b'get length(){return Object.keys(d).length}}}'
    b'["localStorage","sessionStorage"].forEach(function(n){'
    b'try{window[n].getItem("_");}catch(e){'
    b'try{Object.defineProperty(window,n,{value:mk(),configurable:true});}catch(e2){}}});'
    b'})();</script>'
)

_HEAD_RE = re.compile(rb'<head\b[^>]*>', re.IGNORECASE)


def _inject_shim(content: bytes) -> bytes:
    match = _HEAD_RE.search(content)
    if match:
        return content[:match.end()] + STORAGE_SHIM + content[match.end():]
    return STORAGE_SHIM + content


def _perms(user):
    return {
        'can_create': user_can_create_module(user, MODULE_XAY_DUNG),
        'can_update': user_can_update_module(user, MODULE_XAY_DUNG),
        'can_delete': user_can_delete_module(user, MODULE_XAY_DUNG),
    }


@module_perm_required(MODULE_XAY_DUNG, 'view')
def model_list(request):
    search_query = get_search_query(request)
    qs = Model3D.objects.select_related('uploaded_by')
    qs = apply_term_search(qs, search_query, ('title', 'description', 'original_name'))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'xay_dung/list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        **_perms(request.user),
    })


def _save_form(request, form, success_message):
    try:
        with upload_audit(request):
            valid = form.is_valid()
    except UploadRejected as exc:
        form.add_error('html_file', exc)
        valid = False
    if not valid:
        return None
    obj = form.save(commit=False)
    if not obj.pk:
        obj.uploaded_by = request.user
    obj.save()
    messages.success(request, success_message)
    return obj


@module_perm_required(MODULE_XAY_DUNG, 'create')
def model_create(request):
    if request.method == 'POST':
        form = Model3DForm(request.POST, request.FILES)
        obj = _save_form(request, form, 'Đã tải lên mô hình 3D.')
        if obj:
            return redirect('xay_dung:detail', pk=obj.pk)
    else:
        form = Model3DForm()
    return render(request, 'xay_dung/form.html', {'form': form, 'is_edit': False})


@module_perm_required(MODULE_XAY_DUNG, 'update')
def model_update(request, pk):
    obj = get_object_or_404(Model3D, pk=pk)
    if request.method == 'POST':
        form = Model3DForm(request.POST, request.FILES, instance=obj)
        saved = _save_form(request, form, 'Đã cập nhật mô hình 3D.')
        if saved:
            return redirect('xay_dung:detail', pk=saved.pk)
    else:
        form = Model3DForm(instance=obj)
    return render(request, 'xay_dung/form.html', {'form': form, 'is_edit': True, 'item': obj})


@module_perm_required(MODULE_XAY_DUNG, 'delete')
@require_POST
def model_delete(request, pk):
    obj = get_object_or_404(Model3D, pk=pk)
    title = obj.title
    obj.delete()  # django_cleanup xoá file vật lý
    messages.success(request, f'Đã xoá mô hình «{title}».')
    return redirect('xay_dung:list')


@module_perm_required(MODULE_XAY_DUNG, 'view')
def model_detail(request, pk):
    obj = get_object_or_404(Model3D.objects.select_related('uploaded_by'), pk=pk)
    return render(request, 'xay_dung/detail.html', {'item': obj, **_perms(request.user)})


@module_perm_required(MODULE_XAY_DUNG, 'view')
@xframe_options_sameorigin
def model_raw(request, pk):
    """Nội dung HTML cho iframe — luôn kèm CSP sandbox (xem RAW_CSP)."""
    obj = get_object_or_404(Model3D, pk=pk)
    if not obj.html_file:
        raise Http404
    try:
        with obj.html_file.open('rb') as fh:
            content = fh.read()
    except (FileNotFoundError, OSError):
        raise Http404

    response = HttpResponse(_inject_shim(content), content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = RAW_CSP
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store'
    response['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response
