import copy
import io
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy, reverse
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.db import IntegrityError
import re
from django.db import transaction
from django.db.models import Count, Prefetch, Q
# Import từ các app khác sang
from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_CHOICES, MODULE_HRM, MODULE_LABELS, MODULE_PERMISSIONS
from assessment.decorators import module_perm_required, module_perm_required_methods
from assessment.forms import UserForm # Tạm thời Form vẫn để ở nhà cũ, mốt mình dời sau
from django.utils.text import slugify
from hrm.models import (
    Profile,
    ProfileConcurrentPosition,
    Department,
    Division,
    DivisionPosition,
    DepartmentMenuPermission,
    PermissionGroup,
    RoleModulePermission,
)
from hrm.role_permissions import ROLE_LABELS, default_role_permissions
from hrm.permissions import ROLE_CHOICES, ROLE_EMPLOYEE
from hrm.choices import (
    EXCEL_ALL_HEADERS,
    row_to_profile_data,
    profile_defaults_from_import,
    user_to_excel_row,
)
from datetime import date

from PortalJustPlay.utils import (
    PROBATION_JOB_LABEL,
    generate_hm_email,
    generate_hm_username,
    generate_secure_password,
    get_probation_permission_group,
    next_employee_code,
    suggest_hm_credentials,
)
from hrm.forms import (
    CustomUserForm,
    DepartmentForm,
    DepartmentMenuPermissionForm,
    DivisionForm,
    PermissionGroupMetaForm,
    PermissionGroupPermissionForm,
    ProfileConcurrentPositionForm,
    ProfileConcurrentPositionFormSet,
    ProfileConcurrentPositionEditFormSet,
    RolePermissionForm,
)
from hrm.user_search import (
    EMPLOYMENT_STATUS_LABELS,
    build_user_list_table_columns,
    exclude_hidden_hrm_users,
    is_protected_system_user,
    filter_users_by_department,
    filter_users_by_division,
    filter_users_by_employment_status,
    filter_users_by_job_position,
    filter_users_by_search,
    distinct_job_positions_for_filter,
    apply_user_list_sort,
    redirect_user_list_preserve_filters,
    resolve_user_list_sort,
    user_list_nav_query_string,
    user_list_url,
)
from PortalJustPlay.list_search import apply_term_search, apply_user_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from django.http import JsonResponse
import random
import string


def _permission_config_url(tab: str = '') -> str:
    url = reverse('permission_config')
    if tab:
        return f'{url}?tab={tab}'
    return url


def _resolve_permission_group(form):
    """Chọn tay hoặc fallback nhóm vai trò mặc định (mac-dinh-*)."""
    selected = form.cleaned_data.get('permission_group')
    if selected:
        return selected
    from hrm.group_permissions import default_group_for_role
    return default_group_for_role(form.cleaned_data.get('role'))


def _profile_fields_from_form(form):
    return {
        'employee_code': form.cleaned_data.get('employee_code') or None,
        'full_name': form.cleaned_data['full_name'],
        'department': form.cleaned_data.get('department'),
        'division': form.cleaned_data.get('division'),
        'job_position': (form.cleaned_data.get('job_position') or '').strip(),
        'job_title': form.cleaned_data.get('job_title', ''),
        'join_date': form.cleaned_data.get('join_date'),
        'date_of_birth': form.cleaned_data.get('date_of_birth'),
        'gender': form.cleaned_data.get('gender', ''),
        'role': form.cleaned_data['role'],
        'permission_group': _resolve_permission_group(form),
        'must_change_password': True,
        'is_employed': form.cleaned_data.get('is_employed', True),
    }


def _user_form_extra_context():
    import json

    from hrm.org_structure import divisions_allowed_by_department_map

    return {
        'divisions_allowed_by_dept': json.dumps(divisions_allowed_by_department_map()),
        'subordinate_candidates_url': reverse('user_subordinate_candidates'),
    }


def _profile_for_user_edit(user_obj):
    profile, created = Profile.objects.get_or_create(user=user_obj)
    if created:
        return profile
    return (
        Profile.objects.select_related('department', 'division', 'permission_group', 'user')
        .prefetch_related(
            'subordinates',
            'concurrent_positions__department',
            'concurrent_positions__division',
            'concurrent_positions__subordinates',
        )
        .get(pk=profile.pk)
    )


def _user_edit_page_context(profile):
    permission_group = profile.permission_group
    return {
        'subordinate_count': profile.subordinates.filter(profile__is_employed=True).count(),
        'concurrent_active_count': profile.concurrent_positions.filter(is_active=True).count(),
        'permission_group_label': permission_group.name if permission_group else None,
    }


def _user_edit_render_context(profile, user_obj, request, *, list_return_query: str = ''):
    from hrm.module_permissions import user_can_update_module

    if not list_return_query and request.method == 'POST':
        list_return_query = (request.POST.get('list_return_query') or '').strip()
    if not list_return_query:
        list_return_query = user_list_nav_query_string(request)

    return {
        **_user_form_extra_context(),
        **_user_edit_page_context(profile),
        'concurrent_slot_save_url': reverse('user_concurrent_slot_save', args=[user_obj.id]),
        'can_update_user': user_can_update_module(request.user, MODULE_HRM),
        'list_return_query': list_return_query,
        'user_list_url': (
            f"{reverse('user_list')}?{list_return_query}"
            if list_return_query
            else user_list_url(request)
        ),
    }


