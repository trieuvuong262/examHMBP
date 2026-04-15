from django.contrib import admin
from .models import Competency, Question, Choice, Exam, ExamSubmission, UserAnswer

# Cấu hình để nhập đáp án trắc nghiệm ngay trong giao diện nhập câu hỏi
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4  # Hiển thị sẵn 4 dòng để nhập đáp án

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('content', 'q_type', 'competency', 'points')
    list_filter = ('q_type', 'competency')
    search_fields = ('content',)
    inlines = [ChoiceInline] # Nhúng phần nhập đáp án vào đây

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time', 'duration_minutes', 'is_active')
    filter_horizontal = ('questions',) # Giao diện chọn nhiều câu hỏi dễ dàng hơn

@admin.register(ExamSubmission)
class ExamSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam', 'submitted_at', 'auto_score', 'manual_score', 'is_completed')
    readonly_fields = ('start_at', 'submitted_at')

admin.site.register(Competency)
admin.site.register(UserAnswer)