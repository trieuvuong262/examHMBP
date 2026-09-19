from django.contrib import admin

from .models import ExamQuestion, ExamSubmission, UserAnswer


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'sort_order', 'question')
    list_filter = ('exam',)
    search_fields = ('exam__title', 'question__content')
    ordering = ('exam', 'sort_order', 'id')


class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    raw_id_fields = ('question',)
    readonly_fields = ('selected_summary',)
    fields = (
        'question',
        'selected_summary',
        'essay_answer',
        'image_answer',
        'is_graded',
        'graded_score',
    )

    @admin.display(description='Đáp án đã chọn')
    def selected_summary(self, obj):
        if not obj.pk:
            return '—'
        texts = list(obj.selected_choices.values_list('text', flat=True)[:6])
        if not texts:
            return '—'
        return ' | '.join(texts)


@admin.register(ExamSubmission)
class ExamSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user_label',
        'exam',
        'is_completed',
        'auto_score',
        'manual_score',
        'total_score_display',
        'start_at',
        'submitted_at',
    )
    list_filter = ('is_completed', 'exam')
    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'user__email',
        'user__profile__full_name',
        'user__profile__employee_code',
        'exam__title',
    )
    raw_id_fields = ('user', 'exam')
    readonly_fields = ('start_at', 'total_score_display')
    inlines = [UserAnswerInline]
    date_hierarchy = 'submitted_at'
    list_select_related = ('user', 'user__profile', 'exam')
    ordering = ('-submitted_at', '-id')

    @admin.display(description='Thí sinh', ordering='user__username')
    def user_label(self, obj):
        profile = getattr(obj.user, 'profile', None)
        return getattr(profile, 'full_name', None) or obj.user.get_full_name() or obj.user.username

    @admin.display(description='Tổng điểm')
    def total_score_display(self, obj):
        return obj.total_score