# ==========================================
# 1. QUẢN LÝ DANH SÁCH NHÂN VIÊN
# ==========================================
@module_perm_required(MODULE_HRM, 'view')
def user_list(request):
    sort_key, sort_dir, _order_fields = resolve_user_list_sort(
        request.GET.get('sort'),
        request.GET.get('dir'),
    )
    search_query = get_search_query(request)
    department_id = (request.GET.get('department') or '').strip()
    division_id = (request.GET.get('division') or '').strip()
    job_position = (request.GET.get('position') or '').strip()
    employment_status = (request.GET.get('status') or '').strip().lower()
    if employment_status not in EMPLOYMENT_STATUS_LABELS:
        employment_status = ''

    users_qs = User.objects.select_related(
        'profile',
        'profile__department',
        'profile__division',
        'profile__permission_group',
    ).prefetch_related(
        Prefetch(
            'profile__concurrent_positions',
            queryset=ProfileConcurrentPosition.objects.filter(
                is_active=True,
            ).select_related('department', 'division'),
        ),
    )
    users_qs = exclude_hidden_hrm_users(users_qs)
    users_qs = filter_users_by_search(users_qs, search_query)
    users_qs = filter_users_by_department(users_qs, department_id)
    users_qs = filter_users_by_division(users_qs, division_id)
    users_qs = filter_users_by_job_position(users_qs, job_position)
    users_qs = filter_users_by_employment_status(users_qs, employment_status)
    users_qs = apply_user_list_sort(users_qs, sort_key, sort_dir)
    page_obj, query_string = paginate_queryset(request, users_qs)

    from hrm.models import Division
    from hrm.org_structure import (
        divisions_catalog_for_filter,
        divisions_filter_map_for_user_list,
        divisions_for_user_list_filter,
    )
    from hrm.user_search import job_positions_cascade_for_filter

    departments = Department.objects.filter(is_active=True).order_by('sort_order', 'name')
    current_department_label = ''
    if department_id == 'none':
        current_department_label = 'Chưa gán phòng ban'
    elif department_id.isdigit():
        dept = departments.filter(pk=int(department_id)).first()
        if dept:
            current_department_label = dept.name

    if department_id == 'none':
        from hrm.models import Division as DivisionModel
        divisions = DivisionModel.objects.none()
    else:
        dept_pk = int(department_id) if department_id.isdigit() else None
        divisions = divisions_for_user_list_filter(dept_pk)
    current_division_label = ''
    if division_id == 'none':
        current_division_label = 'Chưa gán bộ phận'
    elif division_id.isdigit():
        div = divisions.filter(pk=int(division_id)).first()
        if not div:
            div = Division.objects.filter(pk=int(division_id)).first()
        if div:
            current_division_label = div.name

    job_positions = distinct_job_positions_for_filter(
        department_id=department_id,
        division_id=division_id,
    )
    current_position_label = ''
    if job_position == 'none':
        current_position_label = 'Chưa có vị trí'
    elif job_position:
        current_position_label = job_position

    import json

    return render(request, 'assessment/admin/user_list.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'nav_query_string': user_list_nav_query_string(request, page_obj.number),
        'sort_col': sort_key,
        'sort_dir': sort_dir,
        'table_columns': build_user_list_table_columns(request, sort_key, sort_dir),
        'search_query': search_query,
        'current_status': employment_status,
        'current_status_label': EMPLOYMENT_STATUS_LABELS.get(employment_status, ''),
        'employment_status_options': EMPLOYMENT_STATUS_LABELS,
        'departments': departments,
        'divisions': divisions,
        'job_positions': job_positions,
        'current_department': department_id,
        'current_department_label': current_department_label,
        'current_division': division_id,
        'current_division_label': current_division_label,
        'current_position': job_position,
        'current_position_label': current_position_label,
        'divisions_filter_map': json.dumps(divisions_filter_map_for_user_list()),
        'divisions_catalog': json.dumps(divisions_catalog_for_filter()),
        'positions_cascade': json.dumps(job_positions_cascade_for_filter()),
        'filters_active': bool(
            search_query or department_id or division_id or job_position or employment_status,
        ),
    })


@module_perm_required(MODULE_HRM, 'create')
def user_add(request):
    draft_profile = Profile()
    if request.method == 'POST':
        form = CustomUserForm(request.POST)
        concurrent_formset = ProfileConcurrentPositionFormSet(
            request.POST,
            instance=draft_profile,
            prefix='concurrent',
        )
        avatar_upload = request.FILES.get('avatar')
        if form.is_valid() and concurrent_formset.is_valid():
            u = form.cleaned_data['username']
            p = form.cleaned_data['password']
            e = form.cleaned_data['email']
            f = form.cleaned_data['full_name']

                user = User.objects.create_user(
                    username=u, 
                    email=e, 
                    password=p, 
                first_name=f,
                )
            profile, _ = Profile.objects.update_or_create(
                    user=user, 
                defaults=_profile_fields_from_form(form),
            )
            profile.subordinates.set(form.cleaned_data['subordinates'])
            profile.save()
            if avatar_upload and _save_profile_avatar(profile, avatar_upload, request) is False:
                messages.warning(request, 'Đã thêm nhân viên nhưng không lưu được avatar — kiểm tra lại file ảnh.')
            concurrent_formset.instance = profile
            concurrent_formset.save()
            messages.success(
                request,
                f'Thành công: Đã thêm {f}. Tài khoản: {u} | Mật khẩu: {p}',
            )
                return redirect('user_list')

        messages.error(request, 'Không lưu được — vui lòng kiểm tra các ô báo đỏ bên dưới.')
    else:
        initial = {
            'password': generate_secure_password(),
            'join_date': date.today(),
            'job_position': PROBATION_JOB_LABEL,
            'job_title': PROBATION_JOB_LABEL,
            'role': ROLE_EMPLOYEE,
            'employee_code': next_employee_code(),
        }
        probation_group = get_probation_permission_group()
        if probation_group:
            initial['permission_group'] = probation_group.pk
        dept_id = (request.GET.get('department') or '').strip()
        div_id = (request.GET.get('division') or '').strip()
        job_position = (request.GET.get('job_position') or '').strip()
        role = (request.GET.get('role') or '').strip().upper()
        if dept_id.isdigit():
            initial['department'] = int(dept_id)
        if div_id.isdigit():
            initial['division'] = int(div_id)
        if job_position:
            initial['job_position'] = job_position
        from hrm.permissions import ROLE_CHOICES

        valid_roles = {code for code, _ in ROLE_CHOICES}
        if role in valid_roles:
            initial['role'] = role
        form = CustomUserForm(initial=initial)
        concurrent_formset = ProfileConcurrentPositionFormSet(
            instance=draft_profile,
            prefix='concurrent',
        )
    
    return render(request, 'assessment/admin/user_form.html', {
        'form': form, 
        'concurrent_formset': concurrent_formset,
        'title': 'Thêm nhân viên mới',
        'is_edit': False,
        'profile': draft_profile,
        'subordinate_count': 0,
        'concurrent_active_count': 0,
        **_user_form_extra_context(),
    })


@module_perm_required(MODULE_HRM, 'view')
@require_GET
def user_suggest_username(request):
    """Gợi ý account / email / mã NS từ họ tên (form thêm/sửa NV)."""
    full_name = (request.GET.get('full_name') or '').strip()
    if not full_name:
        return JsonResponse({'username': '', 'email': '', 'employee_code': ''})

    exclude_raw = (request.GET.get('exclude_user_id') or '').strip()
    exclude_user_id = int(exclude_raw) if exclude_raw.isdigit() else None
    include_code = (request.GET.get('include_employee_code') or '1').strip() not in ('0', 'false', 'no')

    return JsonResponse(
        suggest_hm_credentials(
            full_name,
            exclude_user_id=exclude_user_id,
            include_employee_code=include_code,
        )
    )


