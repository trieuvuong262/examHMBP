from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from hrm.permissions import format_team_user_label, get_task_assignable_users

from .models import WorkTask, WorkTaskRecurrence


RECURRENCE_WEEKDAY_CHOICES = [
    (0, 'Thứ Hai'),
    (1, 'Thứ Ba'),
    (2, 'Thứ Tư'),
    (3, 'Thứ Năm'),
    (4, 'Thứ Sáu'),
    (5, 'Thứ Bảy'),
    (6, 'Chủ Nhật'),
]


class WorkTaskAssignForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        label='Tiêu đề',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mô tả ngắn công việc'}),
    )
    description = forms.CharField(
        required=False,
        label='Mô tả chi tiết',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )
    task_type = forms.ChoiceField(
        choices=WorkTask.TYPE_CHOICES,
        label='Loại việc',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    priority = forms.ChoiceField(
        choices=WorkTask.PRIORITY_CHOICES,
        label='Ưu tiên',
        initial=WorkTask.PRIORITY_NORMAL,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    due_date = forms.DateField(
        required=False,
        label='Hạn hoàn thành',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        label='Người nhận',
        widget=forms.CheckboxSelectMultiple(),
        help_text='Chọn một hoặc nhiều người — mỗi người một công việc riêng.',
    )
    skip_completion_review = forms.BooleanField(
        required=False,
        label='Không cần duyệt hoàn thành',
        help_text='Phù hợp việc lặp lại hoặc đơn giản — nhân viên hoàn thành sẽ được chốt luôn.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    is_recurring = forms.BooleanField(
        required=False,
        label='Công việc lặp lại theo chu kỳ',
        help_text='Hệ thống tự giao lại theo lịch — phù hợp việc định kỳ hàng ngày/tuần/tháng.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_is_recurring'}),
    )
    recurrence_frequency = forms.ChoiceField(
        choices=WorkTaskRecurrence.FREQ_CHOICES,
        required=False,
        label='Chu kỳ',
        initial=WorkTaskRecurrence.FREQ_WEEKLY,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    recurrence_interval = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        initial=1,
        label='Lặp mỗi',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 365}),
    )
    recurrence_weekday = forms.ChoiceField(
        choices=RECURRENCE_WEEKDAY_CHOICES,
        required=False,
        label='Thứ trong tuần',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    recurrence_day_of_month = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=28,
        label='Ngày trong tháng',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 28}),
    )
    recurrence_end_date = forms.DateField(
        required=False,
        label='Kết thúc lặp (tùy chọn)',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    def __init__(self, *args, assigner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if assigner is not None:
            qs = get_task_assignable_users(assigner)
            self.fields['assignees'].queryset = qs
            self.fields['assignees'].label_from_instance = format_team_user_label
        if not self.is_bound:
            today = timezone.localdate()
            self.fields['recurrence_weekday'].initial = today.weekday()
            self.fields['recurrence_day_of_month'].initial = min(today.day, 28)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('is_recurring'):
            return cleaned

        frequency = cleaned.get('recurrence_frequency') or WorkTaskRecurrence.FREQ_WEEKLY
        interval = cleaned.get('recurrence_interval') or 1
        if interval < 1:
            self.add_error('recurrence_interval', 'Giá trị phải từ 1 trở lên.')
        cleaned['recurrence_interval'] = interval

        if frequency == WorkTaskRecurrence.FREQ_WEEKLY:
            weekday = cleaned.get('recurrence_weekday')
            if weekday in (None, ''):
                self.add_error('recurrence_weekday', 'Chọn thứ trong tuần.')
            else:
                cleaned['recurrence_weekday'] = int(weekday)

        if frequency == WorkTaskRecurrence.FREQ_MONTHLY:
            dom = cleaned.get('recurrence_day_of_month')
            if not dom:
                self.add_error('recurrence_day_of_month', 'Chọn ngày trong tháng.')
            elif dom < 1 or dom > 28:
                self.add_error('recurrence_day_of_month', 'Chọn ngày từ 1 đến 28.')

        end_date = cleaned.get('recurrence_end_date')
        if end_date and end_date < timezone.localdate():
            self.add_error('recurrence_end_date', 'Ngày kết thúc phải từ hôm nay trở đi.')

        return cleaned


class WorkTaskProgressForm(forms.Form):
    progress_percent = forms.IntegerField(
        min_value=0,
        max_value=100,
        label='Tiến độ (%)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
    )
    result_note = forms.CharField(
        required=False,
        label='Ghi chú tiến độ',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class WorkTaskSubmitForm(forms.Form):
    result_note = forms.CharField(
        label='Báo cáo kết quả',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )


class WorkTaskRejectForm(forms.Form):
    reject_reason = forms.CharField(
        label='Lý do từ chối',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class WorkTaskReviewForm(forms.Form):
    review_note = forms.CharField(
        required=False,
        label='Ghi chú duyệt',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class WorkTaskReassignForm(forms.Form):
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Giao lại cho',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, assigner=None, exclude_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = get_task_assignable_users(assigner) if assigner else User.objects.none()
        if exclude_user is not None:
            qs = qs.exclude(pk=exclude_user.pk)
        self.fields['assignee'].queryset = qs
        self.fields['assignee'].label_from_instance = format_team_user_label
