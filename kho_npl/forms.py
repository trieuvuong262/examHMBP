from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from kho_npl.models import (
    Material,
    MaterialCategory,
    StockAdjustment,
    StockIssue,
    StockIssueLine,
    StockReceipt,
    StockReceiptLine,
    Stocktake,
    StocktakeLine,
    Supplier,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.adjustments import balance_qty

User = get_user_model()

FORM_CONTROL = {'class': 'form-control'}
FORM_SELECT = {'class': 'form-select'}
FORM_TEXTAREA = {'class': 'form-control', 'rows': 3}


def _employed_users_qs():
    return (
        User.objects.filter(profile__is_employed=True)
        .select_related('profile')
        .order_by('profile__full_name', 'username')
    )


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'code',
            'name',
            'category',
            'color',
            'specification',
            'unit',
            'supplier',
            'min_stock',
            'image',
            'notes',
            'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: VAI-001'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'category': forms.Select(attrs=FORM_SELECT),
            'color': forms.TextInput(attrs=FORM_CONTROL),
            'specification': forms.TextInput(attrs=FORM_CONTROL),
            'unit': forms.Select(attrs=FORM_SELECT),
            'supplier': forms.Select(attrs=FORM_SELECT),
            'min_stock': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = MaterialCategory.objects.filter(is_active=True)
        self.fields['unit'].queryset = Unit.objects.filter(is_active=True)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].required = False
        self.fields['image'].required = False
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if not code:
            raise ValidationError('Mã NPL không được để trống.')
        qs = Material.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Mã NPL đã tồn tại.')
        return code


class StockReceiptForm(forms.ModelForm):
    class Meta:
        model = StockReceipt
        fields = [
            'receipt_date',
            'supplier',
            'po_number',
            'received_by',
            'checked_by',
            'notes',
        ]
        widgets = {
            'receipt_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'supplier': forms.Select(attrs=FORM_SELECT),
            'po_number': forms.TextInput(attrs=FORM_CONTROL),
            'received_by': forms.Select(attrs=FORM_SELECT),
            'checked_by': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].required = False
        self.fields['received_by'].queryset = _employed_users_qs()
        self.fields['checked_by'].queryset = _employed_users_qs()
        self.fields['received_by'].required = False
        self.fields['checked_by'].required = False
        if not self.instance.pk:
            self.initial.setdefault('receipt_date', timezone.localdate())


class StockReceiptLineForm(forms.ModelForm):
    class Meta:
        model = StockReceiptLine
        fields = ['material', 'ordered_qty', 'received_qty', 'location', 'notes']
        widgets = {
            'material': forms.Select(attrs=FORM_SELECT),
            'ordered_qty': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'received_qty': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'location': forms.Select(attrs=FORM_SELECT),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True).select_related('unit')
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True)
        self.fields['ordered_qty'].required = False
        self.fields['notes'].required = False
        default_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)


class BaseStockReceiptLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_lines = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            material = form.cleaned_data.get('material')
            if not material:
                continue
            active_lines.append(form.cleaned_data)
        if not active_lines:
            raise ValidationError('Phiếu nhập cần ít nhất một dòng nguyên phụ liệu.')
        for line in active_lines:
            qty = line.get('received_qty')
            if qty is None or qty <= 0:
                raise ValidationError('Số lượng nhập phải lớn hơn 0 cho mỗi dòng NPL.')


StockReceiptLineFormSet = inlineformset_factory(
    StockReceipt,
    StockReceiptLine,
    form=StockReceiptLineForm,
    formset=BaseStockReceiptLineFormSet,
    extra=2,
    can_delete=True,
)


