from django import forms

from kho_san_pham.choices import (
    PRODUCT_TYPE_CHOICES,
    PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_THANH_PHAM,
)
from kho_san_pham.models import Product

FORM_CONTROL = {'class': 'form-control form-control-sm'}
FORM_SELECT = {'class': 'form-select form-select-sm'}
FORM_TEXTAREA = {'class': 'form-control form-control-sm', 'rows': 3}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'product_type',
            'code',
            'accounting_code',
            'kiotviet_code',
            'name',
            'full_name',
            'bar_code',
            'unit',
            'category_name',
            'base_price',
            'image',
            'description',
            'notes',
            'is_active',
        ]
        widgets = {
            'product_type': forms.Select(attrs=FORM_SELECT),
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Mã sản phẩm'}),
            'accounting_code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Mã kế toán'}),
            'kiotviet_code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Mã trên KiotViet'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'full_name': forms.TextInput(attrs=FORM_CONTROL),
            'bar_code': forms.TextInput(attrs=FORM_CONTROL),
            'unit': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: Cái, Bộ…'}),
            'category_name': forms.TextInput(attrs=FORM_CONTROL),
            'base_price': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '1', 'min': '0'}),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control form-control-sm',
                'accept': 'image/*,.jpg,.jpeg,.png,.gif,.webp',
            }),
            'description': forms.Textarea(attrs=FORM_TEXTAREA),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_type'].choices = PRODUCT_TYPE_CHOICES
        self.fields['accounting_code'].required = False
        self.fields['kiotviet_code'].required = False
        self.fields['full_name'].required = False
        self.fields['bar_code'].required = False
        self.fields['unit'].required = False
        self.fields['category_name'].required = False
        self.fields['base_price'].required = False
        self.fields['image'].required = False
        self.fields['description'].required = False
        self.fields['notes'].required = False
        self.fields['is_active'].required = False

        instance = self.instance
        kv_locked = bool(instance and instance.pk and instance.is_kv_synced)
        if kv_locked:
            # Thành phẩm sync KV: khóa field nguồn KV; vẫn sửa 3 mã nghiệp vụ + ghi chú
            for name in (
                'product_type',
                'name',
                'full_name',
                'bar_code',
                'unit',
                'category_name',
                'base_price',
                'kiotviet_code',
            ):
                self.fields[name].disabled = True
                self.fields[name].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Nhập mã sản phẩm.')
        qs = Product.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Mã sản phẩm đã tồn tại.')
        return code

    def clean_accounting_code(self):
        value = (self.cleaned_data.get('accounting_code') or '').strip()
        if not value:
            return ''
        qs = Product.objects.filter(accounting_code__iexact=value).exclude(accounting_code='')
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Mã kế toán đã tồn tại.')
        return value

    def clean_kiotviet_code(self):
        if self.fields['kiotviet_code'].disabled:
            return self.instance.kiotviet_code
        return (self.cleaned_data.get('kiotviet_code') or '').strip()

    def clean_product_type(self):
        if self.fields['product_type'].disabled:
            return self.instance.product_type
        value = self.cleaned_data.get('product_type') or PRODUCT_TYPE_HANG_HOA
        if value not in {PRODUCT_TYPE_THANH_PHAM, PRODUCT_TYPE_HANG_HOA}:
            raise forms.ValidationError('Loại sản phẩm không hợp lệ.')
        return value

    def clean(self):
        cleaned = super().clean()
        if self.fields['name'].disabled:
            cleaned['name'] = self.instance.name
            cleaned['full_name'] = self.instance.full_name
            cleaned['bar_code'] = self.instance.bar_code
            cleaned['unit'] = self.instance.unit
            cleaned['category_name'] = self.instance.category_name
            cleaned['base_price'] = self.instance.base_price
            cleaned['product_type'] = self.instance.product_type
            cleaned['kiotviet_code'] = self.instance.kiotviet_code
        return cleaned
