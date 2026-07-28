"""Forms thiết lập mã: loại / Style / map KV."""

from django import forms
from django.utils import timezone

from kho_san_pham.catalog_models import ProductStyle, ProductType, ProductTypeKvMap
from kho_san_pham.choices import KV_MAP_MATCH_CHOICES, KV_MAP_MATCH_EXACT
from kho_san_pham.services.code_structure import (
    CodeStructureError,
    create_manual_style,
)

FORM_CONTROL = {'class': 'form-control form-control-sm'}
FORM_SELECT = {'class': 'form-select form-select-sm'}


class ProductTypeForm(forms.ModelForm):
    class Meta:
        model = ProductType
        fields = ['code', 'name', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: TEE, SET-SC'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'sort_order': forms.NumberInput(attrs={**FORM_CONTROL, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        return (self.cleaned_data.get('code') or '').strip().upper()


class ProductStyleCreateForm(forms.Form):
    product_type = forms.ModelChoiceField(
        queryset=ProductType.objects.none(),
        label='Loại',
        widget=forms.Select(attrs=FORM_SELECT),
    )
    name = forms.CharField(
        required=False,
        label='Tên / mô tả',
        widget=forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: Áo thun thể thao mẫu số 1'}),
    )
    year = forms.IntegerField(
        required=False,
        label='Năm',
        widget=forms.NumberInput(attrs={**FORM_CONTROL, 'min': 2000, 'max': 2100}),
    )
    sequence = forms.IntegerField(
        required=False,
        label='STT (để trống = tự tăng)',
        widget=forms.NumberInput(attrs={**FORM_CONTROL, 'min': 1, 'max': 9999}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_type'].queryset = ProductType.objects.filter(is_active=True).order_by(
            'sort_order', 'code',
        )
        if not self.is_bound:
            self.fields['year'].initial = timezone.now().year

    def save(self, *, user=None) -> ProductStyle:
        try:
            return create_manual_style(
                product_type=self.cleaned_data['product_type'],
                name=self.cleaned_data.get('name') or '',
                year=self.cleaned_data.get('year'),
                sequence=self.cleaned_data.get('sequence'),
                user=user,
            )
        except CodeStructureError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ProductStyleEditForm(forms.ModelForm):
    class Meta:
        model = ProductStyle
        fields = ['name', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductTypeKvMapForm(forms.ModelForm):
    class Meta:
        model = ProductTypeKvMap
        fields = ['match_value', 'match_mode', 'product_type', 'priority', 'is_active', 'notes']
        widgets = {
            'match_value': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': 'VD: POLO hoặc BÓNG ĐÁ',
            }),
            'match_mode': forms.Select(attrs=FORM_SELECT, choices=KV_MAP_MATCH_CHOICES),
            'product_type': forms.Select(attrs=FORM_SELECT),
            'priority': forms.NumberInput(attrs={**FORM_CONTROL, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_type'].queryset = ProductType.objects.filter(is_active=True).order_by(
            'sort_order', 'code',
        )
        self.fields['match_mode'].initial = KV_MAP_MATCH_EXACT
        self.fields['notes'].required = False

    def clean_match_value(self):
        return (self.cleaned_data.get('match_value') or '').strip()
