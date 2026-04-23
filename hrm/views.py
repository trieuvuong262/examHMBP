import io
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import logout
from django.http import HttpResponse

# Import từ các app khác sang
from assessment.decorators import admin_only
from assessment.forms import UserForm # Tạm thời Form vẫn để ở nhà cũ, mốt mình dời sau
from hrm.models import Profile
from ExamHMBP.utils import generate_hm_username, generate_secure_password # File dùng chung hôm trước

# ==========================================
# 1. QUẢN LÝ DANH SÁCH NHÂN VIÊN
# ==========================================
@admin_only
def user_list(request):
    users = User.objects.all().select_related('profile').order_by('-date_joined')
    # Tạm thời vẫn dùng template cũ ở assessment để khỏi phải copy file HTML lằng nhằng
    return render(request, 'assessment/admin/user_list.html', {'users': users})

@admin_only
def user_add(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            full_name = user.first_name 
            
            new_username = generate_hm_username(full_name)
            user.username = new_username
            user.email = f"{new_username}@hoanmy.com"
            
            new_password = generate_secure_password()
            user.set_password(new_password)
            user.save()
            
            Profile.objects.update_or_create(
                user=user,
                defaults={'full_name': full_name, 'position': 'Khối Hỗ trợ'}
            )
            
            messages.success(request, f"Thêm nhân viên thành công! Tài khoản: {new_username} | Mật khẩu mới là: {new_password}")
            return redirect('user_list')
    else:
        form = UserForm()
    return render(request, 'assessment/admin/user_form.html', {'form': form, 'title': 'Thêm nhân viên mới'})

@admin_only
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Cập nhật thông tin nhân viên thành công!")
            return redirect('user_list')
    else:
        form = UserForm(instance=user)
    return render(request, 'assessment/admin/user_form.html', {'form': form, 'title': 'Sửa thông tin nhân viên'})

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

# ==========================================
# 2. IMPORT / EXCEL EXCEL
# ==========================================
@admin_only
def user_import_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        try:
            df = pd.read_excel(file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            if 'username' not in df.columns:
                messages.error(request, 'Lỗi: File Excel bắt buộc phải có cột "username".')
                return redirect('user_list')
            
            df = df.fillna('')
            success_count = 0
            skipped_count = 0
            
            for _, row in df.iterrows():
                username = str(row['username']).strip()
                if not username: continue
                
                password = str(row.get('password', '')).strip() or 'Hoanmy@123'
                email = str(row.get('email', '')).strip()
                full_name = str(row.get('full_name', '')).strip()
                chuc_danh = str(row.get('chuc_danh', '')).strip()

                if not User.objects.filter(username=username).exists():
                    user = User.objects.create_user(
                        username=username, password=password, email=email,
                        first_name=full_name, is_staff=False
                    )
                    Profile.objects.update_or_create(
                        user=user,
                        defaults={'full_name': full_name, 'position': chuc_danh}
                    )
                    success_count += 1
                else:
                    skipped_count += 1
            
            messages.success(request, f'Thành công: Thêm mới {success_count} nhân viên. Bỏ qua {skipped_count} người đã tồn tại.')
        except Exception as e:
            messages.error(request, f'Lỗi hệ thống khi xử lý file: {str(e)}')
            
    return redirect('user_list')

@admin_only
def user_export_excel(request):
    users = User.objects.all().values('username', 'first_name', 'email', 'date_joined', 'profile__position')
    df = pd.DataFrame(list(users))
    
    df = df.rename(columns={
        'first_name': 'full_name', 'username': 'username',
        'email': 'email', 'date_joined': 'Ngày tham gia', 'profile__position': 'chuc_danh'
    })
    
    if not df.empty:
        df = df[['username', 'full_name', 'chuc_danh', 'email', 'Ngày tham gia']]
        df['Ngày tham gia'] = df['Ngày tham gia'].dt.strftime('%d/%m/%Y')
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Nhan_Vien')
    
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Danh_sach_nhan_vien.xlsx'
    return response

@admin_only
def user_download_template(request):
    columns = ['username', 'password', 'full_name', 'email', 'chuc_danh']
    df = pd.DataFrame(columns=columns)
    df.loc[0] = ['nv001', 'Hoanmy@123', 'Nguyễn Văn An', 'an.nv@hoanmy.com', 'Bác Sĩ']
    df.loc[1] = ['nv002', '', 'Trần Thị Bình', '', 'Điều Dưỡng'] 
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template_Import')
    
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_Nhan_Vien.xlsx'
    return response

# ==========================================
# 3. MẬT KHẨU & ĐĂNG XUẤT
# ==========================================
@admin_only
def user_password_reset(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        new_password = generate_secure_password()
        
        user.set_password(new_password)
        user.save()
        
        try:
            display_name = user.profile.full_name if hasattr(user, 'profile') and user.profile.full_name else user.username
        except:
            display_name = user.username
        
        messages.success(request, f"Đã đặt lại mật khẩu cho {display_name}. Mật khẩu mới là: {new_password}")
    return redirect('user_list')

class MyPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        user = self.request.user
        if hasattr(user, 'is_first_login'):
            user.is_first_login = False
            user.save()
        messages.success(self.request, "Mật khẩu đã được thay đổi thành công!")
        return super().form_valid(form)

def custom_logout(request):
    logout(request)
    return redirect('login')