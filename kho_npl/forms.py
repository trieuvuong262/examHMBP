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
    StockAdjustmentLine,
    StockDisposal,
    StockDisposalLine,
    StockIssue,
    StockIssueLine,
    StockReceipt,
    StockReceiptLine,
    Stocktake,
    StocktakeLine,
    StockTransfer,
    StockTransferLine,
    Supplier,
    Unit,
    WarehouseLocation,
)
from kho_npl.doc_attachment import DOC_ATTACHMENT_ACCEPT, validate_doc_attachment
from kho_npl.services.scrap_warehouse import source_locations_qs
from kho_npl.services.adjustments import balance_qty

User = get_user_model()

FORM_CONTROL = {'class': 'form-control'}
FORM_SELECT = {'class': 'form-select'}
FORM_TEXTAREA = {'class': 'form-control', 'rows': 3}
FORM_ATTACHMENT = forms.ClearableFileInput(attrs={
    'class': 'form-control',
    'accept': DOC_ATTACHMENT_ACCEPT,
})


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
            'attachment',
        ]
        widgets = {
            'receipt_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'supplier': forms.Select(attrs=FORM_SELECT),
            'po_number': forms.TextInput(attrs=FORM_CONTROL),
            'received_by': forms.Select(attrs=FORM_SELECT),
            'checked_by': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].required = False
        self.fields['received_by'].queryset = _employed_users_qs()
        self.fields['checked_by'].queryset = _employed_users_qs()
        self.fields['received_by'].required = False
        self.fields['checked_by'].required = False
        self.fields['attachment'].required = False
        if not self.instance.pk:
            self.initial.setdefault('receipt_date', timezone.localdate())

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


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
            'attachment',
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
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['issued_by'].queryset = _employed_users_qs()
        self.fields['issued_by'].required = False
        self.fields['production_order'].required = False
        self.fields['product_code'].required = False
        self.fields['recipient_department'].required = False
        self.fields['recipient_name'].required = False
        self.fields['attachment'].required = False
        if not self.instance.pk:
            self.initial.setdefault('issue_date', timezone.localdate())

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


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
        fields = ['adjust_date', 'reason', 'attachment']
        widgets = {
            'adjust_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'reason': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attachment'].required = False
        if not self.instance.pk:
            self.initial.setdefault('adjust_date', timezone.localdate())

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


class StockAdjustmentLineForm(forms.ModelForm):
    class Meta:
        model = StockAdjustmentLine
        fields = ['material', 'location', 'system_qty', 'actual_qty', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ tên hoặc mã NPL...',
            }),
            'location': forms.Select(attrs=FORM_SELECT),
            'system_qty': forms.NumberInput(attrs={
                **FORM_CONTROL,
                'step': '0.001',
                'readonly': 'readonly',
                'tabindex': '-1',
                'class': 'form-control jp-npl-system-qty',
            }),
            'actual_qty': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        material_id = None
        if self.instance.pk and self.instance.material_id:
            material_id = self.instance.material_id
        elif self.initial.get('material'):
            material_id = self.initial['material']
        if material_id:
            self.fields['material'].queryset = (
                Material.objects.filter(pk=material_id).select_related('unit')
            )
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = 'Gõ tên hoặc mã để tìm...'
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True)
        self.fields['notes'].required = False
        self.fields['system_qty'].required = False
        default_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)
        if self.instance.pk:
            self.initial.setdefault('system_qty', self.instance.system_qty)
        elif self.is_bound:
            material_id = self.data.get(self.add_prefix('material'))
            location_id = self.data.get(self.add_prefix('location'))
            if material_id and location_id:
                try:
                    material = Material.objects.get(pk=material_id)
                    location = WarehouseLocation.objects.get(pk=location_id)
                    self.initial['system_qty'] = balance_qty(material, location)
                except (Material.DoesNotExist, WarehouseLocation.DoesNotExist, ValueError):
                    pass

    def full_clean(self):
        if self.data:
            self.fields['material'].queryset = (
                Material.objects.filter(is_active=True).select_related('unit')
            )
        super().full_clean()

    def clean(self):
        cleaned = super().clean()
        material = cleaned.get('material')
        location = cleaned.get('location')
        if material and location:
            cleaned['system_qty'] = balance_qty(material, location)
        return cleaned

    def save(self, commit=True):
        line = super().save(commit=False)
        line.system_qty = self.cleaned_data.get('system_qty', Decimal('0'))
        if commit:
            line.save()
        return line


