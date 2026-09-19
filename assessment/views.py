from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from .models import Exam, ExamSubmission, Question, UserAnswer, Choice, ExamQuestion
from .forms import ExamForm, QuestionForm, ChoiceFormSet, UserForm, save_choice_formset_in_order
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from training.models import Course, Enrollment
from django.contrib.auth.hashers import make_password 
from recruitment.models import JobPosting, Candidate, Interview
import pandas as pd
from django.contrib.auth.models import User
from django.http import HttpResponse
import io
from assessment.decorators import dashboard_hub_required, module_perm_required
from hrm.module_permissions import (
    MODULE_ASSESSMENT,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_update_module,
)
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.contrib.auth import logout
from django.db.models import Count, Q
from PortalJustPlay.list_search import apply_term_search, get_search_query, search_terms
from PortalJustPlay.pagination import paginate_queryset
from kpi.models import MonthlyKpi
from hrm.permissions import is_manager, is_portal_admin
from tools.catalog import get_portal_tool_groups
from .portal_widgets import get_portal_dashboard
from .models import (
    Exam, 
    Question, 
    Choice, 
    ExamSubmission, 
    UserAnswer, 
    Competency,
    Certificate,
)

from .scoring import grade_mc_answer, rescore_submission, round_score
from .certificates import apply_exam_pass_or_retry


@login_required
def login_redirect_view(request):
    """Sau đăng nhập — mọi user về trang chủ portal."""
    return redirect('home_portal')

@login_required
def home_portal(request):
    return render(request, 'portal.html', {
        'portal_tool_groups': get_portal_tool_groups(),
        'dashboard_widgets': get_portal_dashboard(request.user),
    })

def _assessment_perm_context(user):
    return {
        'can_create': user_can_create_module(user, MODULE_ASSESSMENT),
        'can_update': user_can_update_module(user, MODULE_ASSESSMENT),
        'can_delete': user_can_delete_module(user, MODULE_ASSESSMENT),
        'is_admin': user_can_edit_module(user, MODULE_ASSESSMENT),
    }


def _submission_result_summary(submission):
    mc_score = 0
    essay_score = 0
    for ans in submission.answers.select_related('question').all():
        score_val = round_score(ans.graded_score or 0)
        if ans.question.q_type in ['single', 'multiple']:
            mc_score += score_val
        else:
            essay_score += score_val

    duration_spent = 1
    if submission.submitted_at and submission.start_at:
        diff = submission.submitted_at - submission.start_at
        duration_spent = max(1, int(diff.total_seconds() / 60))

    return {
        'total_score': round_score(submission.total_score),
        'mc_score': round_score(mc_score),
        'essay_score': round_score(essay_score),
        'is_completed': submission.is_completed,
        'submitted_at': submission.submitted_at,
        'duration_spent': duration_spent,
    }


@module_perm_required(MODULE_ASSESSMENT, 'view')
def exam_list(request):
    now = timezone.now()
    
    active_exams_qs = Exam.objects.filter(
        assigned_users=request.user, 
        is_active=True,
        start_time__lte=now,
        end_time__gte=now
    ).distinct().order_by('-start_time')
    search_query = get_search_query(request)
    active_exams_qs = apply_term_search(
        active_exams_qs, search_query, 'title__icontains', 'description__icontains',
    )
    page_obj, query_string = paginate_queryset(request, active_exams_qs)
    active_exams = page_obj.object_list
    page_exam_ids = [exam.id for exam in active_exams]

    submissions = (
        ExamSubmission.objects.filter(
            user=request.user,
            exam_id__in=page_exam_ids,
            submitted_at__isnull=False,
        )
        .only('exam_id', 'auto_score', 'manual_score', 'is_completed', 'submitted_at', 'start_at')
        .order_by('-submitted_at')
    )
    submission_results = {}
    completed_exam_ids = set()
    for submission in submissions:
        if submission.exam_id in completed_exam_ids:
            continue
        completed_exam_ids.add(submission.exam_id)
        duration_spent = 1
        if submission.submitted_at and submission.start_at:
            duration_spent = max(1, int((submission.submitted_at - submission.start_at).total_seconds() / 60))
        result = {
            'total_score': round_score(submission.total_score),
            'mc_score': round_score(submission.auto_score),
            'essay_score': round_score(submission.manual_score),
            'is_completed': submission.is_completed,
            'submitted_at': submission.submitted_at,
            'duration_spent': duration_spent,
        }
        submission_results[submission.exam_id] = result

    certificates_by_exam = {
        cert.exam_id: cert
        for cert in Certificate.objects.filter(
            user=request.user,
            exam_id__in=page_exam_ids,
            is_revoked=False,
        ).only('id', 'exam_id')
    }
    for exam in active_exams:
        exam.user_certificate = certificates_by_exam.get(exam.id)
        exam.result = submission_results.get(exam.id)

    return render(request, 'assessment/exam_list.html', {
        'active_exams': active_exams,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'completed_exam_ids': completed_exam_ids,
        'submission_results': submission_results,
    })
