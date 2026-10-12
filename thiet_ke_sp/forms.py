from __future__ import annotations

from datetime import datetime, time

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from . import catalog, role_scopes
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


def role_queryset(role: str, current_id=None):
    if role == 'approver':
        return approver_queryset()
    scope = role_scopes.user_filter(role)
    if scope is None:
        return None
    if current_id:
        scope |= Q(pk=current_id)
    return active_users().filter(scope)


class RoleFieldsMixin:
    def _add_role_fields(self, current: dict | None = None):
        current = current or {}
        for role in DOSSIER_ROLE_FIELDS:
            field = user_field(ROLE_LABELS[role], queryset=role_queryset(role, current.get(role)))
            field.help_text = role_scopes.scope_label(role)
            self.fields[role] = field


class CatalogTypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.code} — {obj.name}'


class CatalogTypeSelect(forms.Select):
    """Mỗi option mang data-group để lọc Loại theo Nhóm đã chọn."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-group'] = catalog.group_code(instance.code)
        return option


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
        instance = self.instance
        group_choices = catalog.group_choices()
        if instance.product_group and instance.product_group not in dict(group_choices):
            group_choices.append((instance.product_group, catalog.group_label(instance.product_group)))
        self.fields['product_group'] = forms.ChoiceField(
            label='Nhóm sản phẩm', choices=[('', '— Chọn nhóm —'), *group_choices],
            widget=forms.Select(attrs=_SELECT),
        )
        self.fields['product_type'] = CatalogTypeChoiceField(
            label='Loại sản phẩm', queryset=catalog.type_queryset(include_pk=instance.product_type_id),
            empty_label='— Chọn loại —', widget=CatalogTypeSelect(attrs=_SELECT),
        )
        self._add_role_fields({role: getattr(instance, f'{role}_id') for role in DOSSIER_ROLE_FIELDS})
        if not instance.pk and user is not None and not self.is_bound:
            self.initial.setdefault('owner', user.pk)

    def clean(self):
        data = super().clean()
        group, ptype = data.get('product_group'), data.get('product_type')
        if group and ptype and catalog.group_code(ptype.code) != group:
            self.add_error('product_type', 'Loại sản phẩm không thuộc nhóm đã chọn.')
        return data


class RolesForm(RoleFieldsMixin, forms.Form):
    def __init__(self, *args, dossier: ProductDevelopment, **kwargs):
        initial = {role: getattr(dossier, f'{role}_id') for role in DOSSIER_ROLE_FIELDS}
        super().__init__(*args, initial=initial, **kwargs)
        self._add_role_fields(initial)
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
