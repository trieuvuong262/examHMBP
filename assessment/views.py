from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from .models import Exam, ExamSubmission, Question, UserAnswer, Choice
from .forms import ExamForm, QuestionForm, ChoiceFormSet, UserForm
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
# 1. Thư viện hệ thống và điều hướng
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseForbidden, JsonResponse
from training.models import Course, Enrollment
# 2. Thư viện xử lý User và Auth
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password # Dùng nếu muốn tạo pass mặc định khi thêm user
from recruitment.models import JobPosting, Candidate, Interview
import pandas as pd
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponse
import io
from assessment.decorators import admin_only

# 3. Import các Model của bạn
from .models import (
    Exam, 
    Question, 
    Choice, 
    ExamSubmission, 
    UserAnswer, 
    Profile,
    Competency
)

# 4. Import các Form của bạn
from .forms import (
    ExamForm, 
    QuestionForm, 
    ChoiceFormSet,
    UserForm # Form quản lý nhân viên vừa tạo
)
# ================= USER VIEWS (NHÂN VIÊN) =================
@login_required
def home_portal(request):
    return render(request, 'portal.html')

@login_required
def exam_list(request):
    now = timezone.now()
    
    # 1. Lọc các kỳ thi: Được giao cho User + Đang mở + Đang trong khung giờ
    active_exams = Exam.objects.filter(
        assigned_users=request.user, 
        is_active=True,
        start_time__lte=now,
        end_time__gte=now
    ).distinct()

    # 2. [ĐÃ SỬA QUAN TRỌNG]: Lấy ID các bài thi ĐÃ NỘP BÀI
    # Dùng submitted_at__isnull=False để đảm bảo hễ bấm nộp là khóa, mặc kệ Admin chấm chưa
    completed_exam_ids = ExamSubmission.objects.filter(
        user=request.user, 
        submitted_at__isnull=False 
    ).values_list('exam_id', flat=True)

    return render(request, 'assessment/exam_list.html', {
        'active_exams': active_exams,
        'completed_exam_ids': completed_exam_ids
    })
@login_required
def take_exam(request, exam_id):
    # 1. Lấy thông tin kỳ thi
    exam = get_object_or_404(Exam, id=exam_id)
    now = timezone.now()

    # 2. KIỂM TRA RÀNG BUỘC (GUARDS)
    
    # Ràng buộc A: Kiểm tra nhân viên có được giao bài thi này không
    if request.user not in exam.assigned_users.all() and not request.user.is_staff:
        messages.error(request, "Bạn không có tên trong danh sách nhân viên dự thi kỳ thi này.")
        return redirect('exam_list')

    # Ràng buộc B: Kiểm tra thời gian bắt đầu và kết thúc của kỳ thi
    if now < exam.start_time:
        messages.warning(request, f"Kỳ thi chưa bắt đầu. Vui lòng quay lại lúc {exam.start_time.strftime('%H:%M %d/%m/%Y')}.")
        return redirect('exam_list')
            
    if now > exam.end_time:
        messages.error(request, "Kỳ thi này đã kết thúc thời gian làm bài.")
        return redirect('exam_list')

    # Ràng buộc C: Kiểm tra bài thi có đang bị khóa (is_active) không
    if not exam.is_active:
        messages.error(request, "Kỳ thi hiện đang bị khóa bởi quản trị viên.")
        return redirect('exam_list')

    # Ràng buộc D (ĐÃ SỬA): Dùng 'submitted_at' để chặn thi lại tuyệt đối
    existing_submission = ExamSubmission.objects.filter(
        user=request.user, 
        exam=exam, 
        submitted_at__isnull=False # Bất cứ ai đã có giờ nộp bài là bị chặn
    ).first()
    
    if existing_submission:
        return render(request, 'assessment/result_notice.html', {
            'submission': existing_submission,
            'message': 'Bạn đã nộp bài thi này rồi. Đang chờ kết quả hoặc đã có điểm.'
        })

    # 3. KHỞI TẠO HOẶC LẤY LƯỢT LÀM BÀI (Dành cho trường hợp đang làm thì rớt mạng)
    submission, created = ExamSubmission.objects.get_or_create(
        user=request.user, 
        exam=exam, 
        defaults={'is_completed': False}
    )

    if request.method == 'POST':
        if timezone.now() > exam.end_time:
            submission.is_completed = True
            submission.submitted_at = timezone.now()
            submission.save()
            messages.error(request, "Hệ thống đã tự động nộp bài vì hết giờ quy định.")
            return redirect('exam_list')

        questions = exam.questions.all()
        total_auto_score = 0
        needs_manual_grading = False # THÊM CỜ NÀY ĐỂ THEO DÕI

        for q in questions:
            # Lấy hoặc tạo bản ghi câu trả lời
            answer_obj, _ = UserAnswer.objects.get_or_create(submission=submission, question=q)
            
            # Xử lý trắc nghiệm
            if q.q_type in ['single', 'multiple']:
                choice_ids = request.POST.getlist(f'q_{q.id}')
                if choice_ids:
                    answer_obj.selected_choices.set(choice_ids)
                
                # Logic tính điểm tự động cho Single Choice
