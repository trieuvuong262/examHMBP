from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from .models import Exam, ExamSubmission, Question, UserAnswer, Choice
from .forms import ExamForm, QuestionForm, ChoiceFormSet, UserForm
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from training.models import Course, Enrollment
from django.contrib.auth.hashers import make_password 
from recruitment.models import JobPosting, Candidate, Interview
import pandas as pd
from django.contrib.auth.models import User
from django.http import HttpResponse
import io
from assessment.decorators import admin_only
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib import messages
from .models import (
    Exam, 
    Question, 
    Choice, 
    ExamSubmission, 
    UserAnswer, 
    Profile,
    Competency
)

from .forms import (
    ExamForm, 
    QuestionForm, 
    ChoiceFormSet,
    UserForm 
)
@login_required
def home_portal(request):
    return render(request, 'portal.html')

@login_required
def exam_list(request):
    now = timezone.now()
    
    active_exams = Exam.objects.filter(
        assigned_users=request.user, 
        is_active=True,
        start_time__lte=now,
        end_time__gte=now
    ).distinct()

    submissions = ExamSubmission.objects.filter(
        user=request.user, 
        submitted_at__isnull=False
    ).prefetch_related('answers__question')

    completed_exam_ids = submissions.values_list('exam_id', flat=True)

    submission_results = {}
    for s in submissions:
        mc_score = 0
        essay_score = 0
        
        for ans in s.answers.all():
            score_val = ans.graded_score or 0
            if ans.question.q_type in ['single', 'multiple']:
                mc_score += score_val
            else:
                essay_score += score_val
        
        duration_spent = 0
        if s.submitted_at and s.start_at:
            diff = s.submitted_at - s.start_at
            duration_spent = int(diff.total_seconds() / 60)
            if duration_spent < 1: duration_spent = 1

        submission_results[s.exam_id] = {
            'total_score': s.total_score, 
            'mc_score': mc_score,
            'essay_score': essay_score,
            'is_completed': s.is_completed,
            'submitted_at': s.submitted_at,
            'duration_spent': duration_spent,
        }

    return render(request, 'assessment/exam_list.html', {
        'active_exams': active_exams,
        'completed_exam_ids': completed_exam_ids,
        'submission_results': submission_results 
    })
@login_required
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    now = timezone.now()

    
    is_assigned_directly = exam.assigned_users.filter(id=request.user.id).exists()
    
    is_assigned_via_course = Course.objects.filter(
        final_exam=exam, 
        assigned_users=request.user
    ).exists()

    if not (is_assigned_directly or is_assigned_via_course or request.user.is_staff):
        messages.error(request, "Bạn không có quyền tham gia kỳ thi này.")
        return redirect('exam_list')

    if not exam.is_active:
        messages.error(request, "Kỳ thi hiện đang bị tạm khóa.")
        return redirect('exam_list')

    if now < exam.start_time:
        messages.warning(request, f"Kỳ thi chưa đến giờ bắt đầu ({exam.start_time|date:'H:i'})")
        return redirect('exam_list')
    
    if now > exam.end_time:
        messages.error(request, "Kỳ thi đã kết thúc thời gian hiệu lực.")
        return redirect('exam_list')

    existing_submission = ExamSubmission.objects.filter(
        user=request.user, 
        exam=exam, 
        submitted_at__isnull=False
    ).first()
    
    if existing_submission:
        return render(request, 'assessment/result_notice.html', {
            'submission': existing_submission,
            'message': 'Bạn đã hoàn tất bài thi này.'
        })

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
            answer_obj, _ = UserAnswer.objects.get_or_create(submission=submission, question=q)
            
            if q.q_type in ['single', 'multiple']:
                choice_ids = request.POST.getlist(f'q_{q.id}')
                if choice_ids:
                    answer_obj.selected_choices.set(choice_ids)
                
                if q.q_type == 'single' and choice_ids:
                    correct_choice = q.choices.filter(is_correct=True).first()
                    if correct_choice and str(correct_choice.id) == choice_ids[0]:
                        total_auto_score += q.points
                        answer_obj.graded_score = q.points 
                        
                elif q.q_type == 'multiple' and choice_ids:
                    correct_ids = list(q.choices.filter(is_correct=True).values_list('id', flat=True))
                    selected_ids = [int(i) for i in choice_ids]
                    if sorted(correct_ids) == sorted(selected_ids):
                        total_auto_score += q.points
                        answer_obj.graded_score = q.points 

            elif q.q_type == 'essay':
                essay_text = request.POST.get(f'q_{q.id}', '').strip()
                answer_obj.essay_answer = essay_text
                if essay_text: 
                    needs_manual_grading = True
            
            elif q.q_type in ['image', 'image_upload']:
                if f'q_{q.id}' in request.FILES:
                    answer_obj.image_answer = request.FILES[f'q_{q.id}']
                    needs_manual_grading = True
            
            answer_obj.save()

        submission.auto_score = total_auto_score
        submission.submitted_at = timezone.now() 
        
        if needs_manual_grading:
            submission.is_completed = False 
        else:
            submission.is_completed = True
            submission.manual_score = 0.0

        submission.save()

        return render(request, 'assessment/result_notice.html', {'submission': submission})

    context = {
        'exam': exam,
        'questions': exam.questions.all().prefetch_related('choices'),
        'submission': submission,
        'time_remaining': exam.duration_minutes * 60 
    }
    return render(request, 'assessment/take_exam.html', context)