class StockIssueForm(forms.ModelForm):
    class Meta:
        model = StockIssue
        fields = [
            'issue_date',
            'issue_type',
            'production_order',
            'product_code',
            'recipient_department',
            'recipient_name',
            'issued_by',
            'notes',
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'issue_type': forms.Select(attrs=FORM_SELECT),
            'production_order': forms.TextInput(attrs=FORM_CONTROL),
            'product_code': forms.TextInput(attrs=FORM_CONTROL),
            'recipient_department': forms.TextInput(attrs=FORM_CONTROL),
            'recipient_name': forms.TextInput(attrs=FORM_CONTROL),
            'issued_by': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['issued_by'].queryset = _employed_users_qs()
        self.fields['issued_by'].required = False
        self.fields['production_order'].required = False
        self.fields['product_code'].required = False
        self.fields['recipient_department'].required = False
        self.fields['recipient_name'].required = False
        if not self.instance.pk:
            self.initial.setdefault('issue_date', timezone.localdate())


class StockIssueLineForm(forms.ModelForm):
    class Meta:
        model = StockIssueLine
        fields = ['material', 'quantity', 'location', 'notes']
        widgets = {
            'material': forms.Select(attrs=FORM_SELECT),
            'quantity': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0.001'}),
            'location': forms.Select(attrs=FORM_SELECT),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True).select_related('unit')
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True)
        self.fields['notes'].required = False
        default_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)


class BaseStockIssueLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_lines = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            material = form.cleaned_data.get('material')
            if not material:
                continue
            active_lines.append(form.cleaned_data)
        if not active_lines:
            raise ValidationError('Phiếu xuất cần ít nhất một dòng nguyên phụ liệu.')
        for line in active_lines:
            qty = line.get('quantity')
            if qty is None or qty <= 0:
                raise ValidationError('Số lượng xuất phải lớn hơn 0 cho mỗi dòng NPL.')


StockIssueLineFormSet = inlineformset_factory(
    StockIssue,
    StockIssueLine,
    form=StockIssueLineForm,
    formset=BaseStockIssueLineFormSet,
    extra=2,
    can_delete=True,
)


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['adjust_date', 'material', 'location', 'actual_qty', 'reason']
        widgets = {
            'adjust_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'material': forms.Select(attrs=FORM_SELECT),
            'location': forms.Select(attrs=FORM_SELECT),
            'actual_qty': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'reason': forms.Textarea(attrs=FORM_TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True)
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True)
        if not self.instance.pk:
            self.initial.setdefault('adjust_date', timezone.localdate())

    def clean(self):
        cleaned = super().clean()
        material = cleaned.get('material')
        location = cleaned.get('location')
        if material and location:
            cleaned['system_qty'] = balance_qty(material, location)
        return cleaned

    def save(self, commit=True):
        adjustment = super().save(commit=False)
        adjustment.system_qty = self.cleaned_data.get('system_qty', Decimal('0'))
        if commit:
            adjustment.save()
        return adjustment


class StocktakeForm(forms.ModelForm):
    class Meta:
        model = Stocktake
        fields = ['name', 'stocktake_date', 'notes']
        widgets = {
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'stocktake_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        if not self.instance.pk:
            self.initial.setdefault('stocktake_date', timezone.localdate())


class StocktakeLineForm(forms.ModelForm):
    class Meta:
        model = StocktakeLine
        fields = ['actual_qty', 'notes']
        widgets = {
            'actual_qty': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


class BaseStocktakeLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return


StocktakeLineFormSet = inlineformset_factory(
    Stocktake,
    StocktakeLine,
    form=StocktakeLineForm,
    formset=BaseStocktakeLineFormSet,
    extra=0,
    can_delete=False,
)


def _clean_unique_code(model, field_name, value, instance):
    value = (value or '').strip()
    if not value:
        raise ValidationError('Mã không được để trống.')
    qs = model.objects.filter(**{f'{field_name}__iexact': value})
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise ValidationError('Mã đã tồn tại.')
    return value


class MaterialCategoryForm(forms.ModelForm):
    class Meta:
        model = MaterialCategory
        fields = ['code', 'name', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'vai-chinh'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'sort_order': forms.NumberInput(attrs={**FORM_CONTROL, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower()
        return _clean_unique_code(MaterialCategory, 'code', code, self.instance)


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['code', 'name', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs=FORM_CONTROL),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower()
        return _clean_unique_code(Unit, 'code', code, self.instance)


class WarehouseLocationForm(forms.ModelForm):
    class Meta:
        model = WarehouseLocation
        fields = ['code', 'name', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'MAIN'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        return _clean_unique_code(WarehouseLocation, 'code', code, self.instance)


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['code', 'name', 'phone', 'notes', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs=FORM_CONTROL),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'phone': forms.TextInput(attrs=FORM_CONTROL),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].required = False
        self.fields['notes'].required = False
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        return _clean_unique_code(Supplier, 'code', code, self.instance)
