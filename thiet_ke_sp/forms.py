from __future__ import annotations

from datetime import datetime, time

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from kho_san_pham.catalog_models import ProductType as CatalogType

from . import catalog
from . import permissions as perms
from .models import (
    DOSSIER_ROLE_FIELDS,
    DesignVersion,
    EvaluatorRole,
    POOL_ROLES,
    ProductDevelopment,
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
    'costing_user': 'Kế hoạch / Giá thành',
    'follower': 'Người theo dõi',
}


def _widget_sm(widget):
    """Ô nhập form hồ sơ dùng cỡ sm (38px) theo quy ước Sản xuất. Textarea không bị ép cao."""
    parts = (widget.attrs.get('class') or '').split()
    if 'form-control' in parts and 'form-control-sm' not in parts:
        parts.append('form-control-sm')
    if 'form-select' in parts and 'form-select-sm' not in parts:
        parts.append('form-select-sm')
    widget.attrs['class'] = ' '.join(parts)


def _as_pk(value):
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def role_pool_queryset(role: str, extra_ids=()):
    """Danh sách Thiết lập: mọi nhân sự đang hoạt động, không lọc phòng ban."""
    base = approver_queryset() if role == 'approver' else active_users()
    extra = [pk for pk in (_as_pk(item) for item in extra_ids) if pk]
    if not extra:
        return base
    return get_user_model().objects.filter(
        Q(pk__in=base.values('pk')) | Q(pk__in=extra),
    ).select_related('profile').order_by('profile__full_name', 'username')


def role_queryset(role: str, current_id=None, configured: dict | None = None, current_ids=()):
    """Người được chọn trên hồ sơ: danh sách đã cấu hình, cộng người đang giữ vai trò."""
    if configured is None:
        configured = sla.configured_role_ids()
    allowed = list(configured.get(role) or [])
    extras = list(current_ids or [])
    current_pk = _as_pk(current_id)
    if current_pk:
        extras.append(current_pk)
    for item in extras:
        pk = _as_pk(item)
        if pk and pk not in allowed:
            allowed.append(pk)
    if not allowed:
        return active_users().none()
    return active_users().filter(pk__in=allowed)


def follower_field(current_ids=()):
    configured = sla.configured_role_ids()
    field = UserMultipleChoiceField(
        queryset=role_queryset('follower', configured=configured, current_ids=current_ids),
        required=False,
        label=ROLE_LABELS['follower'],
        widget=forms.SelectMultiple(attrs={**_USER_SELECT, 'multiple': 'multiple'}),
    )
    if not configured.get('follower'):
        field.help_text = 'Chưa có người trong Thiết lập → Nhân sự phụ trách.'
    else:
        field.help_text = 'Không bắt buộc. Chỉ xem hồ sơ và trao đổi, không duyệt hay sửa.'
    return field


class UserMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return perms.display_name(obj)


class RoleFieldsMixin:
    def _add_role_fields(self, current: dict | None = None):
        current = current or {}
        configured = sla.configured_role_ids()
        for role in DOSSIER_ROLE_FIELDS:
            field = user_field(
                ROLE_LABELS[role],
                queryset=role_queryset(role, current.get(role), configured),
            )
            if not configured.get(role):
                field.help_text = 'Chưa có người trong Thiết lập → Nhân sự phụ trách.'
            self.fields[role] = field


NEW_GROUP = '__new__'


