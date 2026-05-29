import io
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy, reverse
from django.contrib.auth import logout
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count
# Import từ các app khác sang
from assessment.decorators import admin_only
from assessment.forms import UserForm # Tạm thời Form vẫn để ở nhà cũ, mốt mình dời sau
from hrm.models import Profile, Department, Division
from hrm.choices import (
    EXCEL_ALL_HEADERS,
    row_to_profile_data,
    profile_defaults_from_import,
    user_to_excel_row,
)
from PortalJustPlay.utils import generate_hm_username, generate_secure_password
from .forms import CustomUserForm, DepartmentForm, DivisionForm
from django.http import JsonResponse
import random
import string


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
        'must_change_password': True,
        'is_employed': form.cleaned_data.get('is_employed', True),
    }


# ==========================================
# 1. QUẢN LÝ DANH SÁCH NHÂN VIÊN
# ==========================================
@admin_only
def user_list(request):
    users = User.objects.select_related(
        'profile', 'profile__department', 'profile__division',
    ).order_by('-date_joined')
    # Tạm thời vẫn dùng template cũ ở assessment để khỏi phải copy file HTML lằng nhằng
    return render(request, 'assessment/admin/user_list.html', {'users': users})


@admin_only
def user_add(request):
    if request.method == 'POST':
        form = CustomUserForm(request.POST)
        if form.is_valid():
            u = form.cleaned_data['username']
            p = form.cleaned_data['password']
            e = form.cleaned_data['email']
            f = form.cleaned_data['full_name']

            if User.objects.filter(username=u).exists():
                messages.error(request, f"Tên đăng nhập '{u}' đã tồn tại!")
            else:
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
                messages.success(request, f"Thành công: Đã thêm {f}. Tài khoản: {u} | Mật khẩu mới là: {p}")
                return redirect('user_list')
    else:
        form = CustomUserForm()
    
    return render(request, 'assessment/admin/user_form.html', {
        'form': form, 
        'title': 'Thêm nhân viên mới'
    })

@admin_only
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    # Lấy profile, tự động tạo nếu chưa có
    profile, created = Profile.objects.get_or_create(user=user_obj)

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
            
            # QUAN TRỌNG: Lưu danh sách nhân viên cấp dưới (ManyToMany)
            # Dùng .set() để ghi đè danh sách mới từ form
            profile.subordinates.set(form.cleaned_data['subordinates'])
            
            # Hàm save() của profile sẽ tự xử lý quyền nếu role là Giám đốc
            profile.save()

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
            'subordinates': profile.subordinates.all(),
        }
        # Truyền user_id để form biết đường loại trừ chính mình khỏi danh sách chọn cấp dưới
        form = CustomUserForm(initial=initial_data, user_id=user_obj.id)
        form.fields['password'].required = False

    return render(request, 'assessment/admin/user_form.html', {
        'form': form, 
        'title': 'Chỉnh sửa nhân sự',
        'is_edit': True,
        'user_instance': user_obj
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
    users = User.objects.select_related(
        'profile', 'profile__department', 'profile__division',
    ).all().order_by('profile__employee_code', 'username')
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


def _org_redirect(tab):
    return redirect(f"{reverse('org_structure')}?tab={tab}")


@admin_only
def org_structure(request):
    tab = request.GET.get('tab', 'department')
    if tab not in {'department', 'division'}:
        tab = 'department'
    departments = Department.objects.annotate(
        staff_count=Count('profiles'),
    ).order_by('sort_order', 'name')
    divisions = Division.objects.annotate(
        staff_count=Count('division_profiles'),
    ).order_by('sort_order', 'name')
    return render(request, 'assessment/admin/org_structure.html', {
        'departments': departments,
        'divisions': divisions,
        'active_tab': tab,
    })


@admin_only
def department_list(request):
    return _org_redirect('department')


@admin_only
def department_add(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã thêm phòng ban "{form.instance.name}".')
            return _org_redirect('department')
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
            form.save()
            messages.success(request, f'Đã cập nhật phòng ban "{department.name}".')
            return _org_redirect('department')
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
        return _org_redirect('department')
    return render(request, 'assessment/admin/department_confirm_delete.html', {
        'department': department,
    })


@admin_only
def division_add(request):
    if request.method == 'POST':
        form = DivisionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã thêm bộ phận "{form.instance.name}".')
            return _org_redirect('division')
    else:
        form = DivisionForm()
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
            form.save()
            messages.success(request, f'Đã cập nhật bộ phận "{division.name}".')
            return _org_redirect('division')
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
            division.delete()
            messages.success(request, f'Đã xóa bộ phận "{name}".')
        return _org_redirect('division')
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

def custom_logout(request):
    logout(request)
    return redirect('login')