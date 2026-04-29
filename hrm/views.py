import io
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import logout
from django.http import HttpResponse
from django.db import transaction # BẮT BUỘC PHẢI CÓ IMPORT NÀY Ở ĐẦU FILE HOẶC TRONG HÀM
# Import từ các app khác sang
from assessment.decorators import admin_only
from assessment.forms import UserForm # Tạm thời Form vẫn để ở nhà cũ, mốt mình dời sau
from hrm.models import Profile
from ExamHMBP.utils import generate_hm_username, generate_secure_password # File dùng chung hôm trước
from .forms import CustomUserForm
from django.http import JsonResponse
import random
import string
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
        form = CustomUserForm(request.POST)
        if form.is_valid():
            u = form.cleaned_data['username']
            p = form.cleaned_data['password']
            e = form.cleaned_data['email']
            f = form.cleaned_data['full_name']
            pos = form.cleaned_data['position']

            if User.objects.filter(username=u).exists():
                messages.error(request, f"Tên đăng nhập '{u}' đã tồn tại!")
            else:
                # Tạo User mới
                user = User.objects.create_user(
                    username=u, 
                    email=e, 
                    password=p, 
                    first_name=f
                )
                # Tạo hoặc cập nhật Profile đi kèm
                Profile.objects.update_or_create(
                    user=user, 
                    defaults={'full_name': f, 'position': pos}
                )
                # Thông báo thành công (Dùng format này để script copy ở trang list bắt được)
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
            profile.position = form.cleaned_data['position']
            profile.role = form.cleaned_data['role']
            
            # QUAN TRỌNG: Lưu danh sách nhân viên cấp dưới (ManyToMany)
            # Dùng .set() để ghi đè danh sách mới từ form
            profile.subordinates.set(form.cleaned_data['subordinates'])
            
            # Hàm save() của profile sẽ tự xử lý việc cấp quyền Admin nếu role là GM
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
            'full_name': profile.full_name,
            'position': profile.position,
            'role': profile.role,
            'subordinates': profile.subordinates.all(), # Lấy danh sách lính hiện tại
        }
        # Truyền user_id để form biết đường loại trừ chính mình khỏi danh sách chọn cấp dưới
        form = CustomUserForm(initial=initial_data, user_id=user_obj.id)
        form.fields['password'].required = False

    return render(request, 'assessment/admin/user_form.html', {
        'form': form, 
        'title': 'Chỉnh sửa nhân sự',
        'is_edit': True,
        'user_instance': user_obj # Truyền thêm để template nếu cần dùng ID
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
            # Chuẩn hóa tên cột thành chữ thường, xóa khoảng trắng thừa
            df.columns = [str(c).strip().lower() for c in df.columns]
            df = df.fillna('')
            
            success_count = 0
            skipped_count = 0
            
            from hrm.models import Profile
            
            # KÍCH HOẠT SỨC MẠNH GỘP ĐƠN - GIẢI QUYẾT LỖI 504 TIMEOUT
            with transaction.atomic():
                for _, row in df.iterrows():
                    # 1. LẤY HỌ VÀ TÊN (Bắt buộc phải có, không có thì bỏ qua dòng)
                    full_name = str(row.get('full_name', '')).strip()
                    if not full_name:
                        continue 

                    # 2. XỬ LÝ USERNAME
                    raw_username = str(row.get('username', '')).strip()
                    if raw_username:
                        # Nếu trong Excel có nhập, lấy đúng trong Excel
                        username = raw_username
                    else:
                        # Nếu Excel để trống, tự động sinh ten.ho@hoanmy.com
                        username = generate_hm_username(full_name)

                    # 3. XỬ LÝ MẬT KHẨU (Đã giữ nguyên logic của ní)
                    raw_password = str(row.get('password', '')).strip()
                    # Nếu Excel để trống pass, tự tạo pass bảo mật
                    password = raw_password if raw_password else generate_secure_password()
                    
                    # 4. Email và Chức danh
                    email = str(row.get('email', '')).strip() or username
                    chuc_danh = str(row.get('chuc_danh', '')).strip() or 'Khối Hỗ trợ'

                    # 5. LƯU VÀO DATABASE
                    if not User.objects.filter(username=username).exists():
                        user = User.objects.create_user(
                            username=username,
                            password=password,
                            email=email,
                            first_name=full_name,
                            is_staff=False
                        )
                        Profile.objects.update_or_create(
                            user=user,
                            defaults={'full_name': full_name, 'position': chuc_danh}
                        )
                        success_count += 1
                    else:
                        skipped_count += 1
            
            messages.success(request, f'Thành công: Thêm mới {success_count} nhân viên. Bỏ qua {skipped_count} người do trùng lặp.')
            
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

@admin_only # Giữ nguyên các khai báo quyền của ní
def user_password_reset(request, user_id):
    if request.method == 'POST':
        user = User.objects.get(id=user_id)
        
        # Tạo mật khẩu ngẫu nhiên mới (Nếu code cũ của ní khác thì thay vào đây)
        characters = string.ascii_letters + string.digits
        new_password = ''.join(random.choice(characters) for i in range(8))
        
        user.set_password(new_password)
        user.save()
        
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