class _TypeSelect(forms.Select):
    """Mỗi option mang nhóm hàng để form lọc loại mã theo nhóm đang chọn."""

    def __init__(self, *args, groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.groups = groups or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        group = self.groups.get(str(option['value']))
        if group:
            option['attrs']['data-group'] = group
        return option


class DossierForm(RoleFieldsMixin, forms.ModelForm):
    new_group_code = forms.CharField(
        required=False, max_length=16, label='Mã nhóm mới',
        widget=forms.TextInput(attrs={**_INPUT, 'placeholder': 'VD: RUN', 'style': 'text-transform: uppercase'}),
    )
    new_group_name = forms.CharField(
        required=False, max_length=120, label='Tên nhóm mới',
        widget=forms.TextInput(attrs={**_INPUT, 'placeholder': 'VD: Đồ chạy bộ'}),
    )

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
            'reference_links': forms.TextInput(attrs=_INPUT),
            'description': _textarea(4),
        }

    def __init__(self, *args, user=None, lock_followers=False, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        group_choices = catalog.group_choices()
        if instance.product_group and instance.product_group not in dict(group_choices):
            group_choices.append((instance.product_group, catalog.group_label(instance.product_group)))
        self.fields['product_group'] = forms.ChoiceField(
            label='Nhóm sản phẩm',
            choices=[('', '— Chọn nhóm —'), *group_choices, (NEW_GROUP, '+ Thêm nhóm mới…')],
            widget=forms.Select(attrs=_SELECT),
        )
        type_qs = CatalogType.objects.filter(is_active=True)
        if instance.pk and instance.product_type_id:
            type_qs = CatalogType.objects.filter(Q(is_active=True) | Q(pk=instance.product_type_id))
        type_qs = type_qs.order_by('sort_order', 'code')
        self.fields['product_type'] = forms.ModelChoiceField(
            label='Loại mã (Style trong Thư viện)',
            queryset=type_qs,
            required=False,
            empty_label='— Chọn loại mã —',
            widget=_TypeSelect(
                attrs=_SELECT,
                groups={str(t.pk): catalog.group_code(t.code) for t in type_qs},
            ),
        )
        self.fields['product_type'].label_from_instance = lambda t: f'{t.code} — {t.name}'
        self.new_group = None
        current = {role: getattr(instance, f'{role}_id') for role in DOSSIER_ROLE_FIELDS}
        self._add_role_fields(current)
        self.follower_names = ''
        if lock_followers and instance.pk:
            names = [perms.display_name(person) for person in instance.followers.select_related('profile')]
            self.follower_names = ', '.join(name for name in names if name)
        else:
            current_followers = list(instance.followers.values_list('pk', flat=True)) if instance.pk else []
            self.fields['followers'] = follower_field(current_followers)
            if instance.pk:
                self.initial.setdefault('followers', current_followers)
        if not instance.pk and user is not None and not self.is_bound:
            allowed = set(sla.configured_role_ids().get('owner') or [])
            if not allowed or user.pk in allowed:
                self.initial.setdefault('owner', user.pk)
        for field in self.fields.values():
            _widget_sm(field.widget)

    def clean(self):
        data = super().clean()
        group = data.get('product_group')
        if group == NEW_GROUP:
            code = catalog.normalize_group_code(data.get('new_group_code'))
            name = (data.get('new_group_name') or '').strip()
            if not catalog.GROUP_CODE_RE.match(code):
                self.add_error('new_group_code', 'Mã nhóm 2–16 ký tự, chỉ gồm chữ không dấu và số (không dùng «-»).')
            elif catalog.group_exists(code):
                self.add_error('new_group_code', f'Nhóm {code} đã có — chọn trong danh sách.')
            if not name:
                self.add_error('new_group_name', 'Nhập tên nhóm mới.')
            data['product_type'] = None
            if 'product_type' in self._errors:
                del self._errors['product_type']
            if not self.errors:
                self.new_group = (code, name)
                data['product_group'] = code
            return data
        ptype = data.get('product_type')
        if not ptype:
            self.add_error('product_type', 'Chọn loại mã.')
        elif group and catalog.group_code(ptype.code) != catalog.normalize_group_code(group):
            self.add_error('product_type', 'Loại mã không thuộc nhóm đã chọn.')
        return data

    def create_new_group(self) -> None:
        """Gọi sau is_valid(): thêm nhóm mới vào danh mục Loại mã nếu người dùng chọn «Thêm nhóm mới»."""
        if not self.new_group:
            return
        code, name = self.new_group
        catalog.create_group(code, name)
        self.cleaned_data['product_type'] = CatalogType.objects.get(code=code)


class RolesForm(RoleFieldsMixin, forms.Form):
    def __init__(self, *args, dossier: ProductDevelopment, **kwargs):
        initial = {role: getattr(dossier, f'{role}_id') for role in DOSSIER_ROLE_FIELDS}
        super().__init__(*args, initial=initial, **kwargs)
        self._add_role_fields(initial)
        self.fields['owner'].required = True
        current_followers = list(dossier.followers.values_list('pk', flat=True))
        self.fields['followers'] = follower_field(current_followers)
        self.initial['followers'] = current_followers


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


class RolePoolForm(forms.Form):
    """Danh sách user được phép chọn cho từng vai trò khi tạo / sửa hồ sơ."""

    def __init__(self, *args, setting, **kwargs):
        self.setting = setting
        current = sla.configured_role_ids(setting)
        super().__init__(*args, initial=current, **kwargs)
        multi = {'class': 'form-select jp-tksp-user-select', 'multiple': 'multiple'}
        for role in POOL_ROLES:
            self.fields[role] = UserMultipleChoiceField(
                queryset=role_pool_queryset(role, current.get(role) or []),
                required=False, label=ROLE_LABELS[role],
                widget=forms.SelectMultiple(attrs=multi),
            )
            if role == 'approver':
                self.fields[role].help_text = 'Mọi nhân sự có quyền duyệt hồ sơ, không lọc phòng ban.'
            elif role == 'follower':
                self.fields[role].help_text = 'Chọn nhiều người trên mỗi hồ sơ. Họ chỉ xem và trao đổi.'

    def save(self, user):
        self.setting.default_roles = {
            role: [person.pk for person in (self.cleaned_data.get(role) or [])]
            for role in POOL_ROLES
        }
        self.setting.updated_by = user
        self.setting.save()
        return self.setting


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

    def sla_fields(self):
        return [self[f'sla_{step}'] for step, _l, _d in sla.SLA_STEPS]

    def save(self, user):
        data = self.cleaned_data
        self.setting.due_hour = data['due_hour']
        self.setting.sla_days = {step: data[f'sla_{step}'] for step, _l, _d in sla.SLA_STEPS}
        self.setting.updated_by = user
        self.setting.save()
        return self.setting
