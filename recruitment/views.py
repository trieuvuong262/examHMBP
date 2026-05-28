import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction, IntegrityError
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
from assessment.models import Exam
from hrm.models import Profile
from hrm.choices import normalize_position
from .models import Interview
import openpyxl
from django.http import HttpResponse
@admin_only
@ensure_csrf_cookie
def kanban_board(request):
    candidates = Candidate.objects.select_related('job_posting').filter(job_posting__is_active=True)
    not_onboarded_candidates = candidates.filter(status='not_onboarded')
    job_id_str = request.GET.get('job_id')
    selected_job_id = None
    
    if job_id_str and job_id_str.isdigit():
        selected_job_id = int(job_id_str)
        candidates = candidates.filter(job_posting_id=selected_job_id)

    context = {
        'jobs': JobPosting.objects.filter(is_active=True),
        'selected_job': selected_job_id,
        'not_onboarded_candidates': not_onboarded_candidates,
        'new_candidates': candidates.filter(status='new'),
        'reviewing_candidates': candidates.filter(status='reviewing'),
        'interviewing_candidates': candidates.filter(status='interviewing'),
        'users': User.objects.filter(is_active=True), # Thêm dòng này để form set lịch có danh sách User
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

    if candidate.status == 'hired':
        if candidate.email and User.objects.filter(email=candidate.email).exists():
            return JsonResponse(
                {'status': 'error', 'message': 'Ứng viên này đã có tài khoản đang hoạt động!'},
                status=400,
            )

    if candidate.status not in {'offered', 'hired'}:
        return JsonResponse(
            {'status': 'error', 'message': 'Chỉ tạo user khi ứng viên ở trạng thái Trúng tuyển.'},
            status=400,
        )

    position = normalize_position(candidate.job_posting.position)

    try:
        with transaction.atomic():
            new_username = generate_hm_username(candidate.full_name)
            new_password = generate_secure_password()

            user = User.objects.create_user(
                username=new_username,
                email=candidate.email or new_username,
                password=new_password,
                first_name=candidate.full_name,
                is_staff=False,
                is_superuser=False,
            )

            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'full_name': candidate.full_name,
                    'position': position,
                    'role': 'EMPLOYEE',
                },
            )

            candidate.status = 'hired'
            candidate.save(update_fields=['status'])

            onboarding_exam = Exam.objects.filter(is_active=True).first()
            if onboarding_exam:
                onboarding_exam.assigned_users.add(user)

        return JsonResponse({
            'status': 'success',
            'message': f'Đã tạo tài khoản cho nhân viên {candidate.full_name}',
            'username': new_username,
            'password': new_password,
        })

    except IntegrityError:
        return JsonResponse(
            {'status': 'error', 'message': 'Tài khoản đã tồn tại (trùng username hoặc email).'},
            status=400,
        )
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
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
    """Tạo username dạng ten.ho1@justplay.vn"""
    clean_name = remove_vietnamese_accents(full_name)
    parts = clean_name.split()

    if not parts:
        base = "user.jp"
    elif len(parts) == 1:
        base = parts[0]
    else:
        ho = parts[0]
        ten = parts[-1]
        base = f"{ten}.{ho}"

    counter = 1
    username = f"{base}{counter}@justplay.vn"
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}{counter}@justplay.vn"

    return username

