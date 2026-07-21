"""Form thiết lập chung module Sản xuất."""

from __future__ import annotations

from django import forms

from san_xuat.hub_models import SxGeneralSettings

_SELECT = forms.Select(attrs={'class': 'form-select'})
_CHECK = forms.CheckboxInput(attrs={'class': 'form-check-input'})
_NUM = forms.NumberInput(attrs={'class': 'form-control', 'min': 0})


class SxGeneralSettingsForm(forms.ModelForm):
    class Meta:
        model = SxGeneralSettings
        fields = (
            'gate_release_before_issue',
            'gate_issue_before_stat',
            'gate_stat_before_fg',
            'gate_qc_pass_before_fg',
            'gate_open_qc_alert_before_fg',
            'gate_packing_before_done',
            'auto_create_qc_from_stat',
            'auto_create_defect_alert',
            'default_defect_tolerance_pct',
            'default_sample_qty',
            'trace_min_timeline_events',
            'capacity_load_warn_pct',
            'capacity_load_danger_pct',
            'list_default_date_range_days',
            'ycx_auto_reserve_stock',
            'require_kv_link_for_fg_done',
            'shopfloor_auto_confirm_stat',
            'shopfloor_default_qty_good',
        )
        widgets = {
            'gate_release_before_issue': _SELECT,
            'gate_issue_before_stat': _SELECT,
            'gate_stat_before_fg': _SELECT,
            'gate_qc_pass_before_fg': _SELECT,
            'gate_open_qc_alert_before_fg': _SELECT,
            'gate_packing_before_done': _SELECT,
            'auto_create_qc_from_stat': _CHECK,
            'auto_create_defect_alert': _CHECK,
            'default_defect_tolerance_pct': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'default_sample_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 9999}),
            'trace_min_timeline_events': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 20}),
            'capacity_load_warn_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 200}),
            'capacity_load_danger_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 200}),
            'list_default_date_range_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 90}),
            'ycx_auto_reserve_stock': _CHECK,
            'require_kv_link_for_fg_done': _CHECK,
            'shopfloor_auto_confirm_stat': _CHECK,
            'shopfloor_default_qty_good': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        warn = cleaned.get('capacity_load_warn_pct') or 80
        danger = cleaned.get('capacity_load_danger_pct') or 100
        if warn > danger:
            self.add_error(
                'capacity_load_warn_pct',
                'Ngưỡng cảnh báo không được lớn hơn ngưỡng quá tải.',
            )
        return cleaned