@module_perm_required(MODULE_HRM, 'view')
@require_GET
def user_subordinate_candidates(request):
    """Danh sách NV có thể gán cấp dưới — cập nhật user_picker khi đổi phòng/vai trò."""
    from hrm.user_search import (
        subordinate_candidate_queryset,
        subordinate_candidates_json,
        subordinate_scope_hint,
    )

    exclude_raw = (request.GET.get('exclude_user_id') or '').strip()
    exclude_user_id = int(exclude_raw) if exclude_raw.isdigit() else None
    manager_role = (request.GET.get('role') or '').strip()
    department_id = (request.GET.get('department') or '').strip() or None
    division_id = (request.GET.get('division') or '').strip() or None
    extra_user_ids = [int(x) for x in request.GET.getlist('extra') if str(x).isdigit()]

    qs = subordinate_candidate_queryset(
        exclude_user_id=exclude_user_id,
        manager_role=manager_role,
        department_id=department_id,
        division_id=division_id,
        extra_user_ids=extra_user_ids,
    )
    users = subordinate_candidates_json(qs)
    return JsonResponse({
        'count': len(users),
        'scope_hint': subordinate_scope_hint(
            manager_role=manager_role,
            department_id=department_id,
            division_id=division_id,
        ),
        'users': users,
    })


AVATAR_MAX_SIZE = 5 * 1024 * 1024


def _save_profile_avatar(profile, upload, request):
    """Lưu avatar — dùng chung sidebar và form sửa nhân sự."""
    from django.core.exceptions import ValidationError
    from tasks.attachment_utils import validate_image_file

    from .avatar_utils import prepare_avatar_image

    if not upload:
        return None
    try:
        validate_image_file(upload)
    except ValidationError as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return False
    if upload.size > AVATAR_MAX_SIZE:
        messages.error(request, 'Ảnh avatar tối đa 5 MB.')
        return False
    try:
        prepared = prepare_avatar_image(upload)
    except Exception:
        messages.error(request, 'Không xử lý được ảnh avatar. Vui lòng chọn file JPG/PNG/WebP hợp lệ.')
        return False
    if profile.avatar:
        profile.avatar.delete(save=False)
    profile.avatar.save(prepared.name, prepared, save=False)
    profile.save(update_fields=['avatar'])
    return True


@module_perm_required(MODULE_HRM, 'update')
def user_nas_folders(request, user_id):
    """Cấu hình thư mục NAS riêng cho từng tài khoản."""
    from nas_storage.user_folders import (
        copy_department_defaults_to_user,
        nas_folders_feature_available,
        nas_folders_page_context,
        save_user_nas_folder_formset,
        user_has_custom_nas_folders,
    )

    user_obj = get_object_or_404(User, id=user_id)
    profile, _created = Profile.objects.get_or_create(user=user_obj)

    if request.method == 'POST' and request.POST.get('nas_copy_defaults'):
        if not nas_folders_feature_available():
            messages.error(
                request,
                'Chưa migrate nas_storage trên server. Chạy: python manage.py migrate nas_storage',
            )
        else:
            created_count = copy_department_defaults_to_user(user_obj)
            if created_count:
                messages.success(
                    request,
                    f'Đã tạo {created_count} thư mục từ map mặc định phòng ban.',
                )
            elif user_has_custom_nas_folders(user_obj):
                messages.info(request, 'User đã có thư mục NAS tùy chỉnh.')
            else:
                messages.warning(
                    request,
                    'Không có map mặc định (chưa gán phòng ban hoặc mã thư mục).',
                )
        return redirect('user_nas_folders', user_id=user_obj.id)

    if request.method == 'POST':
        ctx = nas_folders_page_context(user_obj, post_data=request.POST)
        if ctx['nas_migration_missing']:
            messages.error(request, 'Chưa migrate bảng NAS trên server.')
        elif ctx['nas_formset'].is_valid():
            save_user_nas_folder_formset(user_obj, ctx['nas_formset'])
            messages.success(request, 'Đã lưu link NAS cho tài khoản này.')
            return redirect('user_nas_folders', user_id=user_obj.id)
        else:
            messages.error(request, 'Kiểm tra lại bảng đường dẫn NAS.')
        return render(
            request,
            'assessment/admin/user_nas_folders.html',
            {
                'user_instance': user_obj,
                'profile': profile,
                **ctx,
            },
        )

    ctx = nas_folders_page_context(user_obj)
    return render(
        request,
        'assessment/admin/user_nas_folders.html',
        {
            'user_instance': user_obj,
            'profile': profile,
            **ctx,
        },
    )