class BaseStockAdjustmentLineFormSet(BaseInlineFormSet):
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
            raise ValidationError('Phiếu điều chỉnh cần ít nhất một dòng NPL.')
        seen = set()
        for line in active_lines:
            material = line['material']
            location = line['location']
            key = (material.pk, location.pk)
            if key in seen:
                raise ValidationError(
                    f'Trùng NPL + vị trí: {material.code} tại {location.code}.'
                )
            seen.add(key)
            actual_qty = line.get('actual_qty')
            if actual_qty is None or actual_qty < 0:
                raise ValidationError('Tồn thực tế không được âm cho mỗi dòng NPL.')


StockAdjustmentLineFormSet = inlineformset_factory(
    StockAdjustment,
    StockAdjustmentLine,
    form=StockAdjustmentLineForm,
    formset=BaseStockAdjustmentLineFormSet,
    extra=2,
    can_delete=True,
)


class StocktakeForm(forms.ModelForm):
    class Meta:
        model = Stocktake
        fields = ['name', 'stocktake_date', 'notes', 'attachment']
        widgets = {
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'stocktake_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['attachment'].required = False
        if not self.instance.pk:
            self.initial.setdefault('stocktake_date', timezone.localdate())

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


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


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['transfer_date', 'from_location', 'to_location', 'notes', 'attachment']
        widgets = {
            'transfer_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'from_location': forms.Select(attrs=FORM_SELECT),
            'to_location': forms.Select(attrs=FORM_SELECT),
            'notes': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': 'Ghi chú (tuỳ chọn)',
                'maxlength': '255',
            }),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        self.warehouse_locked = kwargs.pop('warehouse_locked', False)
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['attachment'].required = False
        locations = WarehouseLocation.objects.filter(is_active=True)
        self.fields['from_location'].queryset = locations
        self.fields['to_location'].queryset = locations
        if self.warehouse_locked and self.instance.pk:
            for name in ('from_location', 'to_location'):
                field = self.fields[name]
                field.disabled = True
                css = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = f'{css} jp-wh-locked'.strip()
            self.initial.setdefault('from_location', self.instance.from_location_id)
            self.initial.setdefault('to_location', self.instance.to_location_id)
        if not self.instance.pk:
            self.initial.setdefault('transfer_date', timezone.localdate())
            default = locations.filter(code='MAIN').first()
            if default:
                self.initial.setdefault('from_location', default.pk)

    def clean(self):
        cleaned = super().clean()
        if self.warehouse_locked and self.instance.pk:
            cleaned['from_location'] = self.instance.from_location
            cleaned['to_location'] = self.instance.to_location
        from_loc = cleaned.get('from_location')
        to_loc = cleaned.get('to_location')
        if from_loc and to_loc and from_loc.pk == to_loc.pk:
            raise ValidationError('Kho gửi và kho nhận phải khác nhau.')
        if self.instance.pk and self.instance.lines.exists():
            if from_loc and from_loc.pk != self.instance.from_location_id:
                self.add_error(
                    'from_location',
                    'Đã có dòng hàng — không thể đổi kho gửi. Xóa hết dòng NPL trước.',
                )
            if to_loc and to_loc.pk != self.instance.to_location_id:
                self.add_error(
                    'to_location',
                    'Đã có dòng hàng — không thể đổi kho nhận. Xóa hết dòng NPL trước.',
                )
        return cleaned

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


