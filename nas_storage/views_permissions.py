"""Quản trị phân quyền shared folder NAS."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from hrm.menu_permissions import menu_perm_context, user_can_update_menu
from hrm.models import Profile
from hrm.module_permissions import MODULE_NAS_STORAGE
from hrm.user_search import exclude_hidden_hrm_users, filter_users_by_search
from nas_storage.forms import (
    NasAccessGroupForm,
    NasFolderPermissionForm,
    NasShareFolderChildForm,
    NasShareFolderRootForm,
    NasUserFolderAclFormSet,
)
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder, NasUserFolderAcl
from nas_storage.nas_acl_apply import (
    NasAclApplyError,
    apply_all_folder_permissions,
    apply_all_user_folder_acls,
    apply_folder_permissions,
    apply_user_folder_acl,
    discover_shares_from_nas,
    discover_share_tree_from_nas,
    import_folder_tree_from_nas,
    _count_tree_children,
    nas_acl_ssh_configured,
    provision_portal_folder_on_nas,
    revoke_user_folder_acl,
)
from nas_storage.portal_access import (
    sync_browse_all_share_permissions,
    users_auto_in_nas_group,
    users_excluded_from_nas_group,
)
from nas_storage.permission_defs import ADMIN_FIELDS, READ_FIELDS, WRITE_FIELDS
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset
from nas_storage.dept_nas_config import DEPT_NAS_SPECS, nas_group_for_portal_department
from nas_storage.folder_permissions_resolved import (
    effective_folder_permissions,
    local_folder_permissions,
)
from nas_storage.folder_tree import build_folder_tree

logger = logging.getLogger(__name__)


def _perm_menu_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_update_menu(request.user, MODULE_NAS_STORAGE, 'permissions'):
            messages.error(request, 'Bạn không có quyền cấu hình phân quyền NAS.')
            return redirect('nas_storage:browse')
        return view_func(request, *args, **kwargs)

    return wrapper


def _nav_context(request, active: str) -> dict:
    return {
        'nas_nav_items': [],
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
                'label': 'Tổng quan',
                'url': reverse('nas_storage:permissions_hub'),
            },
            {
                'key': 'groups',
                'label': 'Nhóm quyền',
                'url': reverse('nas_storage:group_list'),
            },
            {
                'key': 'special',
                'label': 'Truy cập theo User',
                'url': reverse('nas_storage:special_access_list'),
            },
            {
                'key': 'folder_manage',
                'label': 'Quản lý Folder',
                'url': reverse('nas_storage:folder_list'),
            },
        ],
    }


def _perm_page_ctx(request, perm_subnav: str, **extra) -> dict:
    return {
        **_nav_context(request, 'permissions'),
        **_perm_subnav_context(perm_subnav),
        'ssh_configured': nas_acl_ssh_configured(),
        **extra,
    }


def _provision_folder_after_save(request, folder) -> None:
    """Lưu Portal xong → tạo thư mục/share trên NAS + áp dụng phân quyền."""
    if not nas_acl_ssh_configured():
        messages.success(
            request,
            'Đã lưu trên Portal. Cấu hình SSH NAS để tự tạo thư mục trên thiết bị.',
        )
        return
    try:
        result = provision_portal_folder_on_nas(folder)
        if result.get('action') == 'mkdir':
            msg = f'Đã tạo thư mục {result["path"]} trên NAS.'
        elif result.get('action') == 'share_add':
            msg = f'Đã tạo share {result["share"]} trên NAS.'
        elif result.get('reason') == 'share_exists':
            msg = f'Share {result["share"]} đã có trên NAS — đã đăng ký Portal.'
        else:
            msg = 'Đã lưu và đồng bộ lên NAS.'
        try:
            apply_result = apply_folder_permissions(folder)
            if apply_result.get('status') == 'ok':
                msg += ' Đã áp dụng phân quyền.'
        except NasAclApplyError as exc:
            messages.warning(request, f'Đã tạo thư mục nhưng chưa áp dụng quyền: {exc}')
        messages.success(request, msg)
    except NasAclApplyError as exc:
        messages.warning(request, f'Đã lưu Portal nhưng chưa tạo trên NAS: {exc}')
        messages.success(request, 'Đã lưu trên Portal.')


@_perm_menu_required
def permissions_hub(request):
    folders = (
        NasShareFolder.objects.filter(is_active=True, parent__isnull=True)
        .annotate(
            perm_count=Count('permissions'),
            applied_count=Count('permissions', filter=Q(permissions__last_applied_at__isnull=False)),
        )
        .order_by('sort_order', 'share_name')
    )
    pending_apply_count = sum(
        1 for f in folders if f.perm_count and f.applied_count < f.perm_count
    )
    return render(
        request,
        'nas_storage/permissions_hub.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folders': folders,
            'pending_apply_count': pending_apply_count,
        },
    )


@_perm_menu_required
def group_list(request):
    groups = (
        NasAccessGroup.objects.filter(is_active=True)
        .prefetch_related('portal_members', 'portal_excluded_members')
        .order_by('sort_order', 'name')
    )
    return render(
        request,
        'nas_storage/group_list.html',
        {
            **_perm_page_ctx(request, 'groups'),
            'groups': groups,
        },
    )


def _dept_share_hint(user) -> tuple[str | None, list[str]]:
    profile = getattr(user, 'profile', None)
    dept_name = profile.department.name if profile and profile.department_id else None
    group = nas_group_for_portal_department(dept_name)
    shares = sorted({
        spec.share_name
        for spec in DEPT_NAS_SPECS
        if spec.nas_group == group and spec.share_name
    })
    return group, shares


def _user_acl_formset(*, user: User, data=None):
    qs = NasUserFolderAcl.objects.filter(user=user).select_related('folder').order_by(
        'folder__sort_order', 'sub_path',
    )
    if data is None:
        return NasUserFolderAclFormSet(queryset=qs, prefix='user_acl')
    return NasUserFolderAclFormSet(data, queryset=qs, prefix='user_acl')


def _save_user_acl_formset(user: User, formset) -> list:
    from nas_storage.user_folders import ensure_portal_link_for_acl

    saved: list = []
    instances = formset.save(commit=False)
    for obj in instances:
        obj.user = user
        obj.save()
        if obj.is_active:
            ensure_portal_link_for_acl(obj)
        saved.append(obj)
    for obj in formset.deleted_objects:
        if obj.pk and nas_acl_ssh_configured():
            try:
                revoke_user_folder_acl(obj)
            except NasAclApplyError:
                pass
        obj.delete()
    return saved


@_perm_menu_required
def special_access_list(request):
    base_ctx = _perm_page_ctx(
        request,
        'special',
        ssh_configured=nas_acl_ssh_configured(),
    )

    only_special = request.GET.get('only_special', '1') != '0'
    search_query = get_search_query(request)
    users_qs = User.objects.select_related('profile', 'profile__department')
    users_qs = exclude_hidden_hrm_users(users_qs)
    users_qs = filter_users_by_search(users_qs, search_query)
    users_qs = users_qs.annotate(
        acl_count=Count(
            'nas_folder_acls',
            filter=Q(nas_folder_acls__is_active=True),
        ),
    )
    if only_special:
        users_qs = users_qs.filter(acl_count__gt=0)
    users_qs = users_qs.prefetch_related(
        Prefetch(
            'nas_folder_acls',
            queryset=NasUserFolderAcl.objects.filter(is_active=True).select_related('folder'),
            to_attr='active_user_acls',
        ),
    ).order_by('-acl_count', 'profile__full_name', 'username')
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
    dept_group, dept_shares = _dept_share_hint(user_obj)
    page_ctx = _perm_page_ctx(
        request,
        'special',
        breadcrumbs=_perm_breadcrumbs(
            ('Phân quyền', hub_url),
            ('Truy cập theo User', special_url),
            (user_obj.username, None),
        ),
        ssh_configured=nas_acl_ssh_configured(),
        dept_group=dept_group,
        dept_shares=dept_shares,
    )

    if request.method == 'POST':
        formset = _user_acl_formset(user=user_obj, data=request.POST)
        if formset.is_valid():
            saved_grants = _save_user_acl_formset(user_obj, formset)
            msg = f'Đã lưu quyền RaiDrive/SMB cho {user_obj.username}.'
            if nas_acl_ssh_configured() and saved_grants:
                applied = 0
                apply_errors: list[str] = []
                for grant in saved_grants:
                    if not grant.is_active:
                        continue
                    try:
                        apply_user_folder_acl(grant)
                        applied += 1
                    except NasAclApplyError as exc:
                        apply_errors.append(str(exc))
                if applied:
                    msg += f' Đã áp dụng {applied} ACL lên NAS.'
                if apply_errors:
                    messages.warning(
                        request,
                        'Một số ACL chưa áp dụng được lên NAS: ' + '; '.join(apply_errors[:2]),
                    )
            messages.success(request, msg)
            return redirect('nas_storage:special_access_edit', user_id=user_obj.pk)
        messages.error(request, 'Kiểm tra lại bảng quyền thư mục riêng.')
        return render(
            request,
            'nas_storage/special_access_edit.html',
            {'user_instance': user_obj, 'profile': profile, 'acl_formset': formset, **page_ctx},
        )

    return render(
        request,
        'nas_storage/special_access_edit.html',
        {
            'user_instance': user_obj,
            'profile': profile,
            'acl_formset': _user_acl_formset(user=user_obj),
            **page_ctx,
        },
    )


@_perm_menu_required
@require_POST
def apply_user_acl(request, pk):
    grant = get_object_or_404(NasUserFolderAcl, pk=pk)
    try:
        apply_user_folder_acl(grant)
        messages.success(
            request,
            f'Đã áp dụng ACL lên NAS: {grant.volume_target_path()} → {grant.resolved_user_principal()}',
        )
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:special_access_edit', user_id=grant.user_id)


@_perm_menu_required
@require_POST
def apply_all_user_acl(request):
    try:
        stats = apply_all_user_folder_acls()
        if stats['errors']:
            messages.warning(
                request,
                f"Áp dụng xong: {stats['ok']} OK. Lỗi: {'; '.join(stats['errors'][:3])}",
            )
        else:
            messages.success(request, f'Đã áp dụng {stats["ok"]} quyền user lên NAS.')
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:special_access_list')


@_perm_menu_required
def group_edit(request, pk=None):
    instance = get_object_or_404(NasAccessGroup, pk=pk) if pk else None
    if request.method == 'POST':
        form = NasAccessGroupForm(request.POST, instance=instance)
        if form.is_valid():
            group = form.save()
            if group.portal_browse_all:
                stats = sync_browse_all_share_permissions()
                messages.info(
                    request,
                    f'Đã gán quyền đọc {stats["permissions_created"] + stats["permissions_updated"]} '
                    f'cặp nhóm–share cho nhóm xem tất cả.',
                )
            messages.success(request, 'Đã lưu nhóm quyền NAS.')
            return redirect('nas_storage:group_list')
    else:
        form = NasAccessGroupForm(instance=instance)
    group_name = instance.name if instance else ''
    if request.method == 'POST' and not group_name:
        group_name = (request.POST.get('name') or '').strip()
    excluded_user_ids: set[int] = set()
    if request.method == 'POST':
        excluded_user_ids = {
            int(x) for x in request.POST.getlist('portal_excluded_members') if str(x).isdigit()
        }
    elif instance:
        excluded_user_ids = set(instance.portal_excluded_members.values_list('pk', flat=True))
    dept_auto_members = users_auto_in_nas_group(group_name, excluded_user_ids=excluded_user_ids)
    dept_excluded_members = users_excluded_from_nas_group(
        group_name, excluded_user_ids=excluded_user_ids,
    )
    extra_member_ids: set[int] = set()
    if request.method == 'POST':
        extra_member_ids = {int(x) for x in request.POST.getlist('portal_members') if str(x).isdigit()}
    elif instance:
        extra_member_ids = set(instance.portal_members.values_list('pk', flat=True))
    return render(
        request,
        'nas_storage/group_form.html',
        {
            **_perm_page_ctx(request, 'groups'),
            'form': form,
            'editing': bool(instance),
            'group_instance': instance,
            'group_name': group_name,
            'dept_auto_members': dept_auto_members,
            'dept_excluded_members': dept_excluded_members,
            'excluded_user_ids': excluded_user_ids,
            'extra_member_ids': extra_member_ids,
        },
    )


@_perm_menu_required
def folder_list(request):
    all_folders = list(
        NasShareFolder.objects.order_by('sort_order', 'share_name', 'sub_path')
    )
    folder_tree = build_folder_tree(all_folders)
    return render(
        request,
        'nas_storage/folder_list.html',
        {
            **_perm_page_ctx(request, 'folder_manage'),
            'folder_tree': folder_tree,
        },
    )


@_perm_menu_required
def folder_edit(request, pk=None):
    instance = get_object_or_404(NasShareFolder, pk=pk) if pk else None
    is_child = bool(instance and instance.parent_id)
    parent = instance.parent if is_child else None

    if request.method == 'POST':
        if is_child:
            form = NasShareFolderChildForm(request.POST, instance=instance, parent=parent)
        else:
            form = NasShareFolderRootForm(request.POST, instance=instance)
        if form.is_valid():
            folder = form.save()
            if instance:
                messages.success(request, 'Đã lưu thư mục NAS.')
                if nas_acl_ssh_configured() and is_child:
                    try:
                        provision_portal_folder_on_nas(folder)
                        messages.info(request, 'Đã cập nhật thư mục trên NAS.')
                    except NasAclApplyError as exc:
                        messages.warning(request, f'Chưa cập nhật NAS: {exc}')
            else:
                _provision_folder_after_save(request, folder)
            return redirect('nas_storage:folder_list')
    else:
        if is_child:
            form = NasShareFolderChildForm(instance=instance, parent=parent)
        else:
            form = NasShareFolderRootForm(instance=instance)
    return render(
        request,
        'nas_storage/folder_form.html',
        {
            **_perm_page_ctx(request, 'folder_manage'),
            'form': form,
            'editing': bool(instance),
            'is_child': is_child,
            'parent': parent,
        },
    )


@_perm_menu_required
def folder_child_create(request, parent_pk):
    parent = get_object_or_404(NasShareFolder, pk=parent_pk)
    if request.method == 'POST':
        form = NasShareFolderChildForm(request.POST, parent=parent)
        if form.is_valid():
            folder = form.save()
            _provision_folder_after_save(request, folder)
            return redirect('nas_storage:folder_list')
    else:
        form = NasShareFolderChildForm(parent=parent)
    return render(
        request,
        'nas_storage/folder_form.html',
        {
            **_perm_page_ctx(request, 'folder_manage'),
            'form': form,
            'editing': False,
            'is_child': True,
            'parent': parent,
        },
    )


@_perm_menu_required
@require_POST
def folder_provision_nas(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    if not nas_acl_ssh_configured():
        messages.error(request, 'Chưa cấu hình SSH NAS.')
        return redirect('nas_storage:folder_list')
    try:
        from nas_storage.nas_paths import normalize_volume_path

        if folder.is_root:
            folder.volume_path = normalize_volume_path(
                folder.volume_path,
                share_name=folder.share_name,
            )
            folder.save(update_fields=['volume_path', 'updated_at'])
        result = provision_portal_folder_on_nas(folder)
        apply_folder_permissions(folder)
        label = folder.portal_path_label()
        if result.get('action') == 'mkdir':
            messages.success(request, f'Đã tạo thư mục {result["path"]} trên NAS.')
        elif result.get('action') == 'share_add':
            messages.success(request, f'Đã tạo share {result["share"]} trên NAS.')
        else:
            messages.success(request, f'Đã đồng bộ «{label}» lên NAS.')
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:folder_list')


@_perm_menu_required
@require_POST
def folder_delete(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    label = folder.portal_path_label()
    folder.delete()
    messages.success(
        request,
        f'Đã gỡ «{label}» khỏi Portal. Thư mục trên NAS không bị xóa — có thể quét lại để đăng ký.',
    )
    return redirect('nas_storage:folder_list')


@_perm_menu_required
def folder_permissions(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    effective = effective_folder_permissions(folder)
    local_permissions = local_folder_permissions(folder)
    hub_url = reverse('nas_storage:permissions_hub')
    folder_url = reverse('nas_storage:folder_permissions', kwargs={'pk': folder.pk})
    return render(
        request,
        'nas_storage/folder_permissions.html',
        {
            **_perm_page_ctx(request, 'shares'),
            'folder': folder,
            'effective_permissions': effective,
            'local_permissions': local_permissions,
            'read_fields': READ_FIELDS,
            'write_fields': WRITE_FIELDS,
            'admin_fields': ADMIN_FIELDS,
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
            msg = 'Đã lưu quyền chi tiết.'
            if nas_acl_ssh_configured():
                try:
                    result = apply_folder_permissions(folder)
                    if result.get('status') == 'ok':
                        msg += f' Đã đồng bộ ACL lên NAS ({folder.portal_path_label()}).'
                except NasAclApplyError as exc:
                    messages.warning(request, f'Đã lưu trên Portal nhưng chưa đẩy NAS: {exc}')
            messages.success(request, msg)
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
    msg = 'Đã xóa quyền.'
    if nas_acl_ssh_configured():
        try:
            result = apply_folder_permissions(folder)
            if result.get('status') == 'ok':
                msg += f' Đã gỡ/đồng bộ ACL lên NAS ({folder.portal_path_label()}).'
        except NasAclApplyError as exc:
            messages.warning(request, f'Đã xóa trên Portal nhưng chưa đẩy NAS: {exc}')
    messages.success(request, msg)
    return redirect('nas_storage:folder_permissions', pk=folder.pk)


@_perm_menu_required
@require_POST
def apply_folder_acl(request, pk):
    folder = get_object_or_404(NasShareFolder, pk=pk)
    try:
        result = apply_folder_permissions(folder)
        if result.get('status') == 'ok':
            messages.success(request, f'Đã áp dụng quyền lên NAS cho {folder.portal_path_label()}.')
        elif result.get('reason') == 'no_changes':
            messages.info(request, f'ACL NAS đã khớp Portal cho {folder.portal_path_label()}.')
        else:
            messages.warning(request, 'Không có quyền nào để áp dụng.')
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
    return redirect('nas_storage:folder_permissions', pk=folder.pk)


@_perm_menu_required
@require_POST
def apply_all_acl(request):
    try:
        sync_browse_all_share_permissions()
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
    except Exception as exc:
        logger.exception('apply_all_acl failed')
        messages.error(request, f'Lỗi khi áp dụng ACL lên NAS: {exc}')
    return redirect('nas_storage:permissions_hub')


@_perm_menu_required
@require_POST
def import_shares_from_nas(request):
    try:
        discovered = discover_share_tree_from_nas(max_child_depth=2)
    except NasAclApplyError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:folder_list')

    child_total = sum(_count_tree_children(t.get('children') or []) for t in discovered)
    stats = import_folder_tree_from_nas(discovered)
    msg = (
        f'Đã quét NAS: {len(discovered)} share, {child_total} thư mục con (tối đa 2 cấp). '
        f'Thêm mới {stats["roots_created"]} share, {stats["children_created"]} thư mục con.'
    )
    if stats['roots_updated']:
        msg += f' Cập nhật {stats["roots_updated"]} share.'
    messages.success(request, msg)
    return redirect('nas_storage:folder_list')
