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
from django.views.decorators.http import require_GET
from django.db import transaction
from django.db.models import Count
# Import từ các app khác sang
from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_CHOICES, MODULE_LABELS
from assessment.decorators import admin_only
from assessment.forms import UserForm # Tạm thời Form vẫn để ở nhà cũ, mốt mình dời sau
from django.utils.text import slugify
from hrm.models import Profile, Department, Division, DepartmentMenuPermission, PermissionGroup, RoleModulePermission
from hrm.group_permissions import group_list_summary
from hrm.role_permissions import ROLE_LABELS, default_role_permissions
from hrm.permissions import ROLE_CHOICES
from hrm.choices import (
    EXCEL_ALL_HEADERS,
    row_to_profile_data,
    profile_defaults_from_import,
    user_to_excel_row,
)
from PortalJustPlay.utils import generate_hm_username, generate_secure_password
from hrm.forms import (
    CustomUserForm,
    DepartmentForm,
    DepartmentMenuPermissionForm,
    DivisionForm,
    PermissionGroupMetaForm,
    PermissionGroupPermissionForm,
    RolePermissionForm,
)
from hrm.user_search import (
    exclude_hidden_hrm_users,
    filter_users_by_department,
    filter_users_by_search,
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

    from hrm.models import Division

    return {
        'division_dept_map': json.dumps({
            str(pk): dept_id
            for pk, dept_id in Division.objects.values_list('pk', 'department_id')
        }),
    }


# ==========================================
# 1. QUẢN LÝ DANH SÁCH NHÂN VIÊN
# ==========================================
USER_LIST_SORTS = {
    'newest': ('-date_joined', 'Mới thêm nhất'),
    'name_asc': ('profile__full_name', 'Họ và tên (A→Z)'),
    'name_desc': ('-profile__full_name', 'Họ và tên (Z→A)'),
    'code': ('profile__employee_code', 'Mã NS'),
    'account': ('username', 'Account'),
    'department': ('profile__department__name', 'Phòng ban'),
    'division': ('profile__division__name', 'Bộ phận'),
    'join_asc': ('profile__join_date', 'Ngày vào (cũ→mới)'),
    'join_desc': ('-profile__join_date', 'Ngày vào (mới→cũ)'),
    'status': ('-profile__is_employed', 'Trạng thái'),
}


@admin_only
def user_list(request):
    sort_key = request.GET.get('sort', 'newest')
    if sort_key not in USER_LIST_SORTS:
        sort_key = 'newest'
    order_by = USER_LIST_SORTS[sort_key][0]
    search_query = get_search_query(request)
    department_id = (request.GET.get('department') or '').strip()

    users_qs = User.objects.select_related(
        'profile', 'profile__department', 'profile__division',
    )
    users_qs = exclude_hidden_hrm_users(users_qs)
    users_qs = filter_users_by_search(users_qs, search_query)
    users_qs = filter_users_by_department(users_qs, department_id)
    users_qs = users_qs.order_by(order_by, 'username')
    page_obj, query_string = paginate_queryset(request, users_qs)

    departments = Department.objects.filter(is_active=True).order_by('sort_order', 'name')
    current_department_label = ''
    if department_id == 'none':
        current_department_label = 'Chưa gán phòng ban'
    elif department_id.isdigit():
        dept = departments.filter(pk=int(department_id)).first()
        if dept:
            current_department_label = dept.name

    from nas_storage.user_folders import nas_folders_feature_available

    return render(request, 'assessment/admin/user_list.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'sort_key': sort_key,
        'sort_options': USER_LIST_SORTS,
        'search_query': search_query,
        'departments': departments,
        'current_department': department_id,
        'current_department_label': current_department_label,
        'filters_active': bool(search_query or department_id),
        'nas_folders_available': nas_folders_feature_available(),
    })


@admin_only
def user_add(request):
    if request.method == 'POST':
        form = CustomUserForm(request.POST)
        if form.is_valid():
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
            messages.success(
                request,
                f'Thành công: Đã thêm {f}. Tài khoản: {u} | Mật khẩu: {p}',
            )
            return redirect('user_list')

        messages.error(request, 'Không lưu được — vui lòng kiểm tra các ô báo đỏ bên dưới.')
    else:
        form = CustomUserForm(initial={
            'password': generate_secure_password(),
        })

    return render(request, 'assessment/admin/user_form.html', {
        'form': form,
        'title': 'Thêm nhân viên mới',
        'is_edit': False,
        **_user_form_extra_context(),
    })