@admin_only
def admin_dashboard(request):
    now = timezone.now()
    
    all_exams = Exam.objects.all().order_by('-id') 
    all_courses = Course.objects.all().order_by('-created_at')
    active_jobs = JobPosting.objects.filter(is_active=True).count()
    total_candidates = Candidate.objects.count()
    upcoming_interviews = Interview.objects.filter(interview_time__gte=timezone.now()).count()
    recent_candidates = Candidate.objects.select_related('job_posting').order_by('-applied_at')
    context = {
        'jobs': JobPosting.objects.filter(is_active=True), 
        'total_exams': all_exams.count(),
        'active_exams_count': all_exams.filter(is_active=True, end_time__gt=now).count(),
        'total_users': User.objects.count(),
        'total_submissions': ExamSubmission.objects.filter(is_completed=True).count(),
        'exams': all_exams,  # THÊM DÒNG NÀY ĐỂ FIX LỖI Failed lookup for key [exams]
        'recent_exams': all_exams[:5],
        'recent_submissions': ExamSubmission.objects.filter(is_completed=True).order_by('-submitted_at'),
        'active_jobs': active_jobs,
        'total_candidates': total_candidates,
        'upcoming_interviews': upcoming_interviews,
        'recent_candidates': recent_candidates,
        'total_courses': all_courses.count(),
        'active_learners': Enrollment.objects.filter(is_completed=False).count(),
        'completed_learners': Enrollment.objects.filter(is_completed=True).count(),
        'recent_courses': all_courses[:5],
    }
    return render(request, 'assessment/admin/dashboard.html', context)

import json
from django.contrib.auth.models import User

@admin_only
def exam_create(request):
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile') and u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass

    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('admin_dashboard')
        else:
            print("Lỗi Form Exam:", form.errors)
    else:
        form = ExamForm()
        
    context = {
        'form': form, 
        'title': 'Tạo kỳ thi mới',
        'user_positions_json': json.dumps(user_positions)  
    }
    
    return render(request, 'assessment/admin/exam_form.html', context)


@admin_only
def exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    questions_in_exam = exam.questions.all().order_by('-created_at')
    
    question_bank = Question.objects.exclude(id__in=questions_in_exam.values_list('id', flat=True))

    if request.method == 'POST':
        if 'add_from_bank' in request.POST:
            selected_q_ids = request.POST.getlist('selected_questions')
            if selected_q_ids:
                exam.questions.add(*selected_q_ids)
            return redirect('exam_edit', pk=exam.id)
            
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
    submission = get_object_or_404(ExamSubmission, id=submission_id)
    
    answers = UserAnswer.objects.filter(
        submission=submission, 
        question__q_type__in=['essay', 'image', 'image_upload']
    )
    
    if not answers.exists():
        if not submission.is_completed:
            submission.manual_score = 0.0
            submission.is_completed = True
            submission.save()
            messages.info(request, f"Bài thi của {submission.user.username} 100% trắc nghiệm, đã được máy chấm xong.")
        else:
            messages.info(request, "Bài thi này không có nội dung cần chấm tay.")
        return redirect('admin_results')

    if request.method == 'POST':
        total_manual = 0
        for answer in answers:
            score_val = request.POST.get(f'score_{answer.id}', 0)
            try:
                score = float(score_val)
            except ValueError:
                score = 0.0
            
            if score > answer.question.points:
                score = answer.question.points
            
            answer.graded_score = score
            comment = request.POST.get(f'comment_{answer.id}', '')
            if hasattr(answer, 'admin_comment'):
                answer.admin_comment = comment
                
            answer.save()
            total_manual += score
            
        submission.manual_score = total_manual
        submission.is_completed = True
        submission.save()
        
        messages.success(request, f"Đã cập nhật điểm tay cho thí sinh {submission.user.username}")
        return redirect('admin_results')

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
            if not question_id: 
                exam.questions.add(question)
            
            messages.success(request, "Đã lưu câu hỏi thành công.")
            return redirect('exam_edit', pk=exam.id)
        else:
            messages.error(request, "Vui lòng kiểm tra lại các thông tin nhập liệu.")
    else:
        form = QuestionForm(instance=question)
        formset = ChoiceFormSet(instance=question)

    competencies = Competency.objects.all().order_by('-id')

    return render(request, 'assessment/admin/question_form.html', {
        'form': form,
        'choices': formset,
        'exam': exam,
        'competencies': competencies,
        'title': 'Sửa câu hỏi' if question_id else 'Thêm câu hỏi mới',
        'is_edit': bool(question_id)
    })