# Logic tính điểm tự động cho Single Choice
                if q.q_type == 'single' and choice_ids:
                    correct_choice = q.choices.filter(is_correct=True).first()
                    if correct_choice and str(correct_choice.id) == choice_ids[0]:
                        total_auto_score += q.points
                        answer_obj.graded_score = q.points # <--- THÊM DÒNG NÀY ĐỂ LƯU ĐIỂM TỪNG CÂU
                        
                # Logic tính điểm tự động cho Multiple Choice
                elif q.q_type == 'multiple' and choice_ids:
                    correct_ids = list(q.choices.filter(is_correct=True).values_list('id', flat=True))
                    selected_ids = [int(i) for i in choice_ids]
                    if sorted(correct_ids) == sorted(selected_ids):
                        total_auto_score += q.points
                        answer_obj.graded_score = q.points # <--- THÊM DÒNG NÀY ĐỂ LƯU ĐIỂM TỪNG CÂU

            # Xử lý tự luận
            elif q.q_type == 'essay':
                essay_text = request.POST.get(f'q_{q.id}', '').strip()
                answer_obj.essay_answer = essay_text
                # NẾU CÓ TRẢ LỜI, BẬT CỜ CẦN CHẤM TAY LÊN
                if essay_text: 
                    needs_manual_grading = True
            
            # Xử lý hình ảnh
            elif q.q_type in ['image', 'image_upload']:
                if f'q_{q.id}' in request.FILES:
                    answer_obj.image_answer = request.FILES[f'q_{q.id}']
                    # NẾU CÓ TẢI ẢNH, BẬT CỜ CẦN CHẤM TAY LÊN
                    needs_manual_grading = True
            
            answer_obj.save()

        # ==========================================
        # LOGIC XỬ LÝ TỔNG ĐIỂM VÀ TRẠNG THÁI NỘP BÀI (ĐÃ FIX)
        # ==========================================
        submission.auto_score = total_auto_score
        submission.submitted_at = timezone.now() 
        
        # SỬ DỤNG CỜ ĐÃ TRACK TRONG VÒNG LẶP THAY VÌ KIỂM TRA LẠI DATABASE
        if needs_manual_grading:
            # Thí sinh có trả lời ít nhất 1 câu tự luận/ảnh -> Chờ Admin chấm
            submission.is_completed = False 
        else:
            # 100% trắc nghiệm HOẶC thí sinh nộp bài trắng phần tự luận -> Hoàn thành
            submission.is_completed = True
            submission.manual_score = 0.0

        submission.save()

        return render(request, 'assessment/result_notice.html', {'submission': submission})

    # 5. HIỂN THỊ ĐỀ THI (GET)
    context = {
        'exam': exam,
        'questions': exam.questions.all().prefetch_related('choices'),
        'submission': submission,
        # Tính toán thời gian còn lại cho Javascript đếm ngược (nếu cần)
        'time_remaining': exam.duration_minutes * 60 
    }
    return render(request, 'assessment/take_exam.html', context)
# ================= ADMIN VIEWS (QUẢN TRỊ) =================

# assessment/views.py

