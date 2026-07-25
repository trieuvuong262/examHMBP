"""Form thiết lập chung module Báo cáo."""

from __future__ import annotations

from django import forms

from reports.models import ReportsGeneralSettings

_CHECK = forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
_TIME = forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': 60})
_NUM = forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
_DEC = forms.NumberInput(attrs={'class': 'form-control', 'min': 0.01, 'step': 0.01})

_LABELS = {
    'workers_may_edit_stage_time': 'Công nhân được sửa',
    'managers_may_edit_stage_time': 'Quản lý được sửa',
    'auto_submit_time': 'Giờ tự động nộp',
    'default_declared_work_hours': 'Giờ làm việc mặc định',
    'auto_approve_proxy_reports': 'Tự duyệt báo cáo nhập hộ',
    'work_hours_min': 'Tối thiểu',
    'work_hours_max': 'Tối đa',
    'approve_deadline_hours': 'Thời hạn duyệt',
    'auto_reject_deadline_hours': 'Thời hạn không duyệt',
    'unapprove_deadline_days': 'Thời hạn hoàn duyệt',
    'employee_edit_deadline_hours': 'Thời hạn CN sửa sau nộp',
}


class ReportsGeneralSettingsForm(forms.ModelForm):
    class Meta:
        model = ReportsGeneralSettings
        fields = (
            'workers_may_edit_stage_time',
            'managers_may_edit_stage_time',
            'auto_submit_time',
            'default_declared_work_hours',
            'auto_approve_proxy_reports',
            'work_hours_min',
            'work_hours_max',
            'approve_deadline_hours',
            'auto_reject_deadline_hours',
            'employee_edit_deadline_hours',
            'unapprove_deadline_days',
        )
        widgets = {
            'workers_may_edit_stage_time': _CHECK,
            'managers_may_edit_stage_time': _CHECK,
            'auto_submit_time': _TIME,
            'default_declared_work_hours': _DEC,
            'auto_approve_proxy_reports': _CHECK,
            'work_hours_min': _DEC,
            'work_hours_max': _DEC,
            'approve_deadline_hours': _NUM,
            'unapprove_deadline_days': _NUM,
            'auto_reject_deadline_hours': _NUM,
            'employee_edit_deadline_hours': _NUM,
        }
        labels = _LABELS
        help_texts = {key: '' for key in _LABELS}

    def clean(self):
        cleaned = super().clean()
        approve_h = cleaned.get('approve_deadline_hours')
        reject_h = cleaned.get('auto_reject_deadline_hours')
        if approve_h is not None and reject_h is not None and reject_h < approve_h:
            self.add_error(
                'auto_reject_deadline_hours',
                'Thời hạn không duyệt phải lớn hơn hoặc bằng thời hạn duyệt.',
            )
        low = cleaned.get('work_hours_min')
        high = cleaned.get('work_hours_max')
        default_h = cleaned.get('default_declared_work_hours')
        if low is not None and high is not None and low >= high:
            self.add_error('work_hours_max', 'Giờ tối đa phải lớn hơn giờ tối thiểu.')
        if (
            default_h is not None
            and low is not None
            and high is not None
            and (default_h < low or default_h >= high)
        ):
            self.add_error(
                'default_declared_work_hours',
                'Giờ mặc định phải nằm trong khoảng giờ hợp lệ.',
            )
        return cleaned
