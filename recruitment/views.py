import json
import unicodedata
import secrets # Dùng để tạo pass ngẫu nhiên (Lỗi 9)
import logging # Dùng để ghi log lỗi (Lỗi 12)
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from .models import JobPosting, Candidate
from .forms import JobPostingForm
from assessment.models import Exam
from assessment.decorators import admin_only

logger = logging.getLogger(__name__) # Khởi tạo bộ ghi log

@admin_only
def kanban_board(request):
    candidates = Candidate.objects.select_related('job_posting').filter(job_posting__is_active=True)
    
    job_id_str = request.GET.get('job_id')
    selected_job_id = None
    
    if job_id_str and job_id_str.isdigit():
        selected_job_id = int(job_id_str)
        candidates = candidates.filter(job_posting_id=selected_job_id)

    context = {
        'jobs': JobPosting.objects.filter(is_active=True),
        'selected_job': selected_job_id,
        
        'new_candidates': candidates.filter(status='new'),
        'reviewing_candidates': candidates.filter(status='reviewing'),
        'interviewing_candidates': candidates.filter(status='interviewing'),
        
        'offered_candidates': candidates.filter(status__in=['offered', 'hired']).order_by('-id')[:15], 
        'rejected_candidates': candidates.filter(status='rejected').order_by('-id')[:15],
    }
    return render(request, 'recruitment/admin/kanban_board.html', context)

@admin_only
@require_POST
def update_candidate_status(request):
    try:
        data = json.loads(request.body)
        candidate_id = data.get('candidate_id')
        new_status = data.get('status')
        
        candidate = Candidate.objects.get(id=candidate_id)
        candidate.status = new_status
        candidate.save()
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        # VÁ LỖI 12: Không trả str(e) ra frontend
        logger.error(f"Lỗi update status: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Không thể cập nhật trạng thái lúc này.'}, status=400)

@admin_only
@require_POST
def update_hr_note(request):
    candidate_id = request.POST.get('candidate_id')
    new_note = request.POST.get('hr_note', '')
    
    try:
        candidate = get_object_or_404(Candidate, id=candidate_id)
        candidate.hr_note = new_note
        candidate.save()
        messages.success(request, f'Đã cập nhật ghi chú cho ứng viên {candidate.full_name}!')
    except Exception as e:
        # VÁ LỖI 12
        logger.error(f"Lỗi update HR note: {str(e)}")
        messages.error(request, 'Đã xảy ra lỗi khi lưu ghi chú.')
        
    return redirect('kanban_board')
    
@admin_only
@require_POST
def add_candidate(request):
    try:
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        job_posting_id = request.POST.get('job_posting')
        hr_note = request.POST.get('hr_note', '')
        cv_file = request.FILES.get('cv_file')

        # VÁ LỖI 5 & 10: Kiểm tra File Upload
        if cv_file:
            # 1. Kiểm tra dung lượng (Max 5MB)
            if cv_file.size > 5 * 1024 * 1024:
                messages.error(request, "Dung lượng CV không được vượt quá 5MB.")
                return redirect('kanban_board')
            
            # 2. Kiểm tra đuôi file an toàn
            ext = os.path.splitext(cv_file.name)[1].lower()
            valid_extensions = ['.pdf', '.doc', '.docx']
            if ext not in valid_extensions:
                messages.error(request, "Chỉ chấp nhận file CV định dạng PDF hoặc Word.")
                return redirect('kanban_board')

        Candidate.objects.create(
            job_posting_id=job_posting_id,
            full_name=full_name,
            email=email,
            phone=phone,
            hr_note=hr_note,
            cv_file=cv_file,
            status='new'
        )
        messages.success(request, "Đã thêm ứng viên thành công!")
        
    except Exception as e:
        # VÁ LỖI 12: Ghi log thay vì dùng "pass" im lặng
        logger.error(f"Lỗi thêm ứng viên: {str(e)}")
        messages.error(request, "Đã xảy ra lỗi khi lưu hồ sơ ứng viên.")
        
    return redirect('kanban_board')

@admin_only
def job_posting_list(request):
    jobs = JobPosting.objects.all().order_by('-created_at')
    return render(request, 'recruitment/admin/job_posting_list.html', {'jobs': jobs})

@admin_only
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

@admin_only
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

@admin_only
@require_POST
def job_posting_delete(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    job.delete()
    messages.success(request, 'Đã xóa vị trí tuyển dụng!')
    return redirect('job_posting_list')


def generate_employee_username(full_name):
    nfkd_form = unicodedata.normalize('NFKD', full_name)
    clean_name = u"".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper()
    words = clean_name.split()
    
    if len(words) >= 3:
        initials = words[0][0] + words[-2][0] + words[-1][0]
    elif len(words) == 2:
        initials = words[0][0] + words[-1][0]
    elif len(words) == 1:
        initials = words[0][0:3]
    else:
        initials = "NV"
        
    prefix = initials.lower() # VD: ltv
    
    existing_users = User.objects.filter(username__startswith=prefix, username__endswith='-bp')
    max_seq = 0
    for u in existing_users:
        try:
            num_part = u.username[len(prefix):-3] 
            num = int(num_part)
            if num > max_seq:
                max_seq = num
        except ValueError:
            continue
            
    next_seq = max_seq + 1
    return f"{prefix}{next_seq:03d}-bp"


@admin_only
@require_POST
def convert_to_employee(request, candidate_id):
    candidate = get_object_or_404(Candidate, id=candidate_id)
    
    if candidate.status == 'hired':
        return JsonResponse({'status': 'error', 'message': 'Ứng viên này đã có tài khoản!'})
        
    try:
        username = generate_employee_username(candidate.full_name)
        
        # VÁ LỖI 9: Mật khẩu ngẫu nhiên an toàn
        random_password = secrets.token_urlsafe(8)
        
        user = User.objects.create(
            username=username,
            email=candidate.email,
            first_name=candidate.full_name,
            password=make_password(random_password), # Dùng pass ngẫu nhiên
            is_staff=False, 
            is_superuser=False
        )
        
        from assessment.models import Profile
        profile, created = Profile.objects.update_or_create(
            user=user,
            defaults={
                'full_name': candidate.full_name,
                'position': candidate.job_posting.position
            }
        )
        
        candidate.status = 'hired'
        candidate.save()
        
        # VÁ LỖI 15: Chỉnh lại Query để lấy ĐÚNG bài thi Hội nhập (Onboarding)
        # Giả sử ní đặt tên bài thi có chữ "Hội nhập" hoặc "Onboard"
        onboarding_exam = Exam.objects.filter(is_active=True, title__icontains='hội nhập').first()
        if onboarding_exam:
            onboarding_exam.assigned_users.add(user)

        # Trả về pass ngẫu nhiên để HR gửi cho nhân viên mới
        return JsonResponse({
            'status': 'success', 
            'message': f'Đã tạo tài khoản {username}. Mật khẩu tạm: {random_password}',
            'username': username
        })
        
    except Exception as e:
        logger.error(f"Lỗi convert_to_employee: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Đã xảy ra lỗi hệ thống khi chuyển đổi.'})
    
    
@admin_only
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