def generate_secure_password(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
# Sửa lại 2 hàm này ở cuối file views.py của ní:

@admin_only
@require_POST
def set_interview_schedule(request):
    candidate_id = request.POST.get('candidate_id')
    interview_time = request.POST.get('interview_time')
    candidate = get_object_or_404(Candidate, id=candidate_id)

    # Bỏ phần interviewer_ids, chỉ lưu thời gian và địa điểm
    interview, created = Interview.objects.update_or_create(
        candidate=candidate,
        defaults={
            'interview_time': interview_time,
        }
    )

    messages.success(request, f'Đã lưu lịch phỏng vấn cho ứng viên {candidate.full_name}!')
    return redirect('kanban_board')

@admin_only
def get_all_interviews(request):
    # 1. Bắt lấy ID của vị trí đang được lọc trên trình duyệt
    job_id = request.GET.get('job_id')
    
    interviews = Interview.objects.select_related('candidate__job_posting')
    
    # 2. Nếu có lọc theo vị trí thì bóp data lại
    if job_id and job_id.isdigit():
        interviews = interviews.filter(candidate__job_posting_id=job_id)
        
    interviews = interviews.order_by('-interview_time')
    
    data = []
    for inv in interviews:
        time_str = inv.interview_time.strftime('%H:%M - %d/%m/%Y') if inv.interview_time else ''
        data.append({
            'candidate_name': inv.candidate.full_name,
            'job_title': inv.candidate.job_posting.title,
            'time': time_str,
            'status': inv.candidate.get_status_display()
        })
    return JsonResponse({'interviews': data})
@admin_only
def get_candidate_interview(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    
    # Kiểm tra xem ứng viên này đã có lịch phỏng vấn trong Database chưa
    if hasattr(candidate, 'interview'):
        # ⚠️ BẮT BUỘC: Ép định dạng ngày giờ chuẩn ISO (YYYY-MM-DDTHH:MM) để thẻ HTML5 hiểu
        time_str = candidate.interview.interview_time.strftime('%Y-%m-%dT%H:%M') if candidate.interview.interview_time else ''
        data = {
            'interview_time': time_str,
        }
    else:
        # Nếu chưa có lịch thì trả về rỗng
        data = {
            'interview_time': '',
        }
        
    return JsonResponse(data)

@admin_only
@require_POST
def update_practice_license(request):
    candidate_id = request.POST.get('candidate_id')
    candidate = get_object_or_404(Candidate, id=candidate_id)
    
    candidate.license_number = request.POST.get('license_number', '')
    candidate.scope_of_practice = request.POST.get('scope_of_practice', '')
    candidate.practice_time = request.POST.get('practice_time', '')
    candidate.professional_position = request.POST.get('professional_position', '')
    candidate.other_practice_time = request.POST.get('other_practice_time', '')
    candidate.license_note = request.POST.get('license_note', '')
    candidate.save()
    
    messages.success(request, f'Đã cập nhật thông tin Hành nghề cho {candidate.full_name}')
    return redirect('kanban_board')

@admin_only
def get_candidate_license(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    data = {
        'license_number': candidate.license_number or '',
        'scope_of_practice': candidate.scope_of_practice or '',
        'practice_time': candidate.practice_time or '',
        'professional_position': candidate.professional_position or '',
        'other_practice_time': candidate.other_practice_time or '',
        'license_note': candidate.license_note or '',
    }
    return JsonResponse(data)

@admin_only
def get_all_licenses(request):
    # 1. Bắt lấy ID của vị trí đang được lọc trên trình duyệt
    job_id = request.GET.get('job_id')
    
    candidates = Candidate.objects.filter(status='hired').select_related('job_posting')
    
    # 2. Nếu có lọc theo vị trí thì bóp data lại
    if job_id and job_id.isdigit():
        candidates = candidates.filter(job_posting_id=job_id)
        
    candidates = candidates.order_by('-applied_at')
    
    data = []
    for cand in candidates:
        data.append({
            'full_name': cand.full_name,
            'professional_position': cand.professional_position or cand.job_posting.title,
            'license_number': cand.license_number or '<span class="badge bg-light text-muted border">Chưa nhập</span>',
            'scope_of_practice': cand.scope_of_practice or '',
            'practice_time': cand.practice_time or '',
            'other_practice_time': cand.other_practice_time or '',
        })
    return JsonResponse({'licenses': data})

@admin_only
def export_interviews_excel(request):
    job_id = request.GET.get('job_id')
    interviews = Interview.objects.select_related('candidate__job_posting')
    
    if job_id and job_id.isdigit():
        interviews = interviews.filter(candidate__job_posting_id=job_id)
        
    interviews = interviews.order_by('-interview_time')

    # Khởi tạo file Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lịch Phỏng Vấn"

    # Tạo hàng Header (Tiêu đề cột)
    headers = ["Thời gian phỏng vấn", "Họ và tên Ứng viên", "Trạng thái", "Vị trí ứng tuyển"]
    ws.append(headers)

    # Đổ dữ liệu vào các hàng tiếp theo
    for inv in interviews:
        time_str = inv.interview_time.strftime('%H:%M - %d/%m/%Y') if inv.interview_time else ''
        ws.append([
            time_str,
            inv.candidate.full_name,
            inv.candidate.get_status_display(),
            inv.candidate.job_posting.title
        ])

    # Thiết lập Response để trình duyệt tự hiểu đây là file tải về
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Danh_sach_lich_phong_van.xlsx"'
    wb.save(response)
    return response


@admin_only
def export_licenses_excel(request):
    job_id = request.GET.get('job_id')
    candidates = Candidate.objects.filter(status='hired').select_related('job_posting')
    
    if job_id and job_id.isdigit():
        candidates = candidates.filter(job_posting_id=job_id)
        
    candidates = candidates.order_by('-applied_at')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Đăng Ký Hành Nghề"

    headers = [
        "Họ và tên", "Số GPHN/CCHN", "Phạm vi hành nghề", 
        "Thời gian ĐKHN tại cơ sở này", "Vị trí chuyên môn", 
        "Thời gian ĐKHN tại cơ sở khác", "Ghi chú"
    ]
    ws.append(headers)

    for cand in candidates:
        ws.append([
            cand.full_name,
            cand.license_number or '',
            cand.scope_of_practice or '',
            cand.practice_time or '',
            cand.professional_position or cand.job_posting.title,
            cand.other_practice_time or '',
            cand.license_note or ''
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Danh_sach_dang_ky_hanh_nghe.xlsx"'
    wb.save(response)
    return response