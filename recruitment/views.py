import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from .models import JobPosting, Candidate
from django.shortcuts import render, redirect
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import JobPostingForm
import unicodedata
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from assessment.models import Exam

@staff_member_required
def kanban_board(request):
    # NÂNG CẤP 1: Mặc định CHỈ HIỂN THỊ ứng viên của các Job ĐANG MỞ (is_active=True)
    # Nếu HR đóng Job, ứng viên sẽ tự động rút khỏi bảng Kanban cho gọn
    candidates = Candidate.objects.select_related('job_posting').filter(job_posting__is_active=True)
    
    job_id_str = request.GET.get('job_id')
    selected_job_id = None
    
    if job_id_str and job_id_str.isdigit():
        selected_job_id = int(job_id_str)
        candidates = candidates.filter(job_posting_id=selected_job_id)

    context = {
        'jobs': JobPosting.objects.filter(is_active=True),
        'selected_job': selected_job_id,
        
        # Các cột đang diễn ra thì lấy hết
        'new_candidates': candidates.filter(status='new'),
        'reviewing_candidates': candidates.filter(status='reviewing'),
        'interviewing_candidates': candidates.filter(status='interviewing'),
        
        # NÂNG CẤP 2: Các cột đã chốt kết quả thì chỉ hiển thị tối đa 15 người mới nhất
        'offered_candidates': candidates.filter(status__in=['offered', 'hired']).order_by('-id')[:15], 
        'rejected_candidates': candidates.filter(status='rejected').order_by('-id')[:15],
    }
    return render(request, 'recruitment/admin/kanban_board.html', context)

@staff_member_required
@require_POST
def update_candidate_status(request):
    try:
        data = json.loads(request.body)
        candidate_id = data.get('candidate_id')
        new_status = data.get('status')
        
        # Cập nhật trạng thái mới vào Database
        candidate = Candidate.objects.get(id=candidate_id)
        candidate.status = new_status
        candidate.save()
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
@staff_member_required
@require_POST
def add_candidate(request):
    try:
        # Lấy dữ liệu từ Form gửi lên
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        job_posting_id = request.POST.get('job_posting')
        hr_note = request.POST.get('hr_note', '')
        cv_file = request.FILES.get('cv_file') # Lấy file upload

        # Tạo Ứng viên mới
        Candidate.objects.create(
            job_posting_id=job_posting_id,
            full_name=full_name,
            email=email,
            phone=phone,
            hr_note=hr_note,
            cv_file=cv_file,
            status='new' # Mặc định rơi vào cột Mới nộp
        )
        
        # messages.success(request, f'Đã thêm ứng viên {full_name} thành công!')
    except Exception as e:
        pass
        # messages.error(request, f'Lỗi khi thêm ứng viên: {str(e)}')
        
    # Xong việc thì quay lại trang Kanban
    return redirect('kanban_board')

# ==========================================
# QUẢN LÝ VỊ TRÍ TUYỂN DỤNG (JOB POSTINGS)
# ==========================================
@staff_member_required
def job_posting_list(request):
    jobs = JobPosting.objects.all().order_by('-created_at')
    return render(request, 'recruitment/admin/job_posting_list.html', {'jobs': jobs})

@staff_member_required
def job_posting_create(request):
    if request.method == 'POST':
        form = JobPostingForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã tạo vị trí tuyển dụng thành công!')
            return redirect('job_posting_list')
    else:
        form = JobPostingForm()
    return render(request, 'recruitment/admin/job_posting_form.html', {'form': form, 'title': 'Đăng tin Tuyển dụng mới'})

