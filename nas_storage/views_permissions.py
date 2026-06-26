"""Quản trị phân quyền shared folder NAS."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from hrm.menu_permissions import menu_perm_context, user_can_access_menu, user_can_update_menu
from hrm.models import Profile
from hrm.module_permissions import MODULE_NAS_STORAGE
from hrm.user_search import exclude_hidden_hrm_users, filter_users_by_search
from nas_storage.forms import NasAccessGroupForm, NasFolderPermissionForm, NasShareFolderForm
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder, NasUserFolderAccess
from nas_storage.nas_acl_apply import (
    NasAclApplyError,
    apply_all_folder_permissions,
    apply_folder_permissions,
    discover_shares_from_nas,
    nas_acl_ssh_configured,
)
from nas_storage.permission_defs import ADMIN_FIELDS, READ_FIELDS, WRITE_FIELDS
from nas_storage.user_folders import (
    nas_folders_feature_available,
    nas_folders_page_context,
    save_user_nas_folder_formset,
)
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset


def _perm_menu_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_update_menu(request.user, MODULE_NAS_STORAGE, 'permissions'):
            messages.error(request, 'Bạn không có quyền cấu hình phân quyền NAS.')
            return redirect('nas_storage:browse')
        return view_func(request, *args, **kwargs)

    return wrapper


def _nav_context(request, active: str) -> dict:
    items = []
    if user_can_access_menu(request.user, MODULE_NAS_STORAGE, 'browse'):
        items.append({'key': 'browse', 'label': 'Duyệt thư mục', 'url': reverse('nas_storage:browse')})
    if user_can_access_menu(request.user, MODULE_NAS_STORAGE, 'permissions'):
        items.append({
            'key': 'permissions',
            'label': 'Phân quyền thư mục',
            'url': reverse('nas_storage:permissions_hub'),
        })
    return {
        'nas_nav_items': items,
        'nas_nav_active': active,
        **menu_perm_context(request.user, MODULE_NAS_STORAGE, active),
    }


def _perm_breadcrumbs(*crumbs: tuple[str, str | None]) -> list[dict]:
    """crumbs: (label, url_or_none) — None = trang hiện tại."""
    return [{'label': label, 'url': url} for label, url in crumbs]


def _perm_subnav_context(perm_subnav_active: str) -> dict:
    return {
        'perm_subnav_active': perm_subnav_active,
        'perm_subnav_items': [
            {
                'key': 'shares',
                'label': 'Phân quyền share',
                'url': reverse('nas_storage:permissions_hub'),
            },
            {
                'key': 'special',
                'label': 'Truy cập riêng',
                'url': reverse('nas_storage:special_access_list'),
            },
        ],
    }


def _perm_page_ctx(request, perm_subnav: str, **extra) -> dict:
    return {
        **_nav_context(request, 'permissions'),
        **_perm_subnav_context(perm_subnav),
        **extra,
    }


@_perm_menu_required
def permissions_hub(request):
    folders = (
        NasShareFolder.objects.filter(is_active=True)
        .annotate(
            perm_count=Count('permissions'),
            applied_count=Count('permissions', filter=Q(permissions__last_applied_at__isnull=False)),
        )
        .order_by('sort_order', 'share_name')
    )
    groups = NasAccessGroup.objects.filter(is_active=True)
    return render(
        request,
        'nas_storage/permissions_hub.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folders': folders,
            'groups': groups,
            'ssh_configured': nas_acl_ssh_configured(),
            'breadcrumbs': _perm_breadcrumbs(('NAS', reverse('nas_storage:permissions_hub'))),
        },
    )


@_perm_menu_required
def group_list(request):
    groups = NasAccessGroup.objects.all()
    return render(
        request,
        'nas_storage/group_list.html',
        {**_perm_page_ctx(request, 'shares'), 'groups': groups},
    )


@_perm_menu_required
def special_access_list(request):
    hub_url = reverse('nas_storage:permissions_hub')
    special_url = reverse('nas_storage:special_access_list')
    base_ctx = _perm_page_ctx(
        request,
        'special',
        breadcrumbs=_perm_breadcrumbs(
            ('NAS', hub_url),
            ('Phân quyền', hub_url),
            ('Truy cập riêng', special_url),
        ),
        nas_folders_available=nas_folders_feature_available(),
    )

    if not nas_folders_feature_available():
        return render(request, 'nas_storage/special_access_list.html', {
            **base_ctx,
            'users': [],
            'page_obj': None,
            'query_string': '',
            'search_query': '',
            'only_special': True,
        })

    only_special = request.GET.get('only_special', '1') != '0'
    search_query = get_search_query(request)
    users_qs = User.objects.select_related('profile', 'profile__department')
    users_qs = exclude_hidden_hrm_users(users_qs)
    users_qs = filter_users_by_search(users_qs, search_query)
    users_qs = users_qs.annotate(
        nas_folder_count=Count(
            'nas_folder_accesses',
            filter=Q(nas_folder_accesses__is_active=True),
        ),
    )
    if only_special:
        users_qs = users_qs.filter(nas_folder_count__gt=0)
    users_qs = users_qs.prefetch_related(
        Prefetch(
            'nas_folder_accesses',
            queryset=NasUserFolderAccess.objects.filter(is_active=True).order_by('sort_order', 'id'),
            to_attr='active_nas_folders',
        ),
    ).order_by('-nas_folder_count', 'profile__full_name', 'username')
    page_obj, query_string = paginate_queryset(request, users_qs)

    return render(
        request,
        'nas_storage/special_access_list.html',
        {
            **base_ctx,
            'users': page_obj.object_list,
            'page_obj': page_obj,
            'query_string': query_string,
            'search_query': search_query,
            'only_special': only_special,
        },
    )


@_perm_menu_required
def special_access_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    profile, _created = Profile.objects.get_or_create(user=user_obj)
    hub_url = reverse('nas_storage:permissions_hub')
    special_url = reverse('nas_storage:special_access_list')
    edit_url = reverse('nas_storage:special_access_edit', kwargs={'user_id': user_obj.pk})
    page_ctx = _perm_page_ctx(
        request,
        'special',
        breadcrumbs=_perm_breadcrumbs(
            ('NAS', hub_url),
            ('Phân quyền', hub_url),
            ('Truy cập riêng', special_url),
            (user_obj.username, edit_url),
        ),
    )

    if request.method == 'POST':
        ctx = nas_folders_page_context(user_obj, post_data=request.POST)
        if ctx['nas_migration_missing']:
            messages.error(request, 'Chưa migrate bảng NAS trên server.')
        elif ctx['nas_formset'].is_valid():
            save_user_nas_folder_formset(user_obj, ctx['nas_formset'])
            messages.success(request, f'Đã lưu thư mục NAS riêng cho {user_obj.username}.')
            return redirect('nas_storage:special_access_edit', user_id=user_obj.pk)
        else:
            messages.error(request, 'Kiểm tra lại bảng đường dẫn NAS.')
        return render(
            request,
            'nas_storage/special_access_edit.html',
            {'user_instance': user_obj, 'profile': profile, **page_ctx, **ctx},
        )

    ctx = nas_folders_page_context(user_obj)
    return render(
        request,
        'nas_storage/special_access_edit.html',
        {'user_instance': user_obj, 'profile': profile, **page_ctx, **ctx},
    )


@_perm_menu_required
def group_edit(request, pk=None):
    instance = get_object_or_404(NasAccessGroup, pk=pk) if pk else None
    if request.method == 'POST':
        form = NasAccessGroupForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã lưu nhóm quyền NAS.')
            return redirect('nas_storage:group_list')
    else:
        form = NasAccessGroupForm(instance=instance)
    return render(
        request,
        'nas_storage/group_form.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'form': form,
            'editing': bool(instance),
        },
    )


@_perm_menu_required
def folder_list(request):
    folders = NasShareFolder.objects.all()
    return render(
        request,
        'nas_storage/folder_list.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folders': folders,
            'ssh_configured': nas_acl_ssh_configured(),
        },
    )


@_perm_menu_required
def folder_edit(request, pk=None):
    instance = get_object_or_404(NasShareFolder, pk=pk) if pk else None
    if request.method == 'POST':
        form = NasShareFolderForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã lưu thư mục NAS.')
            return redirect('nas_storage:folder_list')
    else:
        form = NasShareFolderForm(instance=instance)
    return render(
        request,
        'nas_storage/folder_form.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'form': form,
            'editing': bool(instance),
        },
    )


@_perm_menu_required
def folder_permissions(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    permissions = folder.permissions.select_related('group').order_by('group__sort_order', 'group__name')
    hub_url = reverse('nas_storage:permissions_hub')
    folder_url = reverse('nas_storage:folder_permissions', kwargs={'pk': folder.pk})
    return render(
        request,
        'nas_storage/folder_permissions.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folder': folder,
            'permissions': permissions,
            'read_fields': READ_FIELDS,
            'write_fields': WRITE_FIELDS,
            'admin_fields': ADMIN_FIELDS,
            'ssh_configured': nas_acl_ssh_configured(),
            'breadcrumbs': _perm_breadcrumbs(
                ('NAS', hub_url),
                ('Phân quyền', hub_url),
                (folder.display_name, folder_url),
            ),
        },
    )


def _form_fields_by_defs(form, field_defs):
    return [{'name': name, 'label': label, 'field': form[name]} for name, label in field_defs]


@_perm_menu_required
def permission_edit(request, folder_pk, pk=None):
    folder = get_object_or_404(NasShareFolder, pk=folder_pk)
    instance = get_object_or_404(NasFolderPermission, pk=pk, folder=folder) if pk else None
    if request.method == 'POST':
        form = NasFolderPermissionForm(request.POST, instance=instance, folder=folder)
        if form.is_valid():
            perm = form.save(commit=False)
            perm.folder = folder
            perm.save()
            messages.success(request, 'Đã lưu quyền chi tiết.')
            return redirect('nas_storage:folder_permissions', pk=folder.pk)
    else:
        form = NasFolderPermissionForm(instance=instance, folder=folder)
    hub_url = reverse('nas_storage:permissions_hub')
    folder_url = reverse('nas_storage:folder_permissions', kwargs={'pk': folder.pk})
    edit_label = 'Sửa quyền' if instance else 'Thêm quyền'
    return render(
        request,
        'nas_storage/permission_editor.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folder': folder,
            'form': form,
            'editing': bool(instance),
            'read_form_fields': _form_fields_by_defs(form, READ_FIELDS),
            'write_form_fields': _form_fields_by_defs(form, WRITE_FIELDS),
            'admin_form_fields': _form_fields_by_defs(form, ADMIN_FIELDS),
            'ssh_configured': nas_acl_ssh_configured(),
            'breadcrumbs': _perm_breadcrumbs(
                ('NAS', hub_url),
                ('Phân quyền', hub_url),
                (folder.display_name, folder_url),
                (edit_label, None),
            ),
        },
    )


@_perm_menu_required
@require_POST
def permission_delete(request, folder_pk, pk):
    folder = get_object_or_404(NasShareFolder, pk=folder_pk)
    perm = get_object_or_404(NasFolderPermission, pk=pk, folder=folder)
    perm.delete()
    messages.success(request, 'Đã xóa quyền.')
    return redirect('nas_storage:folder_permissions', pk=folder.pk)


@_perm_menu_required
@require_POST
def apply_folder_acl(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    try:
        result = apply_folder_permissions(folder)
        if result.get('status') == 'ok':
            messages.success(request, f'Đã áp dụng quyền lên NAS cho {folder.share_name}.')
        else:
            messages.warning(request, 'Không có quyền nào để áp dụng.')
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:folder_permissions', pk=folder.pk)


@_perm_menu_required
@require_POST
def apply_all_acl(request):
    try:
        stats = apply_all_folder_permissions()
        if stats['errors']:
            messages.warning(
                request,
                f"Áp dụng xong: {stats['ok']} OK, {stats['skipped']} bỏ qua. "
                f"Lỗi: {'; '.join(stats['errors'][:3])}",
            )
        else:
            messages.success(request, f'Đã áp dụng {stats["ok"]} thư mục lên NAS.')
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:permissions_hub')


@_perm_menu_required
@require_POST
def import_shares_from_nas(request):
    try:
        discovered = discover_shares_from_nas()
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:folder_list')

    created = 0
    for item in discovered:
        _, was_created = NasShareFolder.objects.get_or_create(
            share_name=item['share_name'],
            defaults={'display_name': item['display_name']},
        )
        if was_created:
            created += 1
    messages.success(request, f'Đã quét NAS: {len(discovered)} share, thêm mới {created}.')
    return redirect('nas_storage:folder_list')