@admin_only
@require_GET
def user_suggest_username(request):
    """Gợi ý account từ họ tên (form thêm NV)."""
    full_name = (request.GET.get('full_name') or '').strip()
    if not full_name:
        return JsonResponse({'username': ''})
    return JsonResponse({'username': generate_hm_username(full_name)})


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


@admin_only
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


@admin_only
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    # Lấy profile, tự động tạo nếu chưa có
    profile, created = Profile.objects.get_or_create(user=user_obj)

    from nas_storage.user_folders import nas_folders_feature_available

    if request.method == 'POST':
        # TRUYỀN user_id VÀO ĐÂY: Để hàm clean_username trong forms.py không báo lỗi trùng chính mình
        form = CustomUserForm(request.POST, user_id=user_obj.id)

        # Đang sửa nên không bắt buộc nhập mật khẩu
        form.fields['password'].required = False

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

            # QUAN TRỌNG: Lưu danh sách nhân viên cấp dưới (ManyToMany)
            # Dùng .set() để ghi đè danh sách mới từ form
            profile.subordinates.set(form.cleaned_data['subordinates'])
            
            # Hàm save() của profile sẽ tự xử lý quyền nếu role là Giám đốc
            profile.save()

            avatar_upload = request.FILES.get('avatar')
            if avatar_upload:
                avatar_result = _save_profile_avatar(profile, avatar_upload, request)
                if avatar_result is False:
                    return render(request, 'assessment/admin/user_form.html', {
                        'form': form,
                        'title': 'Chỉnh sửa nhân sự',
                        'is_edit': True,
                        'user_instance': user_obj,
                        'profile': profile,
                        'nas_folders_available': nas_folders_feature_available(),
                        **_user_form_extra_context(),
                    })

            messages.success(request, f"Cập nhật {profile.full_name} thành công!")
            return redirect('user_list')
        else:
            messages.error(request, "Vui lòng kiểm tra lại dữ liệu nhập vào.")
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
            'subordinates': profile.subordinates.all(),
        }
        # Truyền user_id để form biết đường loại trừ chính mình khỏi danh sách chọn cấp dưới
        form = CustomUserForm(initial=initial_data, user_id=user_obj.id)
        form.fields['password'].required = False

    return render(request, 'assessment/admin/user_form.html', {
        'form': form,
        'title': 'Chỉnh sửa nhân sự',
        'is_edit': True,
        'user_instance': user_obj,
        'profile': profile,
        'nas_folders_available': nas_folders_feature_available(),
        **_user_form_extra_context(),
    })
@admin_only
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        messages.error(request, "Không thể xóa tài khoản Quản trị tối cao!")
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