@module_perm_required(MODULE_ASSESSMENT, 'view')
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam.objects.select_related('retry_of'), id=exam_id)
    now = timezone.now()

    if not exam.retry_of_id:
        retry_assigned = exam.retry_exams.filter(is_active=True, assigned_users=request.user).first()
        if retry_assigned:
            return redirect('take_exam', exam_id=retry_assigned.id)

    is_assigned_directly = exam.assigned_users.filter(id=request.user.id).exists()
    
    is_assigned_via_course = Course.objects.filter(
        Q(final_exam=exam) | Q(final_exam_id=exam.retry_of_id),
        assigned_users=request.user,
    ).exists() if exam.retry_of_id else Course.objects.filter(
        final_exam=exam,
        assigned_users=request.user,
    ).exists()

    if not (is_assigned_directly or is_assigned_via_course or is_portal_admin(request.user)):
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

    if not is_portal_admin(request.user):
        from training.course_exam import incomplete_courses_blocking_exam

        blockers = incomplete_courses_blocking_exam(request.user, exam)
        if blockers:
            course = blockers[0]
            return render(request, 'assessment/course_exam_gate.html', {
                'exam': exam,
                'course': course,
                'show_course_gate_modal': True,
            })

    existing_submission = ExamSubmission.objects.filter(
        user=request.user, 
        exam=exam, 
        submitted_at__isnull=False
    ).first()
    
    if existing_submission:
        return render(request, 'assessment/result_notice.html', {
            'submission': existing_submission,
            'exam': exam,
            'result': _submission_result_summary(existing_submission),
            'show_result_modal': True,
            'message': 'Bạn đã hoàn tất bài thi này.',
            'certificate': Certificate.objects.filter(
                user=request.user, exam=exam, is_revoked=False,
            ).first(),
        })

    submission, created = ExamSubmission.objects.get_or_create(
        user=request.user, 
        exam=exam, 
        defaults={'is_completed': False}
    )
    if not submission.start_at:
        submission.start_at = timezone.now()
        submission.save()

    # Tính toán chính xác thời gian còn lại (bất chấp thí sinh F5)
    elapsed_seconds = (timezone.now() - submission.start_at).total_seconds()
    real_time_remaining = int(exam.duration_minutes * 60 - elapsed_seconds)
    
    if real_time_remaining <= 0:
        real_time_remaining = 0 # Ép nộp bài nếu lố giờ

    if request.method == 'POST':
        if timezone.now() > exam.end_time:
            submission.is_completed = True
            submission.submitted_at = timezone.now()
            submission.save()
            messages.error(request, "Hệ thống đã tự động nộp bài vì hết giờ quy định.")
            return redirect('exam_list')

        questions = exam.ordered_questions()
        needs_manual_grading = False

        for q in questions:
            answer_obj, _ = UserAnswer.objects.get_or_create(submission=submission, question=q)

            if q.q_type in ['single', 'multiple']:
                choice_ids = request.POST.getlist(f'q_{q.id}')
                if choice_ids:
                    answer_obj.selected_choices.set(choice_ids)
                else:
                    answer_obj.selected_choices.clear()
                answer_obj.graded_score = grade_mc_answer(q, choice_ids)

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

        rescore_submission(submission)
        submission.submitted_at = timezone.now()
        
        if needs_manual_grading:
            submission.is_completed = False 
        else:
            submission.is_completed = True
            submission.manual_score = 0.0

        submission.save()
        result = _submission_result_summary(submission)
        outcome = apply_exam_pass_or_retry(submission)

        return render(request, 'assessment/result_notice.html', {
            'submission': submission,
            'exam': exam,
            'result': result,
            'show_result_modal': True,
            'certificate': outcome['certificate'],
            'must_retry': outcome['must_retry'],
            'retry_courses': outcome['retry_courses'],
            'retry_exam': outcome.get('retry_exam'),
        })

    context = {
        'exam': exam,
        'questions': exam.ordered_questions(),
        'submission': submission,
        'time_remaining': real_time_remaining 
    }
    return render(request, 'assessment/take_exam.html', context)