@staff_member_required
def job_posting_edit(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    if request.method == 'POST':
        form = JobPostingForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật vị trí tuyển dụng!')
            return redirect('job_posting_list')
    else:
        form = JobPostingForm(instance=job)
    return render(request, 'recruitment/admin/job_posting_form.html', {'form': form, 'title': 'Chỉnh sửa Vị trí Tuyển dụng', 'job': job})

@staff_member_required
@require_POST
def job_posting_delete(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    job.delete()
    messages.success(request, 'Đã xóa vị trí tuyển dụng!')
    return redirect('job_posting_list')


def generate_employee_username(full_name):
    # 1. Bỏ dấu tiếng Việt (VD: Lê -> Le)
    nfkd_form = unicodedata.normalize('NFKD', full_name)
    clean_name = u"".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper()
    words = clean_name.split()
    
    # 2. Lấy chữ cái tắt theo quy tắc của bạn
    if len(words) >= 3:
        initials = words[0][0] + words[-2][0] + words[-1][0] # Lấy chữ đầu, và 2 chữ cuối
    elif len(words) == 2:
        initials = words[0][0] + words[-1][0] # Lấy 2 chữ
    elif len(words) == 1:
        initials = words[0][0:3]
    else:
        initials = "NV"
        
    prefix = initials.lower() # VD: ltv
    
    # 3. Quét Database để tìm số thứ tự lớn nhất đang có
    existing_users = User.objects.filter(username__startswith=prefix, username__endswith='-bp')
    max_seq = 0
    for u in existing_users:
        try:
            # Cắt bỏ prefix ở đầu và '-bp' ở cuối để lấy số (VD: ltv002-bp -> 002)
            num_part = u.username[len(prefix):-3] 
            num = int(num_part)
            if num > max_seq:
                max_seq = num
        except ValueError:
            continue
            
    # Tịnh tiến lên 1 và format 3 chữ số (001, 002,...)
    next_seq = max_seq + 1
    return f"{prefix}{next_seq:03d}-bp"

# Hàm View chính xử lý khi bấm nút "Nhận việc"
@staff_member_required
@require_POST
def convert_to_employee(request, candidate_id):
    candidate = get_object_or_404(Candidate, id=candidate_id)
    
    if candidate.status == 'hired':
        return JsonResponse({'status': 'error', 'message': 'Ứng viên này đã có tài khoản!'})
        
    try:
        # 1. Tạo Username (ltv002-bp...) - Giữ nguyên logic cũ
        username = generate_employee_username(candidate.full_name)
        
        # 2. Tạo User mặc định
        user = User.objects.create(
            username=username,
            email=candidate.email,
            first_name=candidate.full_name, # Lưu vào User model
            password=make_password('Hoanmy@123')
        )
        
        # 3. CẬP NHẬT PROFILE (Đây là phần quan trọng để hiện tên trên Dashboard)
        # Import Profile từ app assessment của bạn
        from assessment.models import Profile
        
        # Sử dụng update_or_create để đảm bảo Profile luôn có dữ liệu đúng
        profile, created = Profile.objects.update_or_create(
            user=user,
            defaults={
                'full_name': candidate.full_name,      # ĐIỀN TÊN NHÂN VIÊN VÀO ĐÂY
                'position': candidate.job_posting.position # Điền chức danh từ tin tuyển dụng
            }
        )
        
        # 4. Chuyển trạng thái ứng viên
        candidate.status = 'hired'
        candidate.save()
        
        # 5. Tự động gán bài thi (Assessment)
        onboarding_exam = Exam.objects.filter(is_active=True).first()
        if onboarding_exam:
            onboarding_exam.assigned_users.add(user)

        return JsonResponse({
            'status': 'success', 
            'message': f'Đã tạo tài khoản {username} cho nhân viên {candidate.full_name}',
            'username': username
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    

@staff_member_required
def candidate_detail_ajax(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    data = {
        'full_name': candidate.full_name,
        'email': candidate.email,
        'phone': candidate.phone,
        'job_title': candidate.job_posting.title,
        'status': candidate.get_status_display(),
        'applied_at': candidate.applied_at.strftime('%d/%m/%Y'),
        'hr_note': candidate.hr_note or "Chưa có ghi chú.",
        'cv_url': candidate.cv_file.url if candidate.cv_file else None,
    }
    return JsonResponse(data)

import pandas as pd
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import redirect

@staff_member_required
def user_import_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        
        try:
            # Đọc file excel
            df = pd.read_excel(file)
            
            # Giả sử file Excel có các cột: username, password, first_name, last_name, email
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                username = str(row.get('username')).strip()
                password = str(row.get('password')).strip()
                email = str(row.get('email', ''))
                first_name = str(row.get('first_name', ''))
                last_name = str(row.get('last_name', ''))

                if not User.objects.filter(username=username).exists():
                    User.objects.create_user(
                        username=username,
                        password=password,
                        email=email,
                        first_name=first_name,
                        last_name=last_name
                    )
                    success_count += 1
                else:
                    error_count += 1
            
            messages.success(request, f'Đã import thành công {success_count} nhân viên. (Bỏ qua {error_count} nhân viên đã tồn tại)')
            
        except Exception as e:
            messages.error(request, f'Lỗi khi xử lý file: {str(e)}')
            
    return redirect('user_list')


import pandas as pd
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import redirect

@staff_member_required
def user_import_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        
        try:
            # Đọc file excel
            df = pd.read_excel(file)
            
            # Giả sử file Excel có các cột: username, password, first_name, last_name, email
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                username = str(row.get('username')).strip()
                password = str(row.get('password')).strip()
                email = str(row.get('email', ''))
                first_name = str(row.get('first_name', ''))
                last_name = str(row.get('last_name', ''))

                if not User.objects.filter(username=username).exists():
                    User.objects.create_user(
                        username=username,
                        password=password,
                        email=email,
                        first_name=first_name,
                        last_name=last_name
                    )
                    success_count += 1
                else:
                    error_count += 1
            
            messages.success(request, f'Đã import thành công {success_count} nhân viên. (Bỏ qua {error_count} nhân viên đã tồn tại)')
            
        except Exception as e:
            messages.error(request, f'Lỗi khi xử lý file: {str(e)}')
            
    return redirect('user_list')