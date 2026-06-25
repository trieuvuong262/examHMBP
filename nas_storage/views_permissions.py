"""Quản trị phân quyền shared folder NAS."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from hrm.menu_permissions import menu_perm_context, user_can_update_menu
from hrm.module_permissions import MODULE_NAS_STORAGE
from nas_storage.forms import NasAccessGroupForm, NasFolderPermissionForm, NasShareFolderForm
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import (
    NasAclApplyError,
    apply_all_folder_permissions,
    apply_folder_permissions,
    discover_shares_from_nas,
    nas_acl_ssh_configured,
)
from nas_storage.permission_defs import ADMIN_FIELDS, READ_FIELDS, WRITE_FIELDS


def _perm_menu_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_update_menu(request.user, MODULE_NAS_STORAGE, 'permissions'):
            messages.error(request, 'Bạn không có quyền cấu hình phân quyền NAS.')
            return redirect('nas_storage:browse')
        return view_func(request, *args, **kwargs)

    return wrapper


def _nav_context(request, active: str) -> dict:
    from hrm.menu_permissions import user_can_access_menu

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
        **menu_perm_context(request.user, MODULE_NAS_STORAGE, 'permissions'),
    }


@_perm_menu_required
def permissions_hub(request):
    folders = NasShareFolder.objects.filter(is_active=True).prefetch_related('permissions__group')
    groups = NasAccessGroup.objects.filter(is_active=True)
    return render(
        request,
        'nas_storage/permissions_hub.html',
        {
            **_nav_context(request, 'permissions'),
            'folders': folders,
            'groups': groups,
            'ssh_configured': nas_acl_ssh_configured(),
        },
    )


@_perm_menu_required
def group_list(request):
    groups = NasAccessGroup.objects.all()
    return render(
        request,
        'nas_storage/group_list.html',
        {**_nav_context(request, 'permissions'), 'groups': groups},
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
            **_nav_context(request, 'permissions'),
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
            **_nav_context(request, 'permissions'),
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
            **_nav_context(request, 'permissions'),
            'form': form,
            'editing': bool(instance),
        },
    )


@_perm_menu_required
def folder_permissions(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    permissions = folder.permissions.select_related('group').order_by('group__sort_order', 'group__name')
    return render(
        request,
        'nas_storage/folder_permissions.html',
        {
            **_nav_context(request, 'permissions'),
            'folder': folder,
            'permissions': permissions,
            'read_fields': READ_FIELDS,
            'write_fields': WRITE_FIELDS,
            'admin_fields': ADMIN_FIELDS,
            'ssh_configured': nas_acl_ssh_configured(),
        },
    )


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
    return render(
        request,
        'nas_storage/permission_editor.html',
        {
            **_nav_context(request, 'permissions'),
            'folder': folder,
            'form': form,
            'editing': bool(instance),
            'read_fields': READ_FIELDS,
            'write_fields': WRITE_FIELDS,
            'admin_fields': ADMIN_FIELDS,
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