@module_perm_required(MODULE_ASSESSMENT, 'view')
def exam_result(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    submission = (
        ExamSubmission.objects.filter(
            user=request.user,
            exam=exam,
            submitted_at__isnull=False,
        )
        .prefetch_related(
            'answers__selected_choices',
            'answers__question__choices',
        )
        .first()
    )
    if not submission:
        messages.warning(request, 'Bạn chưa hoàn thành bài thi này.')
        return redirect('exam_list')

    answer_by_question = {answer.question_id: answer for answer in submission.answers.all()}
    question_rows = []

    for question in exam.ordered_questions():
        answer = answer_by_question.get(question.id)
        earned = (answer.graded_score if answer else 0) or 0
        q_type = question.q_type

        if q_type in ['single', 'multiple']:
            selected_ids = set()
            if answer:
                selected_ids = set(answer.selected_choices.values_list('id', flat=True))

            choice_rows = []
            user_picks = []
            correct_picks = []
            for choice in question.choices.all():
                is_selected = choice.id in selected_ids
                if choice.is_correct:
                    correct_picks.append(choice.text)
                if is_selected:
                    user_picks.append(choice.text)

                if choice.is_correct and is_selected:
                    state = 'ok'
                elif choice.is_correct:
                    state = 'correct'
                elif is_selected:
                    state = 'wrong'
                else:
                    state = 'idle'
                choice_rows.append({
                    'text': choice.text,
                    'state': state,
                })

            if earned >= question.points:
                status_label = 'Đúng'
                status_class = 'success'
                card_class = 'is-correct'
            elif earned > 0:
                status_label = 'Đúng một phần'
                status_class = 'warning'
                card_class = 'is-partial'
            else:
                status_label = 'Sai'
                status_class = 'danger'
                card_class = 'is-wrong'

            question_rows.append({
                'sort_order': getattr(question, 'sort_order', None),
                'content': question.content,
                'q_type': q_type,
                'q_type_display': question.get_q_type_display(),
                'points': question.points,
                'earned': earned,
                'status_label': status_label,
                'status_class': status_class,
                'card_class': card_class,
                'choice_rows': choice_rows,
                'user_answer': ' · '.join(user_picks) if user_picks else '— Chưa chọn —',
                'correct_answer': ' · '.join(correct_picks) if correct_picks else '—',
                'essay_answer': '',
                'image_answer_url': '',
            })
        elif q_type == 'essay':
            essay_text = (answer.essay_answer if answer else '') or ''
            if submission.is_completed and answer and answer.is_graded:
                status_label = f'{earned:g}/{question.points:g} đ'
                status_class = 'primary'
                card_class = 'is-graded'
            else:
                status_label = 'Đang chấm'
                status_class = 'secondary'
                card_class = 'is-pending'

            question_rows.append({
                'sort_order': getattr(question, 'sort_order', None),
                'content': question.content,
                'q_type': q_type,
                'q_type_display': question.get_q_type_display(),
                'points': question.points,
                'earned': earned,
                'status_label': status_label,
                'status_class': status_class,
                'card_class': card_class,
                'choice_rows': [],
                'user_answer': essay_text or '— Chưa trả lời —',
                'correct_answer': '',
                'essay_answer': essay_text,
                'image_answer_url': '',
            })
        else:
            image_url = ''
            if answer and answer.image_answer:
                image_url = answer.image_answer.url
            if submission.is_completed and answer and answer.is_graded:
                status_label = f'{earned:g}/{question.points:g} đ'
                status_class = 'primary'
                card_class = 'is-graded'
            else:
                status_label = 'Đang chấm'
                status_class = 'secondary'
                card_class = 'is-pending'

            question_rows.append({
                'sort_order': getattr(question, 'sort_order', None),
                'content': question.content,
                'q_type': q_type,
                'q_type_display': question.get_q_type_display(),
                'points': question.points,
                'earned': earned,
                'status_label': status_label,
                'status_class': status_class,
                'card_class': card_class,
                'choice_rows': [],
                'user_answer': 'Đã nộp ảnh' if image_url else '— Chưa nộp ảnh —',
                'correct_answer': '',
                'essay_answer': '',
                'image_answer_url': image_url,
            })

    return render(request, 'assessment/exam_result.html', {
        'exam': exam,
        'submission': submission,
        'result': _submission_result_summary(submission),
        'question_rows': question_rows,
        'certificate': Certificate.objects.filter(
            user=request.user, exam=exam, is_revoked=False,
        ).first(),
    })


@dashboard_hub_required
def admin_dashboard(request):
    now = timezone.now()
    tab = (request.GET.get('tab') or '').strip() or 'recruitment'
    context = {
        'active_kpi_periods': 0,
        'total_yearly_kpis': 0,
        'jobs': [],
        'total_exams': 0,
        'active_exams_count': 0,
        'total_users': 0,
        'total_submissions': 0,
        'total_certificates': 0,
        'exams': [],
        'exams_page': None,
        'exams_query_string': '',
        'recent_exams': [],
        'recent_submissions': [],
        'active_jobs': 0,
        'total_candidates': 0,
        'upcoming_interviews': 0,
        'recent_candidates': [],
        'total_courses': 0,
        'active_learners': 0,
        'completed_learners': 0,
        'recent_courses': [],
    }

    if tab == 'assessment':
        exams_qs = Exam.objects.only(
            'id', 'title', 'is_active', 'start_time', 'end_time', 'duration_minutes',
        ).order_by('-id')
        exams_page, exams_query_string = paginate_queryset(
            request, exams_qs, page_param='exam_page',
        )
        exam_stats = Exam.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True, end_time__gt=now)),
        )
        context.update({
            'total_exams': exam_stats['total'],
            'active_exams_count': exam_stats['active'],
            'total_submissions': ExamSubmission.objects.filter(is_completed=True).count(),
            'total_certificates': Certificate.objects.filter(is_revoked=False).count(),
            'exams': exams_page.object_list,
            'exams_page': exams_page,
            'exams_query_string': exams_query_string,
        })
    elif tab == 'training':
        courses_qs = Course.objects.order_by('-created_at')
        context.update({
            'total_courses': courses_qs.count(),
            'active_learners': Enrollment.objects.filter(is_completed=False).count(),
            'completed_learners': Enrollment.objects.filter(is_completed=True).count(),
            'recent_courses': list(courses_qs[:5]),
        })
    elif tab == 'kpi':
        now_kpi = timezone.localdate()
        context.update({
            'active_kpi_periods': MonthlyKpi.objects.filter(
                year=now_kpi.year, month=now_kpi.month,
            ).count(),
            'total_yearly_kpis': MonthlyKpi.objects.count(),
        })
    else:
        today = timezone.localdate()
        open_jobs_qs = JobPosting.objects.filter(is_active=True, deadline__gte=today)
        context.update({
            'jobs': open_jobs_qs,
            'active_jobs': open_jobs_qs.count(),
            'total_candidates': Candidate.objects.count(),
            'upcoming_interviews': Interview.objects.filter(interview_time__gte=now).count(),
            'recent_candidates': list(
                Candidate.objects.select_related('job_posting').order_by('-applied_at')[:5]
            ),
            'total_users': User.objects.count(),
        })

    return render(request, 'assessment/admin/dashboard.html', context)

