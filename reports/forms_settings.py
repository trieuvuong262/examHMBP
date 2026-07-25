"""Form thiết lập chung module Báo cáo."""

from __future__ import annotations

from django import forms

from reports.models import ReportsGeneralSettings

_CHECK = forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
_TIME = forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': 60})
_NUM = forms.NumberInput(attrs={'class': 'form-control', 'min': 1})


class ReportsGeneralSettingsForm(forms.ModelForm):
    class Meta:
        model = ReportsGeneralSettings
        fields = (
            'workers_may_edit_stage_time',
            'managers_may_edit_stage_time',
            'auto_submit_time',
            'approve_deadline_hours',
            'unapprove_deadline_days',
            'auto_reject_deadline_hours',
        )
        widgets = {
            'workers_may_edit_stage_time': _CHECK,
            'managers_may_edit_stage_time': _CHECK,
            'auto_submit_time': _TIME,
            'approve_deadline_hours': _NUM,
            'unapprove_deadline_days': _NUM,
            'auto_reject_deadline_hours': _NUM,
        }

    def clean(self):
        cleaned = super().clean()
        approve_h = cleaned.get('approve_deadline_hours')
        reject_h = cleaned.get('auto_reject_deadline_hours')
        if approve_h is not None and reject_h is not None and reject_h < approve_h:
            self.add_error(
                'auto_reject_deadline_hours',
                'Thời hạn không duyệt phải lớn hơn hoặc bằng thời hạn duyệt.',
            )
        return cleaned
