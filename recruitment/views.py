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
from assessment.decorators import admin_only
import unicodedata
import secrets
import string
import re


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
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
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

        Candidate.objects.create(
            job_posting_id=job_posting_id,
            full_name=full_name,
            email=email,
            phone=phone,
            hr_note=hr_note,
            cv_file=cv_file,
            status='new'
        )
        
    except Exception as e:
        pass
        
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
    
    # --- ĐOẠN CODE NÂNG CẤP KIỂM TRA TÀI KHOẢN ---
    if candidate.status == 'hired':
        # Quét xem thực tế có tài khoản nào xài Email này đang tồn tại không
        user_exists = False
        if candidate.email:
            user_exists = User.objects.filter(email=candidate.email).exists()
        
        # Nếu thực sự có tài khoản rồi thì mới chặn
        if user_exists:
            return JsonResponse({'status': 'error', 'message': 'Ứng viên này đã có tài khoản đang hoạt động!'})
        # Nếu không có (do HR đã xóa bên Quản lý nhân sự) thì cứ cho code đi tiếp để tạo lại!
    # ----------------------------------------------
        
    try:
        # 1. Sinh Username và Password theo quy tắc mới
        new_username = generate_hm_username(candidate.full_name)
        new_password = generate_secure_password()
        
        # 2. Tạo User trong Database
        user = User.objects.create(
            username=new_username,
            email=candidate.email or new_username, # Lấy email ứng viên, nếu không có thì lấy username làm email
            first_name=candidate.full_name,
            is_staff=False, 
            is_superuser=False
        )
        # Set mật khẩu ngẫu nhiên
        user.set_password(new_password)
        user.save()
        
        # 3. Tạo Profile
        from assessment.models import Profile
        profile, created = Profile.objects.update_or_create(
            user=user,
            defaults={
                'full_name': candidate.full_name,
                'position': candidate.job_posting.position
            }
        )
        
        # 4. Đổi trạng thái Ứng viên
        candidate.status = 'hired'
        candidate.save()
        
        # 5. Giao bài thi hội nhập
        onboarding_exam = Exam.objects.filter(is_active=True).first()
        if onboarding_exam:
            onboarding_exam.assigned_users.add(user)

        # 6. QUAN TRỌNG: Trả về cả username và password cho Frontend hiển thị
        return JsonResponse({
            'status': 'success', 
            'message': f'Đã tạo tài khoản cho nhân viên {candidate.full_name}',
            'username': new_username,
            'password': new_password  # <-- Frontend sẽ lấy cục này để show Popup
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    
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
        messages.error(request, f'Lỗi khi lưu ghi chú: {str(e)}')
        
    return redirect('kanban_board')



def remove_vietnamese_accents(text):
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()

def generate_hm_username(full_name):
    """ Tạo username dạng ten.ho1@hoanmy.com """
    clean_name = remove_vietnamese_accents(full_name)
    parts = clean_name.split()
    
    if not parts:
        base = "user.hm"
    elif len(parts) == 1:
        base = parts[0]
    else:
        ho = parts[0]
        ten = parts[-1]
        base = f"{ten}.{ho}"
    
    counter = 1
    username = f"{base}{counter}@hoanmy.com"
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}{counter}@hoanmy.com"
        
    return username

def generate_secure_password(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))