@module_perm_required(MODULE_ASSESSMENT, 'create')
def exam_create(request):
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('admin_dashboard')}?tab=assessment")
        else:
            print("Lỗi Form Exam:", form.errors)
    else:
        form = ExamForm()
        
    context = {
        'form': form, 
        'title': 'Tạo kỳ thi mới',
    }
    
    return render(request, 'assessment/admin/exam_form.html', context)


@module_perm_required(MODULE_ASSESSMENT, 'update')
def exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    exam_questions = exam.ordered_exam_questions()
    questions_in_exam = [link.question for link in exam_questions]

    question_bank = (
        Question.objects.exclude(id__in=[q.id for q in questions_in_exam])
        .select_related('competency')
        .only('id', 'content', 'points', 'q_type', 'competency_id', 'competency__name')
        .order_by('-id')[:200]
    )

    if request.method == 'POST':
        if 'add_from_bank' in request.POST:
            selected_q_ids = request.POST.getlist('selected_questions')
            if selected_q_ids:
                next_order = exam.next_sort_order()
                for offset, qid in enumerate(selected_q_ids):
                    ExamQuestion.objects.get_or_create(
                        exam=exam,
                        question_id=qid,
                        defaults={'sort_order': next_order + offset},
                    )
            return redirect('exam_edit', pk=exam.id)
            
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('admin_dashboard')}?tab=assessment")
    else:
        form = ExamForm(instance=exam)
        
    return render(request, 'assessment/admin/exam_form.html', {
        'form': form,
        'exam': exam,
        'exam_questions': exam_questions,
        'questions': questions_in_exam,
        'question_bank': question_bank,
        'title': 'Chỉnh sửa kỳ thi',
        **_assessment_perm_context(request.user),
    })


