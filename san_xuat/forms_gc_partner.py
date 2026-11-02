"""Form quản lý đối tác gia công (GĐ1)."""

from __future__ import annotations

from django import forms

from san_xuat.partner_models import GcPartner, GcPartnerAccount, GcPriceRule

_INPUT = {'class': 'form-control form-control-sm'}
_SELECT = {'class': 'form-select form-select-sm'}
_DATE = {'class': 'form-control form-control-sm', 'type': 'date'}


def _team_choices():
    from san_xuat.services.progress_template import TEAM_SLUGS

    return [(slug, label) for slug, _g, _m, label in TEAM_SLUGS]


class GcPartnerForm(forms.ModelForm):
    team_slugs = forms.MultipleChoiceField(
        required=False,
        label='Công đoạn nhận GC',
        choices=[],
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = GcPartner
        fields = [
            'code', 'name', 'tax_code', 'contact_name', 'phone', 'email', 'address',
            'team_slugs', 'work_center', 'capacity_per_day', 'payment_terms', 'notes', 'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs=_INPUT),
            'name': forms.TextInput(attrs=_INPUT),
            'tax_code': forms.TextInput(attrs=_INPUT),
            'contact_name': forms.TextInput(attrs=_INPUT),
            'phone': forms.TextInput(attrs=_INPUT),
            'email': forms.EmailInput(attrs=_INPUT),
            'address': forms.TextInput(attrs=_INPUT),
            'work_center': forms.Select(attrs=_SELECT),
            'capacity_per_day': forms.NumberInput(attrs={**_INPUT, 'step': 'any', 'min': '0'}),
            'payment_terms': forms.TextInput(attrs=_INPUT),
            'notes': forms.Textarea(attrs={**_INPUT, 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxWorkCenter

        super().__init__(*args, **kwargs)
        self.fields['team_slugs'].choices = _team_choices()
        self.fields['work_center'].queryset = SxWorkCenter.objects.filter(
            is_demo=False, is_subcontract=True,
        ).order_by('name')
        self.fields['work_center'].required = False
        self.fields['work_center'].empty_label = '— Không gắn —'
        self.fields['work_center'].help_text = 'Tổ đánh dấu "thuê gia công" trên danh mục năng lực (nếu có).'

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if not code:
            raise forms.ValidationError('Nhập mã đối tác.')
        return code


class GcPartnerAccountForm(forms.Form):
    username = forms.CharField(
        max_length=60, label='Tên đăng nhập',
        widget=forms.TextInput(attrs={**_INPUT, 'autocomplete': 'off'}),
    )
    full_name = forms.CharField(max_length=120, required=False, label='Họ tên', widget=forms.TextInput(attrs=_INPUT))
    phone = forms.CharField(max_length=30, required=False, label='Điện thoại', widget=forms.TextInput(attrs=_INPUT))
    role = forms.ChoiceField(
        choices=GcPartnerAccount.ROLE_CHOICES, label='Vai trò', widget=forms.Select(attrs=_SELECT),
    )
    password = forms.CharField(
        required=False, min_length=8, label='Mật khẩu (trống = tự sinh)',
        widget=forms.TextInput(attrs={**_INPUT, 'autocomplete': 'new-password'}),
    )


class GcPriceRuleForm(forms.ModelForm):
    team_slug = forms.ChoiceField(label='Công đoạn', choices=[], widget=forms.Select(attrs=_SELECT))

    class Meta:
        model = GcPriceRule
        fields = ['team_slug', 'product_code', 'product_name', 'unit_price', 'valid_from', 'valid_to', 'notes']
        widgets = {
            'product_code': forms.TextInput(attrs={**_INPUT, 'placeholder': 'Trống = giá chung công đoạn'}),
            'product_name': forms.TextInput(attrs=_INPUT),
            'unit_price': forms.NumberInput(attrs={**_INPUT, 'step': 'any', 'min': '0'}),
            'valid_from': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'valid_to': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'notes': forms.TextInput(attrs=_INPUT),
        }

    def __init__(self, *args, partner: GcPartner | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = _team_choices()
        if partner is not None and partner.team_slugs:
            allowed = set(partner.team_slugs)
            choices = [c for c in choices if c[0] in allowed] or choices
        self.fields['team_slug'].choices = choices

    def clean_product_code(self):
        code = (self.cleaned_data.get('product_code') or '').strip()
        if not code:
            return ''
        from san_xuat.services.products import resolve_product_ref

        ref = resolve_product_ref(code)
        if not ref:
            raise forms.ValidationError(f'Mã {code} không có trong kho sản phẩm.')
        self._ref_name = ref.name
        return ref.code

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('product_code') and not (cleaned.get('product_name') or '').strip():
            cleaned['product_name'] = getattr(self, '_ref_name', '')
        start, end = cleaned.get('valid_from'), cleaned.get('valid_to')
        if start and end and end < start:
            self.add_error('valid_to', 'Ngày kết thúc phải sau ngày bắt đầu.')
        return cleaned
