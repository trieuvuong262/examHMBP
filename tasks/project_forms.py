from django import forms
from django.contrib.auth.models import User

from hrm.permissions import format_team_user_label, get_task_assignable_users

from .models import InternalProject, WorkTask


class InternalProjectForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        label='Thành viên dự án',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 8}),
        help_text='Chỉ cấp dưới trực tiếp. Dùng @username trong comment để nhắc người trong dự án.',
    )

    class Meta:
        model = InternalProject
        fields = ['title', 'description', 'due_date', 'members']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            qs = get_task_assignable_users(owner)
            self.fields['members'].queryset = qs
            self.fields['members'].label_from_instance = format_team_user_label


class ProjectStepForm(forms.Form):
    title = forms.CharField(max_length=200, label='Tên bước', widget=forms.TextInput(attrs={'class': 'form-control'}))
    description = forms.CharField(required=False, label='Mô tả', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Người phụ trách',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    depends_on = forms.ModelChoiceField(
        queryset=WorkTask.objects.none(),
        required=False,
        label='Phụ thuộc bước (tuỳ chọn)',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Để trống nếu có thể làm song song với các bước khác.',
    )
    due_date = forms.DateField(required=False, label='Hạn bước', widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    priority = forms.ChoiceField(
        choices=WorkTask.PRIORITY_CHOICES,
        initial=WorkTask.PRIORITY_NORMAL,
        label='Ưu tiên',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            members = project.members.all()
            self.fields['assignee'].queryset = members
            self.fields['assignee'].label_from_instance = format_team_user_label
            self.fields['depends_on'].queryset = project.steps.exclude(
                status__in={WorkTask.STATUS_CANCELLED, WorkTask.STATUS_HANDED_OFF},
            ).order_by('step_order', 'created_at')


class ProjectCommentForm(forms.Form):
    body = forms.CharField(
        label='Comment',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Viết cập nhật… Dùng @username để nhắc thành viên (vd: @nv_a)',
        }),
    )


class HandoffRequestForm(forms.Form):
    to_user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Chuyển giao cho',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    note = forms.CharField(
        required=False,
        label='Ghi chú',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def __init__(self, *args, project=None, exclude_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            qs = project.members.all()
            if exclude_user is not None:
                qs = qs.exclude(pk=exclude_user.pk)
            self.fields['to_user'].queryset = qs
            self.fields['to_user'].label_from_instance = format_team_user_label