@module_perm_required_methods(MODULE_HRM, get='view', post='update')
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    profile = _profile_for_user_edit(user_obj)

    if request.method == 'POST':
        # TRUYỀN user_id VÀO ĐÂY: Để hàm clean_username trong forms.py không báo lỗi trùng chính mình
        form = CustomUserForm(request.POST, user_id=user_obj.id)
        
        # Đang sửa nên không bắt buộc nhập mật khẩu
        form.fields['password'].required = False 

        # Slot kiêm nhiệm khi sửa NV: lưu từng slot qua AJAX — không ghi qua POST «Lưu nhân viên»
        # (tránh tạo bản ghi trùng khi TOTAL_FORMS / id slot lệch sau thêm dòng trên UI).
        if form.is_valid():
            # 1. Cập nhật bảng User mặc định của Django
            user_obj.username = form.cleaned_data['username']
            user_obj.email = form.cleaned_data['email']
            user_obj.first_name = form.cleaned_data['full_name']
            
            # Chỉ cập nhật mật khẩu nếu sếp có nhập vào ô password
            new_password = form.cleaned_data.get('password')
            if new_password:
                user_obj.set_password(new_password)
            
            user_obj.save()

            # 2. Cập nhật bảng Profile (Logic HRM của mình)
            profile.full_name = form.cleaned_data['full_name']
            profile.employee_code = form.cleaned_data.get('employee_code') or None
            profile.department = form.cleaned_data.get('department')
            profile.division = form.cleaned_data.get('division')
            profile.job_position = (form.cleaned_data.get('job_position') or '').strip()
            profile.job_title = form.cleaned_data.get('job_title', '')
            profile.join_date = form.cleaned_data.get('join_date')
            profile.date_of_birth = form.cleaned_data.get('date_of_birth')
            profile.gender = form.cleaned_data.get('gender', '')
            profile.role = form.cleaned_data['role']
            profile.permission_group = _resolve_permission_group(form)
            profile.is_employed = form.cleaned_data.get('is_employed', True)
            
            # QUAN TRỌNG: Lưu danh sách nhân viên cấp dưới (ManyToMany)
            # Dùng .set() để ghi đè danh sách mới từ form
            profile.subordinates.set(form.cleaned_data['subordinates'])
            
            # Hàm save() của profile sẽ tự xử lý quyền nếu role là Giám đốc
            profile.save()

            avatar_upload = request.FILES.get('avatar')
            if avatar_upload:
                avatar_result = _save_profile_avatar(profile, avatar_upload, request)
                if avatar_result is False:
                    concurrent_formset = ProfileConcurrentPositionEditFormSet(
                        instance=profile,
                        prefix='concurrent',
                    )
                    return render(request, 'assessment/admin/user_form.html', {
                        'form': form,
                        'concurrent_formset': concurrent_formset,
                        'title': profile.full_name or user_obj.username,
                        'is_edit': True,
                        'user_instance': user_obj,
                        'profile': profile,
                        'force_edit_mode': True,
                        **_user_edit_render_context(profile, user_obj, request),
                    })

            messages.success(request, f"Cập nhật {profile.full_name} thành công!")
            return redirect_user_list_preserve_filters(request, from_post=True)
        else:
            messages.error(request, "Vui lòng kiểm tra lại dữ liệu nhập vào.")
        concurrent_formset = ProfileConcurrentPositionEditFormSet(
            instance=profile,
            prefix='concurrent',
        )
    else:
        # Đổ dữ liệu hiện tại vào Form để sếp thấy mà sửa
        initial_data = {
            'username': user_obj.username,
            'email': user_obj.email,
            'employee_code': profile.employee_code or '',
            'full_name': profile.full_name,
            'department': profile.department,
            'division': profile.division,
            'job_position': profile.job_position or '',
            'job_title': profile.job_title,
            'join_date': profile.join_date,
            'date_of_birth': profile.date_of_birth,
            'gender': profile.gender,
            'role': profile.role,
            'permission_group': profile.permission_group,
            'is_employed': '1' if profile.is_employed else '0',
            'subordinates': profile.subordinates.all(),
        }
        # Truyền user_id để form biết đường loại trừ chính mình khỏi danh sách chọn cấp dưới
        form = CustomUserForm(initial=initial_data, user_id=user_obj.id)
        form.fields['password'].required = False
        concurrent_formset = ProfileConcurrentPositionEditFormSet(
            instance=profile,
            prefix='concurrent',
        )

    force_edit_mode = request.method == 'POST'
    return render(request, 'assessment/admin/user_form.html', {
        'form': form, 
        'concurrent_formset': concurrent_formset,
        'title': profile.full_name or user_obj.username,
        'is_edit': True,
        'user_instance': user_obj,
        'profile': profile,
        'force_edit_mode': force_edit_mode,
        **_user_edit_render_context(profile, user_obj, request),
    })
