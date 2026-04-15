# assessment/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Exam, ExamSubmission
from django.utils import timezone

@login_required
def exam_list(request):
    now = timezone.now()
    # Lấy các kỳ thi đang trong thời hạn
    active_exams = Exam.objects.filter(
        start_time__lte=now, 
        end_time__gte=now, 
        is_active=True
    )
    
    # Lấy ID các kỳ thi mà user này đã hoàn thành
    completed_exam_ids = ExamSubmission.objects.filter(
        user=request.user, 
        is_completed=True
    ).values_list('exam_id', flat=True)

    return render(request, 'assessment/exam_list.html', {
        'active_exams': active_exams,
        'completed_exam_ids': completed_exam_ids
    })
    
# assessment/views.py
from django.shortcuts import render, get_object_or_404, redirect
from .models import Exam, Question, ExamSubmission, UserAnswer

from django.utils import timezone

@login_required
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    # Lấy hoặc tạo lượt nộp bài
    submission, created = ExamSubmission.objects.get_or_create(
        user=request.user, 
        exam=exam,
        is_completed=False
    )
    
    if request.method == 'POST':
        questions = exam.questions.all()
        total_auto_score = 0
        
        for q in questions:
            # Tạo hoặc cập nhật câu trả lời cho từng câu hỏi
            answer_obj, _ = UserAnswer.objects.get_or_create(submission=submission, question=q)
            
            # 1. Xử lý Trắc nghiệm (Single & Multiple)
            if q.q_type in ['single', 'multiple']:
                choice_ids = request.POST.getlist(f'q_{q.id}')
                answer_obj.selected_choices.set(choice_ids)
                
                # Tính điểm tự động cho trắc nghiệm 1 đáp án
                if q.q_type == 'single' and choice_ids:
                    correct_choice = q.choices.filter(is_correct=True).first()
                    if correct_choice and str(correct_choice.id) == choice_ids[0]:
                        total_auto_score += q.points

            # 2. Xử lý Tự luận
            elif q.q_type == 'essay':
                answer_obj.essay_answer = request.POST.get(f'q_{q.id}')
            
            # 3. Xử lý Hình ảnh
            elif q.q_type == 'image':
                if f'q_{q.id}' in request.FILES:
                    answer_obj.image_answer = request.FILES[f'q_{q.id}']
            
            answer_obj.save()

        # Cập nhật trạng thái hoàn thành bài thi
        submission.auto_score = total_auto_score
        submission.is_completed = True
        submission.submitted_at = timezone.now()
        submission.save()

        return render(request, 'assessment/result_notice.html', {'submission': submission})

    # Nếu là GET: Hiển thị form thi
    context = {
        'exam': exam,
        'questions': exam.questions.all().prefetch_related('choices'),
        'submission': submission
    }
    return render(request, 'assessment/take_exam.html', context)