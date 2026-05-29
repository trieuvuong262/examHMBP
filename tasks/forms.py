from django import forms
from django.contrib.auth.models import User

from hrm.permissions import get_report_team_users

from .models import WorkTask


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
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
        help_text='Chọn một hoặc nhiều người — mỗi người một công việc riêng, duyệt riêng.',
    )
    order_code = forms.CharField(
        required=False,
        max_length=80,
        label='Mã đơn / Style',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    product_name = forms.CharField(
        required=False,
        max_length=120,
        label='Tên SP / hạng mục',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, assigner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if assigner is not None:
            self.fields['assignees'].queryset = get_report_team_users(assigner)


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
        qs = get_report_team_users(assigner) if assigner else User.objects.none()
        if exclude_user is not None:
            qs = qs.exclude(pk=exclude_user.pk)
        self.fields['assignee'].queryset = qs