@admin_only
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
                    email = data.get('email', '').strip() or f'{username.lower()}@justplay.vn'

                    user = User.objects.create_user(
                        username=username,
                        password=password,
                        email=email,
                        first_name=full_name,
                        is_staff=False,
                    )
                    Profile.objects.update_or_create(
                        user=user,
                        defaults={
                            **profile_defaults_from_import(data),
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

    return redirect('user_list')

@admin_only
def user_export_excel(request):
    from hrm.module_permissions import MODULE_HRM, user_can_export_module
    if not user_can_export_module(request.user, MODULE_HRM):
        messages.error(request, 'Bạn không có quyền xuất Excel danh sách nhân viên.')
        return redirect('user_list')

    search_query = get_search_query(request)
    department_id = (request.GET.get('department') or '').strip()

    users = User.objects.select_related(
        'profile', 'profile__department', 'profile__division',
    )
    users = exclude_hidden_hrm_users(users)
    users = filter_users_by_search(users, search_query)
    users = filter_users_by_department(users, department_id)
    users = users.order_by('profile__employee_code', 'username')
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


@admin_only
def user_download_template(request):
    sample_rows = [
        {
            'Mã NS': 'NV001', 'Họ và tên': 'Nguyễn Văn An', 'Account': 'Annt',
            'Phòng ban': 'SẢN XUẤT', 'Bộ phận': 'QC', 'Vị trí': 'Công nhân may',
            'Chức vụ': 'Nhân viên', 'Ngày vào': '01/01/2026', 'Ngày sinh': '15/05/1995',
            'Giới tính': 'Nam', 'password': 'JustPlay@123', 'email': 'annt@justplay.vn',
        },
        {
            'Mã NS': 'NV002', 'Họ và tên': 'Trần Thị Bình', 'Account': '',
            'Phòng ban': 'ĐẢM BẢO CHẤT LƯỢNG', 'Bộ phận': 'QC', 'Vị trí': 'Nhân viên QC',
            'Chức vụ': 'Nhân viên', 'Ngày vào': '', 'Ngày sinh': '20/08/1998',
            'Giới tính': 'Nữ', 'password': '', 'email': '',
        },
    ]
    df = pd.DataFrame(sample_rows, columns=EXCEL_ALL_HEADERS)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template_Import')

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_Nhan_Vien.xlsx'
    return response


def _org_redirect(anchor=''):
    url = reverse('org_structure')
    if anchor:
        url = f'{url}#{anchor}'
    return redirect(url)


def _org_redirect_for_division(division):
    if division.department_id:
        return _org_redirect(f'dept-{division.department_id}')
    return _org_redirect()


@admin_only
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

    urls = {
        'userList': reverse('user_list'),
        'departmentAdd': reverse('department_add'),
        'divisionAdd': reverse('division_add') + '?department={dept_id}',
        'deptEdit': _pat('department_edit'),
        'deptDelete': _pat('department_delete'),
        'deptPermissions': _pat('department_permissions'),
        'divEdit': _pat('division_edit'),
        'divDelete': _pat('division_delete'),
    }

    return render(request, 'assessment/admin/org_structure.html', {
        'treemap': treemap,
        'search_query': search_query,
        'org_structure_clear_url': reverse('org_structure'),
        'org_tree': tree_data,
        'org_urls': urls,
    })


@admin_only
def department_list(request):
    return _org_redirect()


@admin_only
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
            return _org_redirect()
    else:
        form = DepartmentForm()
    return render(request, 'assessment/admin/department_form.html', {
        'form': form,
        'title': 'Thêm phòng ban',
    })


@admin_only
def department_edit(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'Đã cập nhật phòng ban "{department.name}".')
            return _org_redirect()
    else:
        form = DepartmentForm(instance=department)
    return render(request, 'assessment/admin/department_form.html', {
        'form': form,
        'title': 'Sửa phòng ban',
        'department': department,
        'is_edit': True,
    })


@admin_only
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        if department.profiles.exists():
            messages.error(
                request,
                f'Không thể xóa "{department.name}" vì còn {department.profiles.count()} nhân viên.',
            )
        else:
            name = department.name
            department.delete()
            messages.success(request, f'Đã xóa phòng ban "{name}".')
        return _org_redirect()
    return render(request, 'assessment/admin/department_confirm_delete.html', {
        'department': department,
    })


@admin_only
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


@admin_only
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

    group_qs = PermissionGroup.objects.annotate(
        profile_count=Count('profiles'),
    ).exclude(slug__startswith=PROTECTED_GROUP_SLUG_PREFIX)
    sorted_groups = sorted(group_qs, key=lambda g: g.name.casefold())

    group_rows = []
    for group in sorted_groups:
        list_summary = group_list_summary(group.get_permissions())
        group_rows.append({
            'group': group,
            'summary': list_summary,
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


@admin_only
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


@admin_only
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


@admin_only
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


@admin_only
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


@admin_only
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


@admin_only
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


@admin_only
def division_delete(request, pk):
    division = get_object_or_404(Division, pk=pk)
    if request.method == 'POST':
        if division.division_profiles.exists():
            messages.error(
                request,
                f'Không thể xóa "{division.name}" vì còn {division.division_profiles.count()} nhân viên.',
            )
        else:
            name = division.name
            dept_id = division.department_id
            division.delete()
            messages.success(request, f'Đã xóa bộ phận "{name}".')
            if dept_id:
                return _org_redirect(f'dept-{dept_id}')
        return _org_redirect()
    return render(request, 'assessment/admin/division_confirm_delete.html', {
        'division': division,
    })

@admin_only
def user_toggle_employed(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.is_superuser:
        return JsonResponse(
            {'status': 'error', 'message': 'Không thể đổi trạng thái tài khoản quản trị.'},
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


@admin_only # Giữ nguyên các khai báo quyền của ní
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