@admin_only
def question_add(request, exam_id):
    return question_edit(request, exam_id)

@admin_only
def question_remove(request, exam_id, question_id):
    if request.method == 'POST':
        exam = get_object_or_404(Exam, id=exam_id)
        question = get_object_or_404(Question, id=question_id)
        exam.questions.remove(question) 
        messages.info(request, "Đã gỡ câu hỏi khỏi đề thi.")
    return redirect('exam_edit', pk=exam_id)

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
            user = form.save(commit=False)
            
            # 1. Sinh Username tự động từ Full Name (giả sử lưu ở first_name)
            full_name = user.first_name 
            new_username = generate_hm_username(full_name)
            user.username = new_username
            user.email = new_username  # Lấy email làm username luôn cho tiện
            
            # 2. Sinh mật khẩu ngẫu nhiên
            new_password = generate_secure_password()
            user.set_password(new_password)
            user.save()
            
            # Cảnh báo: Hiện mật khẩu ngay lên màn hình để Admin copy gửi cho nhân viên
            messages.success(request, f"Thêm nhân viên thành công! Tài khoản: {new_username} | Mật khẩu: {new_password}")
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
        # 1. Lưu lại email của người này trước khi xóa
        deleted_email = user.email 
        
        # 2. Búng tay bay màu tài khoản
        user.delete()
        
        # 3. ĐỒNG BỘ KANBAN: Nếu người này từng là ứng viên (quét theo email), 
        # nhả trạng thái của họ từ 'hired' về lại 'interviewing' (Đang phỏng vấn)
        if deleted_email:
            from recruitment.models import Candidate # Có thể import thẳng trong hàm cũng được
            Candidate.objects.filter(email=deleted_email, status='hired').update(status='interviewing')
            
        messages.success(request, "Đã xóa nhân viên và đồng bộ lại thẻ Ứng viên (nếu có).")
        
    return redirect('user_list')

@admin_only
def user_password_reset(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        # 1. Gọi hàm tạo pass ngẫu nhiên (Hàm này tui đã dặn thêm ở đầu file)
        new_password = generate_secure_password()
        
        # 2. Cài pass mới
        user.set_password(new_password)
        user.save()
        
        # 3. Bắn thông báo lên màn hình xanh
        messages.success(request, f"Đã Reset mật khẩu cho {user.username}. Mật khẩu mới là: {new_password}")
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
            skipped_count = 0
            from assessment.models import Profile
            
            for _, row in df.iterrows():
                full_name = str(row.get('full_name', '')).strip()
                if not full_name:
                    continue # Bỏ qua nếu không có tên
                
                # 1. Tự động gen Username/Email nếu trong file Excel không nhập
                raw_username = str(row.get('username', '')).strip()
                username = raw_username if raw_username else generate_hm_username(full_name)
                email = str(row.get('email', '')).strip() or username
                
                # 2. Tự động gen mật khẩu nếu file Excel để trống
                raw_password = str(row.get('password', '')).strip()
                password = raw_password if raw_password else generate_secure_password()
                
                chuc_danh = str(row.get('chuc_danh', '')).strip()

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
            
            messages.success(request, f'Thành công: Thêm mới {success_count} nhân viên. Bỏ qua {skipped_count} do trùng lặp.')
            
        except Exception as e:
            messages.error(request, f'Lỗi hệ thống khi xử lý file: {str(e)}')
            
    return redirect('user_list')

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
            
            from assessment.models import Profile
            
            for _, row in df.iterrows():
                username = str(row['username']).strip()
                if not username:
                    continue
                
                password = str(row.get('password', '')).strip() or 'Hoanmy@123'
                email = str(row.get('email', '')).strip()
                full_name = str(row.get('full_name', '')).strip()
                chuc_danh = str(row.get('chuc_danh', '')).strip()

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
                        defaults={
                            'full_name': full_name,
                            'position': chuc_danh 
                        }
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
        'first_name': 'full_name',
        'username': 'username',
        'email': 'email',
        'date_joined': 'Ngày tham gia',
        'profile__position': 'chuc_danh'
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




class MyPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        # Đây là khúc quan trọng nhất:
        # Khi người dùng đổi mật khẩu thành công, ta tắt cờ "đăng nhập lần đầu"
        user = self.request.user
        if hasattr(user, 'is_first_login'):
            user.is_first_login = False
            user.save()
            
        messages.success(self.request, "Mật khẩu đã được thay đổi thành công!")
        return super().form_valid(form)