@module_perm_required(MODULE_ASSESSMENT, 'delete')
def exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == 'POST':
        exam.delete()
        return redirect(f"{reverse('admin_dashboard')}?tab=assessment")
    return render(request, 'assessment/admin/exam_confirm_delete.html', {'exam': exam})


@module_perm_required(MODULE_ASSESSMENT, 'edit')
def admin_results(request):
    exam_id = request.GET.get('exam')
    search_query = get_search_query(request)
    submissions_qs = ExamSubmission.objects.select_related(
        'user', 'user__profile', 'exam',
    ).only(
        'id', 'auto_score', 'manual_score', 'is_completed', 'submitted_at',
        'user_id', 'exam_id',
        'user__username', 'user__first_name', 'user__last_name', 'user__email',
        'user__profile__full_name', 'user__profile__job_position', 'user__profile__employee_code',
        'exam__title',
    ).order_by('-submitted_at')
    if exam_id:
        submissions_qs = submissions_qs.filter(exam_id=exam_id)
    if search_query:
        for term in search_terms(search_query):
            submissions_qs = submissions_qs.filter(
                Q(user__username__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__profile__full_name__icontains=term)
                | Q(user__profile__employee_code__icontains=term)
                | Q(exam__title__icontains=term)
            )
        submissions_qs = submissions_qs.distinct()
    page_obj, query_string = paginate_queryset(request, submissions_qs)
    return render(request, 'assessment/admin/results_list.html', {
        'submissions': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'exam_id': exam_id or '',
        'total_count': page_obj.paginator.count,
    })

@module_perm_required(MODULE_ASSESSMENT, 'edit')
def admin_submission_review(request, submission_id):
    submission = get_object_or_404(
        ExamSubmission.objects.select_related('user', 'user__profile', 'exam'),
        pk=submission_id,
        submitted_at__isnull=False,
    )
    answers = (
        submission.answers.select_related('question')
        .prefetch_related('question__choices', 'selected_choices')
        .order_by('id')
    )
    return render(request, 'assessment/admin/submission_review.html', {
        'submission': submission,
        'answers': answers,
        **_assessment_perm_context(request.user),
    })

@module_perm_required(MODULE_ASSESSMENT, 'update')
def grade_submission(request, submission_id):
    submission = get_object_or_404(ExamSubmission, id=submission_id)
    
    answers = UserAnswer.objects.filter(
        submission=submission, 
        question__q_type__in=['essay', 'image', 'image_upload']
    )
    
    if not answers.exists():
        rescore_submission(submission)
        if not submission.is_completed:
            submission.is_completed = True
            submission.save(update_fields=['is_completed'])
        outcome = apply_exam_pass_or_retry(submission, by=request.user)
        if outcome['must_retry']:
            messages.warning(
                request,
                f"Bài thi của {submission.user.username} chưa đạt {int(round_score(submission.exam.pass_score))}đ. Đã xóa lịch sử khóa, giao đề thi lại và mở lại để học lại.",
            )
        elif outcome['certificate']:
            messages.info(
                request,
                f"Bài thi của {submission.user.username} đã được máy chấm và cấp chứng chỉ {outcome['certificate'].code}.",
            )
        elif not submission.is_completed:
            messages.info(request, f"Bài thi của {submission.user.username} 100% trắc nghiệm, đã được máy chấm xong.")
        else:
            messages.info(request, "Bài thi này không có nội dung cần chấm tay.")
        return redirect('admin_results')

    if request.method == 'POST':
        total_manual = 0
        for answer in answers:
            score_val = request.POST.get(f'score_{answer.id}', 0)
            try:
                score = round_score(score_val)
            except ValueError:
                score = 0.0
            
            if score > answer.question.points:
                score = round_score(answer.question.points)
            
            answer.graded_score = score
            answer.is_graded = True
            comment = request.POST.get(f'comment_{answer.id}', '')
            if hasattr(answer, 'admin_comment'):
                answer.admin_comment = comment
                
            answer.save()
            total_manual += score
            
        submission.manual_score = round_score(total_manual)
        submission.is_completed = True
        submission.save()
        rescore_submission(submission)
        outcome = apply_exam_pass_or_retry(submission, by=request.user)
        if outcome['certificate']:
            messages.success(
                request,
                f"Đã cập nhật điểm tay cho thí sinh {submission.user.username} và cấp chứng chỉ {outcome['certificate'].code}.",
            )
        elif outcome['must_retry']:
            messages.warning(
                request,
                f"Điểm chưa đạt {int(round_score(submission.exam.pass_score))}đ. Đã xóa lịch sử khóa, giao đề thi lại để học viên học lại.",
            )
        else:
            messages.success(request, f"Đã cập nhật điểm tay cho thí sinh {submission.user.username}")
        return redirect('admin_results')

    return render(request, 'assessment/admin/grade_form.html', {
        'submission': submission,
        'answers': answers
    })
