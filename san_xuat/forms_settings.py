"""Form thiết lập chung module Sản xuất."""

from __future__ import annotations

import re

from django import forms

from san_xuat.hub_models import SxGeneralSettings

_SELECT = forms.Select(attrs={'class': 'form-select'})
_CHECK = forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
_PREFIX = forms.TextInput(attrs={'class': 'form-control form-control-sm text-uppercase', 'maxlength': 16})

_PREFIX_FIELDS = (
    'prefix_mo',
    'prefix_ycx',
    'prefix_stat',
    'prefix_fg',
    'prefix_qc_req',
    'prefix_qc_sheet',
    'prefix_qc_alert',
    'prefix_wip_ho',
    'prefix_wip_ret',
    'prefix_disassembly',
    'prefix_npl_surplus',
    'prefix_packing',
    'prefix_subcontract',
    'prefix_work_assign',
    'prefix_plan_overall',
    'prefix_plan_npl',
    'prefix_plan_detail',
    'prefix_npl_pr',
    'prefix_po',
    'prefix_cost_std',
    'prefix_cost_order',
    'prefix_actual_cost',
    'prefix_ncr',
    'prefix_downtime',
)


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
            'gate_sku_on_stat',
            'gate_sku_on_packing',
            'auto_create_qc_from_stat',
            'auto_create_defect_alert',
            'default_defect_tolerance_pct',
            'default_sample_qty',
            'trace_min_timeline_events',
            'capacity_load_warn_pct',
            'capacity_load_danger_pct',
            'plan_capacity_mode',
            'plan_block_over_capacity',
            'plan_workdays',
            'npl_prep_days',
            'mo_late_alert_days',
            'list_default_date_range_days',
            'oee_shift_hours',
            'ycx_auto_reserve_stock',
            'require_kv_link_for_fg_done',
            'show_pending_ycx_banner',
            'shopfloor_auto_confirm_stat',
            'shopfloor_default_qty_good',
            *_PREFIX_FIELDS,
        )
        widgets = {
            'gate_release_before_issue': _SELECT,
            'gate_issue_before_stat': _SELECT,
            'gate_stat_before_fg': _SELECT,
            'gate_qc_pass_before_fg': _SELECT,
            'gate_open_qc_alert_before_fg': _SELECT,
            'gate_packing_before_done': _SELECT,
            'gate_sku_on_stat': _SELECT,
            'gate_sku_on_packing': _SELECT,
            'auto_create_qc_from_stat': _CHECK,
            'auto_create_defect_alert': _CHECK,
            'default_defect_tolerance_pct': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'default_sample_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 9999}),
            'trace_min_timeline_events': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 20}),
            'capacity_load_warn_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 200}),
            'capacity_load_danger_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 200}),
            'plan_capacity_mode': forms.Select(attrs={'class': 'form-select'}),
            'plan_workdays': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 7,
                'placeholder': '1111110',
            }),
            'npl_prep_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 120}),
            'mo_late_alert_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 60}),
            'list_default_date_range_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 90}),
            'oee_shift_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 24}),
            'ycx_auto_reserve_stock': _CHECK,
            'require_kv_link_for_fg_done': _CHECK,
            'show_pending_ycx_banner': _CHECK,
            'shopfloor_auto_confirm_stat': _CHECK,
            'shopfloor_default_qty_good': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}
            ),
            **{f: _PREFIX for f in _PREFIX_FIELDS},
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
        raw_days = (cleaned.get('plan_workdays') or '').strip()
        if raw_days:
            from san_xuat.services.work_calendar import normalize_workdays

            bits = ''.join(ch for ch in raw_days if ch in '01')
            if len(bits) != 7 or '1' not in bits:
                self.add_error(
                    'plan_workdays',
                    'Cần đúng 7 ký tự 0/1 (Thứ 2 → Chủ nhật) và có ít nhất một ngày làm việc.',
                )
            else:
                cleaned['plan_workdays'] = normalize_workdays(bits)
        for name in _PREFIX_FIELDS:
            raw = (cleaned.get(name) or '').strip().upper()
            raw = re.sub(r'[^A-Z0-9\-]', '', raw)
            if not raw:
                self.add_error(name, 'Prefix không được để trống.')
            else:
                cleaned[name] = raw[:16]
        return cleaned


class SxInterStepSettingsForm(forms.ModelForm):
    class Meta:
        model = SxGeneralSettings
        fields = ('plan_count_minutes', 'plan_transfer_minutes')
        labels = {
            'plan_count_minutes': 'Kiểm đếm mặc định',
            'plan_transfer_minutes': 'Vận chuyển mặc định',
        }
        help_texts = {
            'plan_count_minutes': 'Dùng khi chưa khai báo cặp bộ phận bên dưới. Gợi ý trên nút + bảng kế hoạch. 0 = không gợi ý.',
            'plan_transfer_minutes': 'Dùng khi chưa khai báo cặp bộ phận bên dưới. Gợi ý trên nút + bảng kế hoạch. 0 = không gợi ý.',
        }
        widgets = {
            'plan_count_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'plan_transfer_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }
