from __future__ import annotations

from datetime import datetime, time

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from . import permissions as perms
from .models import (
    DOSSIER_ROLE_FIELDS,
    DesignVersion,
    EvaluatorRole,
    ProductDevelopment,
    ReceivingDepartment,
    SampleEvaluation,
    SampleVersion,
    TechnicalPack,
)
from .services import sla

_INPUT = {'class': 'form-control'}
_SELECT = {'class': 'form-select'}
_USER_SELECT = {'class': 'form-select jp-tksp-user-select'}
_DATE = {'class': 'form-control jp-date-vn', 'type': 'date'}
_MONEY = {'class': 'form-control text-end', 'inputmode': 'numeric', 'min': '0', 'step': '1'}


def _textarea(rows: int = 3) -> forms.Textarea:
    return forms.Textarea(attrs={'class': 'form-control', 'rows': rows})


def active_users():
    return get_user_model().objects.filter(is_active=True).select_related('profile').order_by(
        'profile__full_name', 'username',
    )


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return perms.display_name(obj)


def user_field(label: str, *, required: bool = False, queryset=None) -> UserChoiceField:
    return UserChoiceField(
        queryset=queryset if queryset is not None else active_users(),
        required=required, label=label, empty_label='— Chọn —',
        widget=forms.Select(attrs=_USER_SELECT),
    )


def approver_queryset():
    ids = [u.pk for u in perms.approver_candidates()]
    return active_users().filter(pk__in=ids)


def parse_due(raw: str):
    """«YYYY-MM-DDTHH:MM» hoặc «YYYY-MM-DD» (giờ chốt hạn mặc định) → datetime aware; rỗng → None."""
    raw = (raw or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            value = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt == '%Y-%m-%d':
            value = datetime.combine(value.date(), time(sla.get_settings().due_hour or sla.DEFAULT_DUE_HOUR, 0))
        return timezone.make_aware(value)
    return None


ROLE_LABELS = {
    'owner': 'Người phụ trách chính',
    'approver': 'Người duyệt',
    'designer': 'Thiết kế / R&D',
    'technician': 'Kỹ thuật / Tài liệu kỹ thuật',
    'sample_maker': 'May mẫu',
    'qa_user': 'QA/QC',
    'costing_user': 'Kế hoạch / Giá thành',
}


class RoleFieldsMixin:
    def _add_role_fields(self):
        for role in DOSSIER_ROLE_FIELDS:
            qs = approver_queryset() if role == 'approver' else None
            self.fields[role] = user_field(ROLE_LABELS[role], queryset=qs)


class DossierForm(RoleFieldsMixin, forms.ModelForm):
    class Meta:
        model = ProductDevelopment
        fields = [
            'name', 'product_group', 'product_type', 'collection', 'priority', 'launch_date',
            'target_customer', 'usage_need', 'market_need', 'expected_qty',
            'target_wholesale_price', 'target_retail_price', 'target_cost',
            'reference_links', 'description',
            *DOSSIER_ROLE_FIELDS,
        ]
        widgets = {
            'name': forms.TextInput(attrs=_INPUT),
            'product_group': forms.Select(attrs=_SELECT),
            'product_type': forms.Select(attrs=_SELECT),
            'collection': forms.TextInput(attrs=_INPUT),
            'priority': forms.Select(attrs=_SELECT),
            'launch_date': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'target_customer': forms.TextInput(attrs=_INPUT),
            'usage_need': _textarea(2),
            'market_need': _textarea(2),
            'expected_qty': forms.NumberInput(attrs={**_MONEY}),
            'target_wholesale_price': forms.NumberInput(attrs=_MONEY),
            'target_retail_price': forms.NumberInput(attrs=_MONEY),
            'target_cost': forms.NumberInput(attrs=_MONEY),
            'reference_links': _textarea(2),
            'description': _textarea(4),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_role_fields()
        if not self.instance.pk and user is not None and not self.is_bound:
            self.initial.setdefault('owner', user.pk)


class RolesForm(RoleFieldsMixin, forms.Form):
    def __init__(self, *args, dossier: ProductDevelopment, **kwargs):
        initial = {role: getattr(dossier, f'{role}_id') for role in DOSSIER_ROLE_FIELDS}
        super().__init__(*args, initial=initial, **kwargs)
        self._add_role_fields()
        self.fields['owner'].required = True


class DesignVersionForm(forms.ModelForm):
    class Meta:
        model = DesignVersion
        fields = ['style_description', 'pattern_description', 'logo_placement', 'materials', 'highlights', 'change_note']
        widgets = {f: _textarea(2) for f in fields}


class ColorwayForm(forms.Form):
    name = forms.CharField(max_length=120, label='Tên phối màu', widget=forms.TextInput(attrs=_INPUT))
    color_codes = forms.CharField(max_length=255, label='Mã màu', widget=forms.TextInput(attrs=_INPUT))
    note = forms.CharField(max_length=255, required=False, label='Ghi chú', widget=forms.TextInput(attrs=_INPUT))


class SampleForm(forms.ModelForm):
    maker = user_field('Người làm mẫu')

    class Meta:
        model = SampleVersion
        fields = ['maker', 'assigned_date', 'completed_date', 'progress_note', 'change_note']
        widgets = {
            'assigned_date': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'completed_date': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'progress_note': _textarea(2),
            'change_note': _textarea(2),
        }


class TechPackForm(forms.ModelForm):
    class Meta:
        model = TechnicalPack
        fields = ['size_spec', 'cutting_req', 'sewing_req', 'decoration_req', 'finishing_req', 'packing_req']
        widgets = {
            'size_spec': _textarea(4),
            'cutting_req': _textarea(2),
            'sewing_req': _textarea(2),
            'decoration_req': _textarea(2),
            'finishing_req': _textarea(2),
            'packing_req': _textarea(2),
        }


class EvaluationForm(forms.Form):
    role = forms.ChoiceField(label='Vai trò đánh giá', widget=forms.Select(attrs=_SELECT))
    result = forms.ChoiceField(
        label='Kết luận', choices=SampleEvaluation.RESULT_CHOICES, widget=forms.Select(attrs=_SELECT),
    )
    conclusion = forms.CharField(required=False, label='Nhận xét chung', widget=_textarea(2))
    defects = forms.CharField(required=False, label='Lỗi / nội dung phải chỉnh', widget=_textarea(2))
    fix_owner = user_field('Người chịu trách nhiệm sửa')
    fix_due = forms.DateField(required=False, label='Hạn sửa', widget=forms.DateInput(attrs=_DATE))

    def __init__(self, *args, allowed_roles: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = [(r, EvaluatorRole(r).label) for r in allowed_roles]


class CostingForm(forms.ModelForm):
    class Meta:
        model = ProductDevelopment
        fields = ['estimated_cost', 'post_sample_cost', 'proposed_wholesale_price', 'proposed_retail_price', 'cost_note']
        widgets = {
            'estimated_cost': forms.NumberInput(attrs=_MONEY),
            'post_sample_cost': forms.NumberInput(attrs=_MONEY),
            'proposed_wholesale_price': forms.NumberInput(attrs=_MONEY),
            'proposed_retail_price': forms.NumberInput(attrs=_MONEY),
            'cost_note': _textarea(2),
        }


class HandoverForm(forms.Form):
    note = forms.CharField(required=False, label='Nội dung bàn giao', widget=_textarea(3))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        defaults = sla.default_receiver_ids()
        for dept in ReceivingDepartment:
            self.fields[f'receiver_{dept.value}'] = user_field(f'Người nhận — {dept.label}', required=True)
            if not self.is_bound and defaults.get(dept.value):
                self.initial[f'receiver_{dept.value}'] = defaults[dept.value]

    def receivers(self) -> dict:
        return {dept: self.cleaned_data.get(f'receiver_{dept}') for dept in ReceivingDepartment.values}

    def receiver_fields(self):
        return [self[f'receiver_{dept}'] for dept in ReceivingDepartment.values]


class SettingsForm(forms.Form):
    due_hour = forms.IntegerField(
        min_value=0, max_value=23, label='Giờ chốt hạn trong ngày',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 23}),
    )

    def __init__(self, *args, setting, **kwargs):
        super().__init__(*args, **kwargs)
        self.setting = setting
        self.initial['due_hour'] = setting.due_hour
        for step, label, _days in sla.SLA_STEPS:
            self.fields[f'sla_{step}'] = forms.IntegerField(
                min_value=0, max_value=90, label=label,
                widget=forms.NumberInput(attrs={'class': 'form-control text-end', 'min': 0, 'max': 90}),
            )
            self.initial[f'sla_{step}'] = sla.sla_days(step, setting)
        defaults = sla.default_receiver_ids(setting)
        for dept in ReceivingDepartment:
            self.fields[f'receiver_{dept.value}'] = user_field(f'Người nhận mặc định — {dept.label}')
            self.initial[f'receiver_{dept.value}'] = defaults.get(dept.value)

    def sla_fields(self):
        return [self[f'sla_{step}'] for step, _l, _d in sla.SLA_STEPS]

    def receiver_fields(self):
        return [self[f'receiver_{dept}'] for dept in ReceivingDepartment.values]

    def save(self, user):
        data = self.cleaned_data
        self.setting.due_hour = data['due_hour']
        self.setting.sla_days = {step: data[f'sla_{step}'] for step, _l, _d in sla.SLA_STEPS}
        self.setting.default_receivers = {
            dept: (data[f'receiver_{dept}'].pk if data.get(f'receiver_{dept}') else None)
            for dept in ReceivingDepartment.values
        }
        self.setting.updated_by = user
        self.setting.save()
        return self.setting