@admin_only
def admin_dashboard(request):
    now = timezone.now()
    
    # Lấy QuerySet cơ bản
    all_exams = Exam.objects.all().order_by('-id') 
    all_courses = Course.objects.all().order_by('-created_at')
    active_jobs = JobPosting.objects.filter(is_active=True).count()
    total_candidates = Candidate.objects.count()
    upcoming_interviews = Interview.objects.filter(interview_time__gte=timezone.now()).count()
    recent_candidates = Candidate.objects.select_related('job_posting').order_by('-applied_at')
    context = {
        # ==========================================
        # 1. DỮ LIỆU MODULE ĐÁNH GIÁ (ASSESSMENT)
        'jobs': JobPosting.objects.filter(is_active=True), # Thêm dòng này để Modal lấy được danh sách Job
        'total_exams': all_exams.count(),
        'active_exams_count': all_exams.filter(is_active=True, end_time__gt=now).count(),
        'total_users': User.objects.count(),
        'total_submissions': ExamSubmission.objects.filter(is_completed=True).count(),
        'exams': all_exams,  # THÊM DÒNG NÀY ĐỂ FIX LỖI Failed lookup for key [exams]
        'recent_exams': all_exams[:5],
        'recent_submissions': ExamSubmission.objects.filter(is_completed=True).order_by('-submitted_at'),
        # Biến mới cho HR
        'active_jobs': active_jobs,
        'total_candidates': total_candidates,
        'upcoming_interviews': upcoming_interviews,
        'recent_candidates': recent_candidates,
        # ==========================================
        # 2. DỮ LIỆU MODULE ĐÀO TẠO (TRAINING)
        # ==========================================
        'total_courses': all_courses.count(),
        'active_learners': Enrollment.objects.filter(is_completed=False).count(),
        'completed_learners': Enrollment.objects.filter(is_completed=True).count(),
        'recent_courses': all_courses[:5],
    }
    return render(request, 'assessment/admin/dashboard.html', context)

import json
from django.contrib.auth.models import User
# (Nhớ đảm bảo bạn đã import các thư viện trên ở đầu file nhé)

@admin_only
def exam_create(request):
    # 1. TẠO TỪ ĐIỂN MAP ID_NHÂN_VIÊN VÀ CHỨC DANH
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile') and u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass

    # 2. XỬ LÝ FORM NHƯ CŨ
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('admin_dashboard')
        else:
            # Debug: In lỗi ra terminal nếu lưu thất bại
            print("Lỗi Form Exam:", form.errors)
    else:
        form = ExamForm()
        
    # 3. ĐÓNG GÓI VÀ TRUYỀN DỮ LIỆU RA GIAO DIỆN
    context = {
        'form': form, 
        'title': 'Tạo kỳ thi mới',
        'user_positions_json': json.dumps(user_positions)  # Thêm dòng này
    }
    
    return render(request, 'assessment/admin/exam_form.html', context)

# assessment/views.py

@admin_only
def exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    # Lấy danh sách câu hỏi đang có trong đề thi này
    questions_in_exam = exam.questions.all().order_by('-created_at')
    
    # Lấy ngân hàng câu hỏi (loại trừ những câu đã có trong đề thi này)
    question_bank = Question.objects.exclude(id__in=questions_in_exam.values_list('id', flat=True))

    if request.method == 'POST':
        # TRƯỜNG HỢP 1: Admin chọn câu hỏi từ ngân hàng Modal
        if 'add_from_bank' in request.POST:
            selected_q_ids = request.POST.getlist('selected_questions')
            if selected_q_ids:
                exam.questions.add(*selected_q_ids)
            return redirect('exam_edit', pk=exam.id)
            
        # TRƯỜNG HỢP 2: Lưu thông tin cấu hình kỳ thi (Tên, thời gian...)
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            return redirect('admin_dashboard')
    else:
        form = ExamForm(instance=exam)
        
    return render(request, 'assessment/admin/exam_form.html', {
        'form': form, 
        'exam': exam, 
        'questions': questions_in_exam,
        'question_bank': question_bank,
        'title': 'Chỉnh sửa kỳ thi'
    })
@admin_only
def exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == 'POST':
        exam.delete()
        return redirect('admin_dashboard')
    return render(request, 'assessment/admin/exam_confirm_delete.html', {'exam': exam})


@admin_only
def admin_results(request):
    exam_id = request.GET.get('exam')
    submissions = ExamSubmission.objects.all().order_by('-submitted_at')
    if exam_id:
        submissions = submissions.filter(exam_id=exam_id)
    return render(request, 'assessment/admin/results_list.html', {'submissions': submissions})

@admin_only
def grade_submission(request, submission_id):
    # 1. Lấy bài nộp
    submission = get_object_or_404(ExamSubmission, id=submission_id)
    
    # 2. Lọc các câu trả lời thuộc loại cần chấm tay (essay, image, image_upload)
    # Lưu ý: Tui dùng __in để bao quát cả các tên loại ní có thể đã đặt
    answers = UserAnswer.objects.filter(
        submission=submission, 
        question__q_type__in=['essay', 'image', 'image_upload']
    )
    
    # 3. KIỂM TRA: Nếu bài thi này vốn dĩ không có câu tự luận nào
    if not answers.exists():
        # Tự động chốt điểm và hoàn thành bài thi nếu chưa xong
        if not submission.is_completed:
            submission.manual_score = 0.0
            submission.is_completed = True
            submission.save()
            messages.info(request, f"Bài thi của {submission.user.username} 100% trắc nghiệm, đã được máy chấm xong.")
        else:
            messages.info(request, "Bài thi này không có nội dung cần chấm tay.")
        return redirect('admin_results')

    # 4. XỬ LÝ LƯU ĐIỂM (POST)
    if request.method == 'POST':
        total_manual = 0
        for answer in answers:
            # Lấy điểm từ form
            score_val = request.POST.get(f'score_{answer.id}', 0)
            try:
                score = float(score_val)
            except ValueError:
                score = 0.0
            
            # Đảm bảo không chấm lố điểm tối đa
            if score > answer.question.points:
                score = answer.question.points
            
            answer.graded_score = score
            # Cập nhật thêm ghi chú nếu ní có trường này trong Model UserAnswer
            comment = request.POST.get(f'comment_{answer.id}', '')
            if hasattr(answer, 'admin_comment'):
                answer.admin_comment = comment
                
            answer.save()
            total_manual += score
            
        # Cập nhật kết quả cuối cùng cho bài nộp
        submission.manual_score = total_manual
        submission.is_completed = True # Đánh dấu đã chấm xong hoàn toàn
        submission.save()
        
        messages.success(request, f"Đã cập nhật điểm tay cho thí sinh {submission.user.username}")
        return redirect('admin_results')

    # 5. HIỂN THỊ FORM (GET)
    return render(request, 'assessment/admin/grade_form.html', {
        'submission': submission,
        'answers': answers
    })
@admin_only
def question_edit(request, exam_id, question_id=None):
    """View dùng chung cho cả THÊM và SỬA câu hỏi, hỗ trợ Inline Formset để sửa đáp án"""
    exam = get_object_or_404(Exam, id=exam_id)
    question = get_object_or_404(Question, id=question_id) if question_id else Question()

    if request.method == 'POST':
        form = QuestionForm(request.POST, request.FILES, instance=question)
        formset = ChoiceFormSet(request.POST, instance=question)
        
        if form.is_valid() and formset.is_valid():
            question = form.save()
            formset.save()
            if not question_id:  # Chỉ add vào exam nếu là tạo mới
                exam.questions.add(question)
            
            messages.success(request, "Đã lưu câu hỏi thành công.")
            return redirect('exam_edit', pk=exam.id)
        else:
            messages.error(request, "Vui lòng kiểm tra lại các thông tin nhập liệu.")
    else:
        form = QuestionForm(instance=question)
        formset = ChoiceFormSet(instance=question)

    # QUAN TRỌNG: Lấy danh sách Competency để hiển thị trong Modal quản lý
    competencies = Competency.objects.all().order_by('-id')

    return render(request, 'assessment/admin/question_form.html', {
        'form': form,
        'choices': formset, # Đổi tên từ 'formset' thành 'choices' để khớp với template question_form
        'exam': exam,
        'competencies': competencies, # Truyền danh sách năng lực xuống
        'title': 'Sửa câu hỏi' if question_id else 'Thêm câu hỏi mới',
        'is_edit': bool(question_id)
    })

@admin_only
def question_add(request, exam_id):
    # Đơn giản là gọi lại hàm question_edit nhưng không truyền question_id
    return question_edit(request, exam_id)

@admin_only
def question_remove(request, exam_id, question_id):
    if request.method == 'POST':
        exam = get_object_or_404(Exam, id=exam_id)
        question = get_object_or_404(Question, id=question_id)
        exam.questions.remove(question) # Chỉ gỡ mối quan hệ, không xóa Question khỏi DB
        messages.info(request, "Đã gỡ câu hỏi khỏi đề thi.")
    return redirect('exam_edit', pk=exam_id)

# --- VIEW AJAX CHO COMPETENCY ---
@admin_only
def competency_manage(request):
    competencies = Competency.objects.all()
    return render(request, 'assessment/admin/competency_list_partial.html', {'competencies': competencies})

@admin_only
def competency_add_ajax(request):
    """Thêm nhanh năng lực qua AJAX"""
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            comp, created = Competency.objects.get_or_create(name=name)
            return JsonResponse({'status': 'success', 'id': comp.id, 'name': comp.name})
    return JsonResponse({'status': 'error'}, status=400)