@module_perm_required(MODULE_HRM, 'update')
@require_POST
def user_concurrent_slot_save(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(Profile, user=user_obj)

    form_prefix = (request.POST.get('form_prefix') or '').strip()
    if not re.match(r'^concurrent-\d+$', form_prefix):
        return JsonResponse({'status': 'error', 'message': 'Form slot không hợp lệ.'}, status=400)

    slot_id = (
        request.POST.get('slot_id')
        or request.POST.get(f'{form_prefix}-id')
        or ''
    ).strip()
    delete_flag = (
        (request.POST.get('slot_action') or '').strip().lower() == 'delete'
        or request.POST.get(f'{form_prefix}-DELETE') in ('on', 'true', '1', 'True')
    )

    instance = None
    if slot_id.isdigit():
        instance = get_object_or_404(
            ProfileConcurrentPosition,
            pk=int(slot_id),
            profile=profile,
        )

    if delete_flag:
        if instance and instance.pk:
            instance.delete()
            return JsonResponse({
                'status': 'ok',
                'deleted': True,
                'concurrent_active_count': profile.concurrent_positions.filter(is_active=True).count(),
            })
        return JsonResponse({
            'status': 'error',
            'message': 'Slot chưa lưu — xóa dòng trên màn hình.',
        }, status=400)

    form = ProfileConcurrentPositionForm(
        request.POST,
        instance=instance or ProfileConcurrentPosition(profile=profile),
        prefix=form_prefix,
    )
    if not form.is_valid():
        flat_errors = []
        for field, errs in form.errors.items():
            for err in errs:
                label = field
                if field in form.fields:
                    label = form.fields[field].label or field
                flat_errors.append(f'{label}: {err}')
        return JsonResponse({
            'status': 'error',
            'message': flat_errors[0] if flat_errors else 'Kiểm tra lại dữ liệu slot.',
            'errors': form.errors,
        }, status=400)

    slot = form.save(commit=False)
    slot.profile = profile
    try:
        slot.save()
    except IntegrityError:
        return JsonResponse({
            'status': 'error',
            'message': 'Trùng slot kiêm nhiệm đang hiệu lực (phòng/bộ phận/vị trí).',
        }, status=400)

    if 'subordinates' in form.cleaned_data:
        slot.subordinates.set(form.cleaned_data['subordinates'])

    return JsonResponse({
        'status': 'ok',
        'slot_id': slot.pk,
        'is_active': slot.is_active,
        'concurrent_active_count': profile.concurrent_positions.filter(is_active=True).count(),
        'form_prefix': form_prefix,
    })


@module_perm_required(MODULE_HRM, 'delete')
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if is_protected_system_user(user):
        messages.error(request, "Không thể xóa tài khoản quản trị hệ thống!")
    else:
        deleted_email = user.email 
        user.delete()
        
        # Đồng bộ trạng thái thẻ Kanban bên Recruitment
        if deleted_email:
            try:
                from recruitment.models import Candidate
                Candidate.objects.filter(email=deleted_email, status='hired').update(status='interviewing')
            except:
                pass
                
        messages.success(request, "Đã xóa nhân viên khỏi hệ thống.")
    return redirect('user_list')

@module_perm_required(MODULE_HRM, 'create')
def user_import_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        try:
            df = pd.read_excel(file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            df = df.fillna('')
            
            success_count = 0
            updated_count = 0
            skipped_count = 0
            
            with transaction.atomic():
                for _, row in df.iterrows():
                    data = row_to_profile_data(row)
                    full_name = data.get('full_name', '').strip()
                    if not full_name:
                        skipped_count += 1
                        continue 

                    username = data.get('username', '').strip()
                    employee_code = data.get('employee_code', '').strip() or None

                    existing_user = None
                    if username:
                        existing_user = User.objects.filter(username=username).select_related('profile').first()
                    if not existing_user and employee_code:
                        profile_match = Profile.objects.filter(employee_code=employee_code).select_related('user').first()
                        if profile_match:
                            existing_user = profile_match.user

                    if existing_user:
                        if employee_code:
                            code_clash = Profile.objects.filter(employee_code=employee_code).exclude(user=existing_user).exists()
                            if code_clash:
                                skipped_count += 1
                                continue

                        profile_defaults = profile_defaults_from_import(data)
                        _ensure_division_position_from_profile(profile_defaults)

                        existing_user.first_name = full_name
                        email = data.get('email', '').strip()
                        if email:
                            existing_user.email = email
                        password = data.get('password', '').strip()
                        if password:
                            existing_user.set_password(password)
                        existing_user.save()

                        Profile.objects.update_or_create(
                            user=existing_user,
                            defaults=profile_defaults,
                        )
                        updated_count += 1
                        continue

                    if not username:
                        username = generate_hm_username(full_name)

                    if User.objects.filter(username=username).exists():
                        skipped_count += 1
                        continue

                    if employee_code and Profile.objects.filter(employee_code=employee_code).exists():
                        skipped_count += 1
                        continue

                    password = data.get('password', '').strip() or generate_secure_password()
                    email = data.get('email', '').strip() or generate_hm_email(username)

                        user = User.objects.create_user(
                            username=username,
                            password=password,
                            email=email,
                            first_name=full_name,
                        is_staff=False,
                        )
                    new_defaults = profile_defaults_from_import(data)
                    _ensure_division_position_from_profile(new_defaults)
                        Profile.objects.update_or_create(
                            user=user,
                        defaults={
                            **new_defaults,
                            'must_change_password': True,
                        },
                        )
                        success_count += 1
            
            messages.success(
                request,
                f'Import xong: thêm mới {success_count}, cập nhật {updated_count}, bỏ qua {skipped_count} dòng.',
            )
            
        except Exception as e:
            messages.error(request, f'Lỗi hệ thống khi xử lý file: {str(e)}')
            
    if request.POST.get('return_to') == 'org':
        return redirect('org_structure')
    return redirect('user_list')

@module_perm_required(MODULE_HRM, 'export')
def user_export_excel(request):
    search_query = get_search_query(request)
    department_id = (request.GET.get('department') or '').strip()
    division_id = (request.GET.get('division') or '').strip()
    job_position = (request.GET.get('position') or '').strip()
    employment_status = (request.GET.get('status') or '').strip().lower()
    if employment_status not in EMPLOYMENT_STATUS_LABELS:
        employment_status = ''
    _sort_key, _sort_dir, _order_fields = resolve_user_list_sort(
        request.GET.get('sort'),
        request.GET.get('dir'),
    )

    users = User.objects.select_related(
        'profile',
        'profile__department',
        'profile__division',
        'profile__permission_group',
    )
    users = exclude_hidden_hrm_users(users)
    users = filter_users_by_search(users, search_query)
    users = filter_users_by_department(users, department_id)
    users = filter_users_by_division(users, division_id)
    users = filter_users_by_job_position(users, job_position)
    users = filter_users_by_employment_status(users, employment_status)
    users = apply_user_list_sort(users, _sort_key, _sort_dir)
    rows = [user_to_excel_row(u) for u in users]
    df = pd.DataFrame(rows, columns=EXCEL_ALL_HEADERS)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Nhan_Vien')
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=Danh_sach_nhan_vien.xlsx'
    return response


def _ensure_division_position_from_profile(profile_defaults: dict) -> None:
    """Tạo vị trí danh mục khi import NV có bộ phận + tên vị trí."""
    division = profile_defaults.get('division')
    job_position = (profile_defaults.get('job_position') or '').strip()
    if not division or not job_position:
        return
    from hrm.models import DivisionPosition

    DivisionPosition.objects.get_or_create(
        division=division,
        name=job_position,
        defaults={
            'department': profile_defaults.get('department') or division.department,
            'is_active': True,
        },
    )


@module_perm_required(MODULE_HRM, 'create')
def user_download_template(request):
    from hrm.excel_template import build_import_template_xlsx

    content = build_import_template_xlsx()
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_Nhan_Vien.xlsx'
    return response


def _org_redirect(anchor='', tab=''):
    """Quay lại sơ đồ; mở panel Cập nhật sơ đồ (tab: departments | divisions)."""
    url = reverse('org_structure')
    if tab:
        url = f'{url}?tab={tab}'
    frag = anchor if anchor else 'org-manage-panel'
    url = f'{url}#{frag}'
    return redirect(url)


def _org_redirect_for_division(division):
    return _org_redirect(tab='divisions')


@module_perm_required(MODULE_HRM, 'view')
def org_structure(request):
    from django.db.utils import OperationalError, ProgrammingError

    from hrm.org_structure import build_org_tree, build_org_treemap, filter_org_tree

    search_query = get_search_query(request)
    try:
        treemap = build_org_treemap()
    except (OperationalError, ProgrammingError) as exc:
        err = str(exc).lower()
        if 'department_id' in err or 'division' in err:
            messages.error(
                request,
                'Chưa migrate cơ cấu tổ chức. IT chạy: python manage.py migrate hrm',
            )
            treemap = None
        else:
            raise
    if treemap is None:
        return render(request, 'assessment/admin/org_structure.html', {
            'treemap': None,
            'search_query': search_query,
            'max_treemap_weight': 1,
            'org_structure_clear_url': reverse('org_structure'),
            'migration_required': True,
        })
    if search_query:
        q = search_query.lower()
        treemap.departments = [
            dept for dept in treemap.departments
            if q in dept.name.lower()
            or any(q in div.name.lower() for div in dept.divisions)
        ]
        for dept in treemap.departments:
            dept.divisions = [
                div for div in dept.divisions if q in div.name.lower() or q in dept.name.lower()
            ]
        treemap.unassigned_divisions = [
            div for div in treemap.unassigned_divisions if q in div.name.lower()
        ]
    tree_data = build_org_tree(treemap)
    if search_query:
        filtered = filter_org_tree(tree_data, search_query)
        if filtered is not None:
            tree_data = filtered

    def _pat(name, pk=0):
        return reverse(name, args=[pk]).replace(f'/{pk}/', '/{id}/')

    from urllib.parse import quote

    from hrm.org_structure import (
        ORG_DEPARTMENT_HEAD_LABEL,
        ORG_DIVISION_HEAD_LABEL,
    )
    from hrm.permissions import ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR, ROLE_DIVISION_HEAD

    urls = {
        'userList': reverse('user_list'),
        'userAdd': reverse('user_add') + '?department={dept_id}&division={div_id}&job_position={position}',
        'departmentAdd': reverse('department_add'),
        'divisionAdd': reverse('division_add') + '?department={dept_id}',
        'positionAdd': reverse('org_position_add') + '?department={dept_id}&division={div_id}',
        'deptHeadAssign': (
            reverse('user_add')
            + f'?department={{dept_id}}&job_position={quote(ORG_DEPARTMENT_HEAD_LABEL)}'
            + f'&role={ROLE_DEPARTMENT_HEAD}'
        ),
        'divHeadAssign': (
            reverse('user_add')
            + f'?department={{dept_id}}&division={{div_id}}'
            + f'&job_position={quote(ORG_DIVISION_HEAD_LABEL)}'
            + f'&role={ROLE_DIVISION_HEAD}'
        ),
        'directorAssign': reverse('user_add') + f'?role={ROLE_DIRECTOR}',
        'deptEdit': _pat('department_edit'),
        'deptDelete': _pat('department_delete'),
        'deptPermissions': _pat('department_permissions'),
        'divEdit': _pat('division_edit'),
        'divDelete': _pat('division_delete'),
        'positionEdit': _pat('org_position_edit'),
        'positionDelete': _pat('org_position_delete'),
        'userEdit': _pat('user_edit'),
        'userImport': reverse('user_import_excel'),
        'importTemplate': reverse('user_download_template'),
    }

    from hrm.org_structure import _org_profile_count_filter

    manage_departments = (
        Department.objects.annotate(
            staff_count=Count(
                'profiles',
                filter=_org_profile_count_filter('profiles__'),
                distinct=True,
            ),
            division_count=Count('divisions', distinct=True),
        )
        .order_by('sort_order', 'name')
    )
    manage_divisions = (
        Division.objects.select_related('department')
        .annotate(
            staff_count=Count(
                'division_profiles',
                filter=_org_profile_count_filter('division_profiles__'),
                distinct=True,
            ),
        )
        .order_by('department__sort_order', 'department__name', 'sort_order', 'name')
    )

    manage_tab = (request.GET.get('tab') or 'departments').strip()
    if manage_tab not in ('departments', 'divisions'):
        manage_tab = 'departments'

    return render(request, 'assessment/admin/org_structure.html', {
        'treemap': treemap,
        'search_query': search_query,
        'org_structure_clear_url': reverse('org_structure'),
        'org_tree': tree_data,
        'org_urls': urls,
        'manage_departments': manage_departments,
        'manage_divisions': manage_divisions,
        'manage_tab': manage_tab,
    })


@module_perm_required(MODULE_HRM, 'view')
def department_list(request):
    return _org_redirect()


@module_perm_required(MODULE_HRM, 'create')
def department_add(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            from hrm.models import DepartmentMenuPermission

            DepartmentMenuPermission.objects.get_or_create(
                department=department,
                defaults={'modules': sorted(ALL_MODULE_KEYS)},
            )
            messages.success(request, f'Đã thêm phòng ban "{department.name}".')
            return _org_redirect(tab='departments')
    else:
        form = DepartmentForm()
    return render(request, 'assessment/admin/department_form.html', {
        'form': form,
        'title': 'Thêm phòng ban',
    })


@module_perm_required(MODULE_HRM, 'update')
def department_edit(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'Đã cập nhật phòng ban "{department.name}".')
            return _org_redirect(tab='departments')
    else:
        form = DepartmentForm(instance=department)
    return render(request, 'assessment/admin/department_form.html', {
        'form': form,
        'title': 'Sửa phòng ban',
        'department': department,
        'is_edit': True,
    })


@module_perm_required(MODULE_HRM, 'delete')
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        if department.employee_count:
            messages.error(
                request,
                f'Không thể xóa "{department.name}" vì còn {department.employee_count} nhân viên.',
            )
        else:
            name = department.name
            department.delete()
            messages.success(request, f'Đã xóa phòng ban "{name}".')
        return _org_redirect(tab='departments')
    return render(request, 'assessment/admin/department_confirm_delete.html', {
        'department': department,
    })


@module_perm_required(MODULE_PERMISSIONS, 'update')
def department_permissions(request, pk):
    department = get_object_or_404(Department, pk=pk)
    perm, _ = DepartmentMenuPermission.objects.get_or_create(
        department=department,
        defaults={'modules': sorted(ALL_MODULE_KEYS)},
    )

    if request.method == 'POST':
        form = DepartmentMenuPermissionForm(request.POST)
        if form.is_valid():
            perm.modules = form.cleaned_data.get('modules') or []
            perm.save()
            messages.success(
                request,
                f'Đã cập nhật phân quyền menu cho phòng ban "{department.name}".',
            )
            return redirect('permission_config')
    else:
        form = DepartmentMenuPermissionForm(initial={
            'modules': perm.modules if perm.modules else sorted(ALL_MODULE_KEYS),
        })

    return render(request, 'assessment/admin/department_permissions.html', {
        'department': department,
        'form': form,
        'employee_count': department.employee_count,
    })


@module_perm_required(MODULE_PERMISSIONS, 'view')
def permission_config(request):
    search_query = get_search_query(request)
    departments_qs = Department.objects.annotate(
        staff_count=Count('profiles'),
    ).order_by('sort_order', 'name')
    departments_qs = apply_term_search(departments_qs, search_query, 'name__icontains')
    dept_page, query_string = paginate_queryset(request, departments_qs)

    rows = []
    for dept in dept_page.object_list:
        enabled = dept.get_enabled_modules()
        rows.append({
            'department': dept,
            'enabled_labels': [MODULE_LABELS[key] for key, _ in MODULE_CHOICES if key in enabled],
        })

    from hrm.department_permission_templates import is_protected_permission_group, PROTECTED_GROUP_SLUG_PREFIX
    from hrm.user_search import visible_employed_profiles

    employed_profile_q = Q(profiles__is_employed=True)
    member_profiles_qs = visible_employed_profiles().select_related(
        'user', 'department',
    ).order_by('full_name', 'user__username')
    group_qs = PermissionGroup.objects.annotate(
        profile_count=Count('profiles', filter=employed_profile_q),
    ).prefetch_related(
        Prefetch('profiles', queryset=member_profiles_qs, to_attr='member_profiles'),
    ).exclude(slug__startswith=PROTECTED_GROUP_SLUG_PREFIX)
    sorted_groups = sorted(group_qs, key=lambda g: g.name.casefold())

    group_rows = []
    for group in sorted_groups:
        group_rows.append({
            'group': group,
            'is_deletable': not is_protected_permission_group(group.slug),
        })

    return render(request, 'assessment/admin/permission_config.html', {
        'departments': dept_page.object_list,
        'rows': rows,
        'page_obj': dept_page,
        'query_string': query_string,
        'search_query': search_query,
        'group_rows': group_rows,
        'active_tab': request.GET.get('tab', 'dept'),
    })


def _unique_group_slug(base: str) -> str:
    slug = slugify(base) or 'nhom-quyen'
    if not PermissionGroup.objects.filter(slug=slug).exists():
        return slug
    n = 2
    while PermissionGroup.objects.filter(slug=f'{slug}-{n}').exists():
        n += 1
    return f'{slug}-{n}'


def _unique_group_name(base: str) -> str:
    root = (base or 'Nhóm quyền').strip()
    candidate = f'{root} (bản sao)'
    if not PermissionGroup.objects.filter(name=candidate).exists():
        return candidate
    n = 2
    while PermissionGroup.objects.filter(name=f'{root} (bản sao {n})').exists():
        n += 1
    return f'{root} (bản sao {n})'


def _permission_group_form_context(meta_form, perm_form, title, *, group=None, is_edit=False):
    from hrm.department_permission_templates import is_protected_permission_group

    perm_action_meta = [
        {'key': 'view', 'label': 'Xem', 'icon': 'bi-eye', 'tone': 'view'},
        {'key': 'create', 'label': 'Thêm', 'icon': 'bi-plus-lg', 'tone': 'create'},
        {'key': 'update', 'label': 'Sửa', 'icon': 'bi-pencil', 'tone': 'update'},
        {'key': 'delete', 'label': 'Xóa', 'icon': 'bi-trash', 'tone': 'delete'},
        {'key': 'export', 'label': 'Excel', 'icon': 'bi-file-earmark-spreadsheet', 'tone': 'export'},
    ]
    return {
        'meta_form': meta_form,
        'perm_form': perm_form,
        'title': title,
        'is_edit': is_edit,
        'group': group,
        'perm_actions': [a['key'] for a in perm_action_meta],
        'perm_action_meta': perm_action_meta,
        'perm_config_back_url': _permission_config_url('group'),
        'is_group_deletable': bool(group and not is_protected_permission_group(group.slug)),
        'group_profile_count': group.profiles.count() if group else 0,
    }


@module_perm_required(MODULE_PERMISSIONS, 'create')
def permission_group_add(request):
    if request.method == 'POST':
        meta_form = PermissionGroupMetaForm(request.POST)
        perm_form = PermissionGroupPermissionForm(request.POST)
        if meta_form.is_valid() and perm_form.is_valid():
            group = meta_form.save(commit=False)
            group.slug = _unique_group_slug(group.name)
            group.is_system = False
            group.module_permissions = perm_form.cleaned_permissions()
            group.save()
            messages.success(request, f'Đã tạo nhóm quyền "{group.name}".')
            return redirect(_permission_config_url('group'))
    else:
        meta_form = PermissionGroupMetaForm()
        perm_form = PermissionGroupPermissionForm()

    return render(request, 'assessment/admin/permission_group_form.html', _permission_group_form_context(
        meta_form, perm_form, 'Thêm nhóm quyền', is_edit=False,
    ))


@module_perm_required(MODULE_PERMISSIONS, 'update')
def permission_group_edit(request, pk):
    group = get_object_or_404(PermissionGroup, pk=pk)

    if request.method == 'POST':
        meta_form = PermissionGroupMetaForm(request.POST, instance=group)
        perm_form = PermissionGroupPermissionForm(
            request.POST,
            initial_permissions=group.module_permissions,
        )
        if meta_form.is_valid() and perm_form.is_valid():
            group = meta_form.save()
            group.module_permissions = perm_form.cleaned_permissions()
            group.save()
            messages.success(request, f'Đã cập nhật nhóm quyền "{group.name}".')
            return redirect(_permission_config_url('group'))
    else:
        meta_form = PermissionGroupMetaForm(instance=group)
        perm_form = PermissionGroupPermissionForm(initial_permissions=group.module_permissions)

    return render(request, 'assessment/admin/permission_group_form.html', _permission_group_form_context(
        meta_form, perm_form, f'Chỉnh sửa — {group.name}', group=group, is_edit=True,
    ))


@module_perm_required(MODULE_PERMISSIONS, 'create')
@require_POST
def permission_group_clone(request, pk):
    source = get_object_or_404(PermissionGroup, pk=pk)
    new_name = _unique_group_name(source.name)
    new_group = PermissionGroup.objects.create(
        name=new_name,
        slug=_unique_group_slug(new_name),
        description=source.description,
        is_system=False,
        module_permissions=copy.deepcopy(source.module_permissions or {}),
    )
    messages.success(
        request,
        f'Đã nhân bản «{source.name}» thành «{new_group.name}». Chỉnh sửa và lưu nếu cần.',
    )
    return redirect('permission_group_edit', pk=new_group.pk)


@module_perm_required(MODULE_PERMISSIONS, 'delete')
def permission_group_delete(request, pk):
    from hrm.department_permission_templates import is_protected_permission_group

    group = get_object_or_404(PermissionGroup, pk=pk)
    if is_protected_permission_group(group.slug):
        messages.error(request, 'Không thể xóa nhóm quyền vai trò mặc định hệ thống.')
        return redirect(_permission_config_url('group'))
    if group.profiles.exists():
        messages.error(
            request,
            f'Nhóm "{group.name}" đang được gán cho {group.profiles.count()} nhân viên — hãy đổi nhóm trước khi xóa.',
        )
        return redirect(_permission_config_url('group'))
    name = group.name
    group.delete()
    messages.success(request, f'Đã xóa nhóm quyền "{name}".')
    return redirect(_permission_config_url('group'))


@module_perm_required(MODULE_PERMISSIONS, 'update')
def role_permission_edit(request, role):
    valid_roles = {r for r, _ in ROLE_CHOICES}
    if role not in valid_roles:
        messages.error(request, 'Vai trò không hợp lệ.')
        return redirect('permission_config')

    perm, _ = RoleModulePermission.objects.get_or_create(
        role=role,
        defaults={'module_permissions': default_role_permissions().get(role, {})},
    )
    role_label = ROLE_LABELS.get(role, role)

    if request.method == 'POST':
        form = RolePermissionForm(request.POST, initial_permissions=perm.module_permissions)
        if form.is_valid():
            perm.module_permissions = form.cleaned_permissions()
            perm.save()
            messages.success(request, f'Đã cập nhật phân quyền cho vai trò "{role_label}".')
            return redirect('permission_config')
    else:
        form = RolePermissionForm(initial_permissions=perm.module_permissions)

    return render(request, 'assessment/admin/role_permission_edit.html', {
        'form': form,
        'role': role,
        'role_label': role_label,
    })


@module_perm_required(MODULE_HRM, 'create')
def division_add(request):
    if request.method == 'POST':
        form = DivisionForm(request.POST)
        if form.is_valid():
            division = form.save()
            messages.success(request, f'Đã thêm bộ phận "{division.name}".')
            return _org_redirect_for_division(division)
    else:
        initial = {}
        dept_id = (request.GET.get('department') or '').strip()
        if dept_id.isdigit():
            initial['department'] = int(dept_id)
        form = DivisionForm(initial=initial)
    return render(request, 'assessment/admin/division_form.html', {
        'form': form,
        'title': 'Thêm bộ phận',
    })


@module_perm_required(MODULE_HRM, 'update')
def division_edit(request, pk):
    division = get_object_or_404(Division, pk=pk)
    if request.method == 'POST':
        form = DivisionForm(request.POST, instance=division)
        if form.is_valid():
            division = form.save()
            messages.success(request, f'Đã cập nhật bộ phận "{division.name}".')
            return _org_redirect_for_division(division)
    else:
        form = DivisionForm(instance=division)
    return render(request, 'assessment/admin/division_form.html', {
        'form': form,
        'title': 'Sửa bộ phận',
        'division': division,
        'is_edit': True,
    })


@module_perm_required(MODULE_HRM, 'delete')
def division_delete(request, pk):
    division = get_object_or_404(Division, pk=pk)
    if request.method == 'POST':
        if division.employee_count:
            messages.error(
                request,
                f'Không thể xóa "{division.name}" vì còn {division.employee_count} nhân viên.',
            )
        else:
            name = division.name
            dept_id = division.department_id
            division.delete()
            messages.success(request, f'Đã xóa bộ phận "{name}".')
        return _org_redirect(tab='divisions')
    return render(request, 'assessment/admin/division_confirm_delete.html', {
        'division': division,
    })


@module_perm_required(MODULE_HRM, 'create')
def org_position_add(request):
    from hrm.forms import DivisionPositionForm

    if request.method == 'POST':
        form = DivisionPositionForm(request.POST)
        if form.is_valid():
            position = form.save()
            messages.success(request, f'Đã thêm vị trí "{position.name}".')
            return _org_redirect_for_division(position.division)
    else:
        initial = {}
        div_id = (request.GET.get('division') or '').strip()
        dept_id = (request.GET.get('department') or '').strip()
        if div_id.isdigit():
            initial['division'] = int(div_id)
        elif dept_id.isdigit():
            div = Division.objects.filter(department_id=int(dept_id)).order_by('sort_order', 'name').first()
            if div:
                initial['division'] = div.pk
        form = DivisionPositionForm(initial=initial)
    return render(request, 'assessment/admin/org_position_form.html', {
        'form': form,
        'title': 'Thêm vị trí',
    })


@module_perm_required(MODULE_HRM, 'update')
def org_position_edit(request, pk):
    from hrm.forms import DivisionPositionForm
    from hrm.models import DivisionPosition

    position = get_object_or_404(DivisionPosition, pk=pk)
    if request.method == 'POST':
        form = DivisionPositionForm(request.POST, instance=position)
        if form.is_valid():
            position = form.save()
            moved = getattr(form, 'profiles_synced_count', 0) or 0
            msg = f'Đã cập nhật vị trí "{position.name}".'
            if moved:
                msg += f' Đã chuyển {moved} nhân viên theo bộ phận / vị trí mới.'
            messages.success(request, msg)
            return _org_redirect_for_division(position.division)
    else:
        form = DivisionPositionForm(instance=position)
    return render(request, 'assessment/admin/org_position_form.html', {
        'form': form,
        'title': 'Sửa vị trí',
        'position': position,
        'is_edit': True,
    })


@module_perm_required(MODULE_HRM, 'delete')
def org_position_delete(request, pk):
    from hrm.models import DivisionPosition

    position = get_object_or_404(DivisionPosition, pk=pk)
    if request.method == 'POST':
        in_use = Profile.objects.filter(
            is_employed=True,
            division=position.division,
            job_position=position.name,
        ).exists()
        if in_use:
            messages.error(
                request,
                f'Không thể xóa "{position.name}" vì còn nhân viên đang dùng vị trí này.',
            )
        else:
            name = position.name
            division = position.division
            position.delete()
            messages.success(request, f'Đã xóa vị trí "{name}".')
            return _org_redirect_for_division(division)
        return _org_redirect_for_division(position.division)
    return render(request, 'assessment/admin/org_position_confirm_delete.html', {
        'position': position,
    })


@module_perm_required(MODULE_HRM, 'update')
def user_toggle_employed(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    user_obj = get_object_or_404(User, id=user_id)
    if is_protected_system_user(user_obj):
        return JsonResponse(
            {'status': 'error', 'message': 'Không thể đổi trạng thái tài khoản quản trị hệ thống.'},
            status=400,
        )

    profile, _ = Profile.objects.get_or_create(user=user_obj)
    profile.is_employed = not profile.is_employed
    profile.save()

    return JsonResponse({
        'status': 'success',
        'is_employed': profile.is_employed,
        'label': 'Đang làm' if profile.is_employed else 'Đã nghỉ',
    })


@module_perm_required(MODULE_HRM, 'update')
def user_password_reset(request, user_id):
    if request.method == 'POST':
        user = User.objects.get(id=user_id)
        
        # Tạo mật khẩu ngẫu nhiên mới (Nếu code cũ của ní khác thì thay vào đây)
        characters = string.ascii_letters + string.digits
        new_password = ''.join(random.choice(characters) for i in range(8))
        
        user.set_password(new_password)
        user.save()

        Profile.require_password_change(user)
        
        # Lấy tên hiển thị
        full_name = user.first_name
        if hasattr(user, 'profile') and user.profile.full_name:
            full_name = user.profile.full_name
            
        # QUAN TRỌNG: Trả về JSON để Frontend tự động Copy
        return JsonResponse({
            'status': 'success',
            'username': user.username,
            'password': new_password,
            'full_name': full_name
        })
    return JsonResponse({'status': 'error'})

class MyPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.request.user, 'profile', None)
        context['force_change'] = bool(profile and profile.must_change_password)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=['must_change_password'])
        messages.success(self.request, "Mật khẩu đã được thay đổi thành công!")
        return response


@login_required
def update_avatar(request):
    if request.method != 'POST':
        return redirect('home_portal')

    upload = request.FILES.get('avatar')
    if not upload:
        messages.warning(request, 'Chưa chọn hình ảnh avatar.')
        return redirect(request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('home_portal'))

    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Không tìm thấy hồ sơ nhân viên.')
        return redirect('home_portal')

    if _save_profile_avatar(profile, upload, request) is False:
        return redirect(request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('home_portal'))

    messages.success(request, 'Đã cập nhật avatar.')
    return redirect(request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('home_portal'))


def custom_logout(request):
    logout(request)
    return redirect('login')