@module_perm_required(MODULE_ASSESSMENT, 'update')
def question_edit(request, exam_id, question_id=None):
    """View dùng chung cho cả THÊM và SỬA câu hỏi, hỗ trợ Inline Formset để sửa đáp án"""
    exam = get_object_or_404(Exam, id=exam_id)
    question = get_object_or_404(Question, id=question_id) if question_id else Question()
    exam_question = None
    if question_id:
        exam_question = ExamQuestion.objects.filter(exam=exam, question=question).first()

    if request.method == 'POST':
        form = QuestionForm(request.POST, request.FILES, instance=question)
        formset = ChoiceFormSet(request.POST, instance=question)

        if form.is_valid() and formset.is_valid():
            question = form.save()
            save_choice_formset_in_order(formset, question)
            sort_order = form.cleaned_data['sort_order']
            if exam_question:
                exam_question.sort_order = sort_order
                exam_question.save(update_fields=['sort_order'])
            else:
                ExamQuestion.objects.create(
                    exam=exam,
                    question=question,
                    sort_order=sort_order,
                )

            messages.success(request, "Đã lưu câu hỏi thành công.")
            return redirect('exam_edit', pk=exam.id)
        else:
            messages.error(request, "Vui lòng kiểm tra lại các thông tin nhập liệu.")
    else:
        initial_sort = exam_question.sort_order if exam_question else exam.next_sort_order()
        form = QuestionForm(instance=question, initial={'sort_order': initial_sort})
        formset = ChoiceFormSet(instance=question)

    competencies = Competency.objects.all().order_by('-id')
    question_total = exam.exam_questions.count()

    return render(request, 'assessment/admin/question_form.html', {
        'form': form,
        'choices': formset,
        'exam': exam,
        'competencies': competencies,
        'title': 'Sửa câu hỏi' if question_id else 'Thêm câu hỏi mới',
        'is_edit': bool(question_id),
        'question_total': question_total,
    })

@module_perm_required(MODULE_ASSESSMENT, 'create')
def question_add(request, exam_id):
    return question_edit(request, exam_id)


@module_perm_required(MODULE_ASSESSMENT, 'update')
def question_remove(request, exam_id, question_id):
    if request.method == 'POST':
        exam = get_object_or_404(Exam, id=exam_id)
        question = get_object_or_404(Question, id=question_id)
        exam_question = get_object_or_404(ExamQuestion, exam=exam, question=question)
        exam_question.delete()
        messages.info(request, "Đã gỡ câu hỏi khỏi đề thi.")
    return redirect('exam_edit', pk=exam_id)

@module_perm_required(MODULE_ASSESSMENT, 'edit')
def competency_manage(request):
    competencies = Competency.objects.all()
    return render(request, 'assessment/admin/competency_list_partial.html', {'competencies': competencies})

@module_perm_required(MODULE_ASSESSMENT, 'create')
def competency_add_ajax(request):
    """Thêm nhanh năng lực qua AJAX"""
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            comp, created = Competency.objects.get_or_create(name=name)
            return JsonResponse({'status': 'success', 'id': comp.id, 'name': comp.name})
    return JsonResponse({'status': 'error'}, status=400)

@module_perm_required(MODULE_ASSESSMENT, 'delete')
def competency_delete_ajax(request, pk):
    """Xóa năng lực qua AJAX"""
    if request.method == 'POST':
        comp = get_object_or_404(Competency, pk=pk)
        comp.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