@admin_only
def competency_delete_ajax(request, pk):
    """Xóa năng lực qua AJAX"""
    if request.method == 'POST':
        comp = get_object_or_404(Competency, pk=pk)
        comp.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@admin_only
def user_list(request):
    users = User.objects.all().select_related('profile').order_by('-date_joined')
    return render(request, 'assessment/admin/user_list.html', {'users': users})

@admin_only
def user_add(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Đặt mật khẩu mặc định là username123 nếu muốn
            user.set_password(user.username + "123")
            user.save()
            messages.success(request, f"Đã thêm nhân viên {user.username} thành công!")
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
        user.delete()
        messages.success(request, "Đã xóa nhân viên.")
    return redirect('user_list')

@admin_only
def user_password_reset(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        default_password = f"Hoanmy@123"
        user.set_password(default_password)
        user.save()
        messages.success(request, f"Đã reset mật khẩu cho {user.username} về mặc định: {default_password}")
    return redirect('user_list')


@admin_only
def user_import_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        file = request.FILES['excel_file']
        
        try:
            # 1. Đọc file
            df = pd.read_excel(file)
            
            # 2. CHUẨN HÓA TÊN CỘT: Biến tất cả tên cột thành chữ thường, xóa khoảng trắng dư
            # (Giúp HR gõ "Email", " EMAIL ", hay "email" thì máy đều hiểu)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            # Kiểm tra sống còn: Bắt buộc phải có cột username
            if 'username' not in df.columns:
                messages.error(request, 'Lỗi: File Excel bắt buộc phải có cột "username".')
                return redirect('user_list')
            
            # 3. Biến tất cả các ô trống (NaN) thành chuỗi rỗng để không bị lỗi
            df = df.fillna('')
            
            success_count = 0
            skipped_count = 0
            
            from assessment.models import Profile
            
            for _, row in df.iterrows():
                # Lấy username, nếu dòng đó trống thì bỏ qua
                username = str(row['username']).strip()
                if not username:
                    continue
                
                # LẤY DỮ LIỆU CỰC KỲ AN TOÀN (Không có cột thì tự gán rỗng '')
                password = str(row.get('password', '')).strip() or 'Hoanmy@123'
                email = str(row.get('email', '')).strip()
                full_name = str(row.get('full_name', '')).strip()

                if not User.objects.filter(username=username).exists():
                    # Tạo User (Ngày tham gia tự động được tính là lúc bấm nút Import)
                    user = User.objects.create_user(
                        username=username,
                        password=password,
                        email=email,
                        first_name=full_name,
                        is_staff=False
                    )
                    
                    # Tạo Profile hiển thị tên
                    Profile.objects.update_or_create(
                        user=user,
                        defaults={'full_name': full_name}
                    )
                    
                    success_count += 1
                else:
                    skipped_count += 1
            
            messages.success(request, f'Thành công: Thêm mới {success_count} nhân viên. Bỏ qua {skipped_count} người đã tồn tại.')
            
        except Exception as e:
            messages.error(request, f'Lỗi hệ thống khi xử lý file: {str(e)}')
            
    return redirect('user_list')
# 1. Hàm Xuất danh sách nhân viên hiện có
@admin_only
def user_export_excel(request):
    # Lấy dữ liệu, ta lấy 'first_name' vì logic trước đó mình lưu full_name vào đây
    users = User.objects.all().values('username', 'first_name', 'email', 'date_joined')
    df = pd.DataFrame(list(users))
    
    # ĐỔI TÊN CỘT ĐỂ ĐỒNG BỘ: từ 'first_name' thành 'full_name'
    df = df.rename(columns={
        'first_name': 'full_name',
        'username': 'username',
        'email': 'email',
        'date_joined': 'Ngày tham gia'
    })
    
    # Định dạng lại ngày tháng
    if not df.empty:
        df['Ngày tham gia'] = df['Ngày tham gia'].dt.strftime('%d/%m/%Y')
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Nhan_Vien')
    
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Danh_sach_nhan_vien.xlsx'
    return response

# 2. Hàm Tải File Mẫu (Cũng phải bỏ last_name đi)
@admin_only
def user_download_template(request):
    # Chỉ để lại các cột cần thiết cho việc Import
    columns = ['username', 'password', 'full_name', 'email']
    df = pd.DataFrame(columns=columns)
    
    # Dòng dữ liệu mẫu để HR biết cách điền
    df.loc[0] = ['nv001', 'Hoanmy@123', 'Nguyễn Văn An', 'an.nv@hoanmy.com']
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template_Import')
    
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_Nhan_Vien.xlsx'
    return response