class StockTransferLineForm(forms.ModelForm):
    class Meta:
        model = StockTransferLine
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ mã hoặc tên NPL...',
            }),
            'quantity': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0.001'}),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        material_id = None
        if self.instance.pk and self.instance.material_id:
            material_id = self.instance.material_id
        elif self.initial.get('material'):
            material_id = self.initial['material']
        if material_id:
            self.fields['material'].queryset = (
                Material.objects.filter(pk=material_id).select_related('unit')
            )
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = 'Gõ mã hoặc tên để tìm...'
        self.fields['notes'].required = False

    def full_clean(self):
        if self.data:
            self.fields['material'].queryset = (
                Material.objects.filter(is_active=True).select_related('unit')
            )
        super().full_clean()


def transfer_post_has_active_lines(data, prefix: str = 'lines') -> bool:
    if not data:
        return False
    try:
        total = int(data.get(f'{prefix}-TOTAL_FORMS', 0) or 0)
    except (TypeError, ValueError):
        return False
    for idx in range(total):
        if data.get(f'{prefix}-{idx}-DELETE'):
            continue
        if data.get(f'{prefix}-{idx}-material'):
            return True
    return False


class BaseStockTransferLineFormSet(BaseInlineFormSet):
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
            raise ValidationError('Phiếu chuyển cần ít nhất một dòng nguyên phụ liệu.')
        for line in active_lines:
            qty = line.get('quantity')
            if qty is None or qty <= 0:
                raise ValidationError('Số lượng chuyển phải lớn hơn 0 cho mỗi dòng NPL.')
        if self.data and active_lines:
            lock_from = (self.data.get('wh_lock_from') or '').strip()
            lock_to = (self.data.get('wh_lock_to') or '').strip()
            post_from = (self.data.get('from_location') or '').strip()
            post_to = (self.data.get('to_location') or '').strip()
            if lock_from and post_from and lock_from != post_from:
                raise ValidationError(
                    'Không thể đổi kho gửi sau khi đã nhập dòng hàng. Xóa hết dòng NPL để đổi kho.',
                )
            if lock_to and post_to and lock_to != post_to:
                raise ValidationError(
                    'Không thể đổi kho nhận sau khi đã nhập dòng hàng. Xóa hết dòng NPL để đổi kho.',
                )


StockTransferLineFormSet = inlineformset_factory(
    StockTransfer,
    StockTransferLine,
    form=StockTransferLineForm,
    formset=BaseStockTransferLineFormSet,
    extra=2,
    can_delete=True,
)


class StockDisposalForm(forms.ModelForm):
    class Meta:
        model = StockDisposal
        fields = ['disposal_date', 'from_location', 'reason', 'notes', 'attachment']
        widgets = {
            'disposal_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'from_location': forms.Select(attrs=FORM_SELECT),
            'reason': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['from_location'].queryset = source_locations_qs()
        if not self.instance.pk:
            self.initial.setdefault('disposal_date', timezone.localdate())
            default = source_locations_qs().filter(code='MAIN').first()
            if default:
                self.initial.setdefault('from_location', default.pk)
        self.fields['attachment'].required = False

    def clean_attachment(self):
        return validate_doc_attachment(self.cleaned_data.get('attachment'))


class StockDisposalLineForm(forms.ModelForm):
    class Meta:
        model = StockDisposalLine
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs=FORM_SELECT),
            'quantity': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0.001'}),
            'notes': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True).select_related('unit')
        self.fields['notes'].required = False


class BaseStockDisposalLineFormSet(BaseInlineFormSet):
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
            raise ValidationError('Phiếu hủy cần ít nhất một dòng nguyên phụ liệu.')
        for line in active_lines:
            qty = line.get('quantity')
            if qty is None or qty <= 0:
                raise ValidationError('Số lượng hủy phải lớn hơn 0 cho mỗi dòng NPL.')


StockDisposalLineFormSet = inlineformset_factory(
    StockDisposal,
    StockDisposalLine,
    form=StockDisposalLineForm,
    formset=BaseStockDisposalLineFormSet,
    extra=2,
    can_delete=True,
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
