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
from hrm.choices import resolve_department
from PortalJustPlay.utils import generate_hm_username, generate_secure_password
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_columns, paginate_queryset
from .models import Interview
import openpyxl
from django.http import HttpResponse
from django.utils import timezone
@admin_only
@ensure_csrf_cookie
def kanban_board(request):
    candidates = Candidate.objects.select_related('job_posting').filter(job_posting__is_active=True)
    job_id_str = request.GET.get('job_id')
    selected_job_id = None
    
    if job_id_str and job_id_str.isdigit():
        selected_job_id = int(job_id_str)
        candidates = candidates.filter(job_posting_id=selected_job_id)

    kanban_pages, kanban_query_string = paginate_columns(request, [
        ('not_onboarded', candidates.filter(status='not_onboarded').order_by('-applied_at'), 'p_not_onboarded'),
        ('new', candidates.filter(status='new').order_by('-applied_at'), 'p_new'),
        ('reviewing', candidates.filter(status='reviewing').order_by('-applied_at'), 'p_reviewing'),
        ('interviewing', candidates.filter(status='interviewing').order_by('-applied_at'), 'p_interviewing'),
        ('offered', candidates.filter(status__in=['offered', 'hired']).order_by('-id'), 'p_offered'),
        ('rejected', candidates.filter(status='rejected').order_by('-id'), 'p_rejected'),
    ])

    context = {
        'jobs': JobPosting.objects.filter(is_active=True),
        'selected_job': selected_job_id,
        'not_onboarded_candidates': kanban_pages['not_onboarded'],
        'new_candidates': kanban_pages['new'],
        'reviewing_candidates': kanban_pages['reviewing'],
        'interviewing_candidates': kanban_pages['interviewing'],
        'offered_candidates': kanban_pages['offered'],
        'rejected_candidates': kanban_pages['rejected'],
        'kanban_query_string': kanban_query_string,
        'users': User.objects.filter(is_active=True),
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
    full_name = (request.POST.get('full_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    job_posting_id = request.POST.get('job_posting')
    hr_note = (request.POST.get('hr_note') or '').strip()
    cv_file = request.FILES.get('cv_file')

    if not full_name:
        messages.error(request, 'Vui lòng nhập họ và tên ứng viên.')
        return redirect('kanban_board')

    if not email:
        messages.error(request, 'Vui lòng nhập email ứng viên.')
        return redirect('kanban_board')

    if not phone:
        messages.error(request, 'Vui lòng nhập số điện thoại.')
        return redirect('kanban_board')

    if not job_posting_id:
        messages.error(request, 'Vui lòng chọn vị trí ứng tuyển.')
        return redirect('kanban_board')

    job = JobPosting.objects.filter(id=job_posting_id, is_active=True).first()
    if not job:
        messages.error(request, 'Vị trí tuyển dụng không hợp lệ hoặc đã đóng.')
        return redirect('kanban_board')

    if not cv_file:
        messages.error(request, 'Vui lòng tải lên file CV (PDF/Word).')
        return redirect('kanban_board')

    if Candidate.objects.filter(email__iexact=email, job_posting=job).exists():
        messages.error(request, f'Email {email} đã được nộp cho vị trí "{job.title}".')
        return redirect('kanban_board')

    try:
        Candidate.objects.create(
            job_posting=job,
            full_name=full_name,
            email=email,
            phone=phone,
            hr_note=hr_note,
            cv_file=cv_file,
            status='new',
        )
        messages.success(request, f'Đã thêm ứng viên {full_name}.')
    except Exception as e:
        messages.error(request, f'Không thể lưu hồ sơ: {e}')

    return redirect('kanban_board')

@admin_only
def job_posting_list(request):
    search_query = get_search_query(request)
    jobs_qs = JobPosting.objects.all().order_by('-created_at')
    jobs_qs = apply_term_search(
        jobs_qs, search_query,
        'title__icontains', 'department__icontains', 'description__icontains',
        'requirements__icontains', 'position__icontains',
    )
    page_obj, query_string = paginate_queryset(request, jobs_qs)
    return render(request, 'recruitment/admin/job_posting_list.html', {
        'jobs': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })

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
                email=candidate.email or f'{new_username.lower()}@justplay.vn',
                password=new_password,
                first_name=candidate.full_name,
                is_staff=False,
                is_superuser=False,
            )

            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'full_name': candidate.full_name,
                    'department': resolve_department(candidate.job_posting.department),
                    'job_position': position,
                    'job_title': candidate.job_posting.title,
                    'join_date': timezone.now().date(),
                    'role': 'EMPLOYEE',
                    'must_change_password': True,
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