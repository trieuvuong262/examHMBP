from decimal import Decimal

import re

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from kho_npl.models import (
    Material,
    MaterialCategory,
    MaterialColor,
    MaterialSpecification,
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
from hrm.user_search import exclude_hidden_hrm_users, issue_recipient_label, issue_recipient_org_name
from kho_npl.category_tree import material_form_category_queryset
from kho_npl.doc_attachment import (
    DOC_ATTACHMENT_ACCEPT,
    IMAGE_ATTACHMENT_EXTENSIONS,
    DocClearableFileInput,
    clean_required_doc_attachment,
    validate_doc_attachment,
)
from kho_npl.catalog_labels import color_label, spec_label, unit_label
from kho_npl.services.scrap_warehouse import source_locations_qs
from kho_npl.services.adjustments import balance_qty

User = get_user_model()

FORM_CONTROL = {'class': 'form-control'}
FORM_SELECT = {'class': 'form-select'}
FORM_SEARCH_SELECT = {'class': 'form-select jp-npl-search-select'}
ISSUE_EMPLOYEE_SELECT = {
    **FORM_SEARCH_SELECT,
    'class': 'form-select jp-npl-search-select jp-npl-employee-select',
    'data-placeholder': 'Gõ tên hoặc mã nhân viên...',
}
DOC_EMPLOYEE_SELECT = ISSUE_EMPLOYEE_SELECT
SUPPLIER_SELECT = {
    **FORM_SEARCH_SELECT,
    'class': 'form-select jp-npl-search-select jp-npl-supplier-select',
    'data-placeholder': 'Gõ tên hoặc mã NCC...',
    'data-browse-on-open': '1',
}
DOC_EMPLOYEE_SELECT_BROWSE = {
    **DOC_EMPLOYEE_SELECT,
    'data-browse-on-open': '1',
}
LOCATION_ROW_SELECT = {
    **FORM_SEARCH_SELECT,
    'class': 'form-select jp-npl-search-select jp-npl-location-select',
    'data-placeholder': 'Gõ mã hoặc tên vị trí...',
}
FORM_TEXTAREA = {'class': 'form-control', 'rows': 3}
FORM_ATTACHMENT = DocClearableFileInput(attrs={
    'class': 'form-control',
    'accept': DOC_ATTACHMENT_ACCEPT,
})
DOC_DATE_DISPLAY_FORMAT = '%d/%m/%Y'
DOC_DATE_INPUT_FORMATS = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']
DOC_DATE_INPUT = {
    **FORM_CONTROL,
    'class': 'form-control jp-npl-date-input',
    'placeholder': 'dd/mm/yyyy',
    'autocomplete': 'off',
    'inputmode': 'numeric',
}


def _employed_users_qs():
    return exclude_hidden_hrm_users(
        User.objects.filter(is_active=True, profile__is_employed=True),
    ).select_related('profile', 'profile__department', 'profile__division').order_by(
        'profile__full_name', 'username',
    )


def _configure_employee_select_field(field, *, selected_id=None, required=False):
    field.queryset = (
        _employed_users_qs().filter(pk=selected_id)
        if selected_id
        else User.objects.none()
    )
    field.label_from_instance = issue_recipient_label
    field.required = required
    field.empty_label = None


def _configure_supplier_select_field(field, *, selected_id=None, required=False):
    field.queryset = (
        Supplier.objects.filter(pk=selected_id, is_active=True)
        if selected_id
        else Supplier.objects.none()
    )
    field.label_from_instance = lambda obj: (
        f'{obj.name} ({obj.code})' + (f' — {obj.phone}' if obj.phone else '')
    )
    field.required = required
    field.empty_label = None


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
            'color': forms.Select(attrs={**FORM_SEARCH_SELECT, 'data-placeholder': 'Tìm màu...'}),
            'specification': forms.Select(attrs={**FORM_SEARCH_SELECT, 'data-placeholder': 'Tìm quy cách / khổ...'}),
            'unit': forms.Select(attrs=FORM_SELECT),
            'supplier': forms.Select(attrs={**FORM_SEARCH_SELECT, 'data-placeholder': 'Tìm NCC...'}),
            'min_stock': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0'}),
            'image': DocClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.jpg,.jpeg,.png,.gif,.webp',
            }),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].label = 'Nhóm cấp 2'
        self.fields['category'].queryset = material_form_category_queryset(
            self.instance if self.instance.pk else None,
        )
        self.fields['category'].label_from_instance = lambda obj: (
            f'{obj.parent.name} › {obj.name}'
            if obj.parent_id
            else f'{obj.name} (nhóm cấp 1 — nên chọn nhóm con)'
        )
        self.fields['color'].queryset = MaterialColor.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['color'].label_from_instance = lambda obj: f'{color_label(obj)} ({obj.hex_code})'
        self.fields['color'].required = False
        self.fields['color'].empty_label = '—'
        self.fields['specification'].queryset = MaterialSpecification.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['specification'].label_from_instance = spec_label
        self.fields['specification'].required = False
        self.fields['specification'].empty_label = '—'
        self.fields['unit'].queryset = Unit.objects.filter(is_active=True)
        self.fields['unit'].label_from_instance = unit_label
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True).order_by('name')
        self.fields['supplier'].label_from_instance = lambda obj: (
            f'{obj.name} ({obj.code})' + (f' — {obj.phone}' if obj.phone else '')
        )
        self.fields['supplier'].required = False
        self.fields['supplier'].empty_label = '—'
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

    def clean_image(self):
        uploaded = self.cleaned_data.get('image')
        if uploaded is False:
            return False
        if uploaded:
            ext = (uploaded.name or '').rsplit('.', 1)[-1].lower()
            if f'.{ext}' not in IMAGE_ATTACHMENT_EXTENSIONS:
                raise ValidationError('Chỉ chấp nhận file ảnh JPG, PNG, GIF hoặc WebP.')
            return validate_doc_attachment(uploaded)
        if self.instance.pk and self.instance.image:
            return self.instance.image
        return None


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
            'receipt_date': forms.DateInput(attrs=DOC_DATE_INPUT, format=DOC_DATE_DISPLAY_FORMAT),
            'supplier': forms.Select(attrs=SUPPLIER_SELECT),
            'po_number': forms.TextInput(attrs=FORM_CONTROL),
            'received_by': forms.Select(attrs=DOC_EMPLOYEE_SELECT),
            'checked_by': forms.Select(attrs=DOC_EMPLOYEE_SELECT_BROWSE),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, operator=None, **kwargs):
        instance = kwargs.get('instance')
        if (
            instance is not None
            and not instance.pk
            and not args
            and not kwargs.get('data')
        ):
            if not instance.receipt_date:
                instance.receipt_date = timezone.localdate()
            if operator and not instance.received_by_id:
                instance.received_by = operator
        super().__init__(*args, **kwargs)
        selected_supplier_id = None
        if self.instance.pk and self.instance.supplier_id:
            selected_supplier_id = self.instance.supplier_id
        elif self.data.get('supplier'):
            raw = str(self.data.get('supplier') or '').strip()
            if raw.isdigit():
                selected_supplier_id = int(raw)
        _configure_supplier_select_field(
            self.fields['supplier'],
            selected_id=selected_supplier_id,
            required=True,
        )
        selected_received_id = None
        if self.instance.pk and self.instance.received_by_id:
            selected_received_id = self.instance.received_by_id
        elif self.data.get('received_by'):
            raw = str(self.data.get('received_by') or '').strip()
            if raw.isdigit():
                selected_received_id = int(raw)
        elif operator and not args and not kwargs.get('data'):
            selected_received_id = operator.pk
        _configure_employee_select_field(
            self.fields['received_by'],
            selected_id=selected_received_id,
            required=True,
        )
        selected_checked_id = None
        if self.instance.pk and self.instance.checked_by_id:
            selected_checked_id = self.instance.checked_by_id
        elif self.data.get('checked_by'):
            raw = str(self.data.get('checked_by') or '').strip()
            if raw.isdigit():
                selected_checked_id = int(raw)
        _configure_employee_select_field(
            self.fields['checked_by'],
            selected_id=selected_checked_id,
            required=False,
        )
        self.fields['attachment'].required = True
        self.fields['receipt_date'].input_formats = DOC_DATE_INPUT_FORMATS

    def clean_attachment(self):
        return clean_required_doc_attachment(self.cleaned_data, self.instance)

    def full_clean(self):
        if self.data:
            raw_supplier = str(self.data.get('supplier') or '').strip()
            if raw_supplier.isdigit():
                self.fields['supplier'].queryset = Supplier.objects.filter(
                    pk=int(raw_supplier),
                    is_active=True,
                )
            for field_name in ('received_by', 'checked_by'):
                raw = str(self.data.get(field_name) or '').strip()
                if raw.isdigit():
                    self.fields[field_name].queryset = _employed_users_qs().filter(pk=int(raw))
        super().full_clean()


class StockReceiptLineForm(forms.ModelForm):
    class Meta:
        model = StockReceiptLine
        fields = ['material', 'received_qty', 'location', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ tên NPL...',
            }),
            'received_qty': forms.NumberInput(attrs={
                **FORM_CONTROL,
                'step': '0.001',
                'min': '0',
                'inputmode': 'decimal',
            }),
            'location': forms.Select(attrs=LOCATION_ROW_SELECT),
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'class': 'form-control jp-npl-line-notes'}),
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
            self.fields['material'].label_from_instance = lambda material: material.name
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = None
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True).order_by('code')
        self.fields['location'].label_from_instance = lambda obj: obj.display_label()
        self.fields['notes'].required = False
        default_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)

    def clean_received_qty(self):
        qty = self.cleaned_data.get('received_qty')
        if qty is not None and qty <= 0:
            raise ValidationError('Số lượng nhập phải lớn hơn 0.')
        return qty

    def full_clean(self):
        if self.data:
            self.fields['material'].queryset = (
                Material.objects.filter(is_active=True).select_related('unit')
            )
        super().full_clean()


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
    extra=1,
    can_delete=True,
)


class StockReceiptNotesForm(forms.ModelForm):
    """Chỉ sửa ghi chú phiếu nhập đã ghi sổ — không đổi tồn hay chi tiết."""

    class Meta:
        model = StockReceipt
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={**FORM_TEXTAREA, 'placeholder': 'Ghi chú bổ sung sau khi nhập...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


class StockReceiptLineNotesForm(forms.ModelForm):
    """Chỉ sửa ghi chú từng dòng phiếu nhập đã ghi sổ."""

    class Meta:
        model = StockReceiptLine
        fields = ['notes']
        widgets = {
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Nhập ghi chú'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


StockReceiptLineNotesFormSet = inlineformset_factory(
    StockReceipt,
    StockReceiptLine,
    form=StockReceiptLineNotesForm,
    extra=0,
    can_delete=False,
)


class StockIssueForm(forms.ModelForm):
    class Meta:
        model = StockIssue
        fields = [
            'issue_date',
            'issue_type',
            'issued_by',
            'recipient',
            'notes',
            'attachment',
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs=DOC_DATE_INPUT, format=DOC_DATE_DISPLAY_FORMAT),
            'issue_type': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': 'VD: Xuất cho sản xuất, làm mẫu...',
            }),
            'issued_by': forms.Select(attrs=ISSUE_EMPLOYEE_SELECT),
            'recipient': forms.Select(attrs=ISSUE_EMPLOYEE_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, operator=None, **kwargs):
        instance = kwargs.get('instance')
        if (
            instance is not None
            and not instance.pk
            and not args
            and not kwargs.get('data')
        ):
            if not instance.issue_date:
                instance.issue_date = timezone.localdate()
            if operator and not instance.issued_by_id:
                instance.issued_by = operator
        super().__init__(*args, **kwargs)
        selected_recipient_id = None
        if self.instance.pk and self.instance.recipient_id:
            selected_recipient_id = self.instance.recipient_id
        elif self.data.get('recipient'):
            raw = str(self.data.get('recipient') or '').strip()
            if raw.isdigit():
                selected_recipient_id = int(raw)
        _configure_employee_select_field(
            self.fields['recipient'],
            selected_id=selected_recipient_id,
            required=False,
        )
        selected_issued_id = None
        if self.instance.pk and self.instance.issued_by_id:
            selected_issued_id = self.instance.issued_by_id
        elif self.data.get('issued_by'):
            raw = str(self.data.get('issued_by') or '').strip()
            if raw.isdigit():
                selected_issued_id = int(raw)
        elif operator and not args and not kwargs.get('data'):
            selected_issued_id = operator.pk
        _configure_employee_select_field(
            self.fields['issued_by'],
            selected_id=selected_issued_id,
            required=True,
        )
        self.fields['issue_type'].required = True
        self.fields['attachment'].required = True
        self.fields['issue_date'].input_formats = DOC_DATE_INPUT_FORMATS

    def clean_issue_type(self):
        value = (self.cleaned_data.get('issue_type') or '').strip()
        if not value:
            raise ValidationError('Vui lòng nhập lý do xuất.')
        return value

    def clean_attachment(self):
        return clean_required_doc_attachment(self.cleaned_data, self.instance)

    def full_clean(self):
        if self.data:
            for field_name in ('recipient', 'issued_by'):
                raw = str(self.data.get(field_name) or '').strip()
                if raw.isdigit():
                    self.fields[field_name].queryset = _employed_users_qs().filter(pk=int(raw))
        super().full_clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        recipient = self.cleaned_data.get('recipient')
        instance.recipient_department = ''
        if recipient:
            profile = getattr(recipient, 'profile', None)
            instance.recipient_name = (
                profile.full_name
                if profile and profile.full_name
                else recipient.get_full_name() or recipient.username
            )
            instance.recipient_department = issue_recipient_org_name(profile)
        else:
            instance.recipient_name = ''
        if commit:
            instance.save()
        return instance


class StockIssueNotesForm(forms.ModelForm):
    """Chỉ sửa ghi chú phiếu xuất đã ghi sổ — không đổi tồn hay chi tiết."""

    class Meta:
        model = StockIssue
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={**FORM_TEXTAREA, 'placeholder': 'Ghi chú bổ sung sau khi xuất...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


class StockIssueLineNotesForm(forms.ModelForm):
    """Chỉ sửa ghi chú từng dòng phiếu xuất đã ghi sổ."""

    class Meta:
        model = StockIssueLine
        fields = ['notes']
        widgets = {
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Nhập ghi chú'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


StockIssueLineNotesFormSet = inlineformset_factory(
    StockIssue,
    StockIssueLine,
    form=StockIssueLineNotesForm,
    extra=0,
    can_delete=False,
)


class StockIssueLineForm(forms.ModelForm):
    class Meta:
        model = StockIssueLine
        fields = ['material', 'quantity', 'location', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ tên NPL...',
            }),
            'quantity': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0.001'}),
            'location': forms.Select(attrs=LOCATION_ROW_SELECT),
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'class': 'form-control jp-npl-line-notes'}),
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
            self.fields['material'].label_from_instance = lambda material: material.name
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = None
        self.fields['location'].queryset = WarehouseLocation.objects.filter(is_active=True).order_by('code')
        self.fields['location'].label_from_instance = lambda obj: obj.display_label()
        self.fields['notes'].required = False
        default_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data
        material = cleaned_data.get('material')
        location = cleaned_data.get('location')
        qty = cleaned_data.get('quantity')
        if material and location and qty is not None:
            available = balance_qty(material, location)
            if qty > available:
                self.add_error(
                    'quantity',
                    f'Số lượng xuất vượt tồn tại vị trí (tồn {available}).',
                )
        return cleaned_data

    def full_clean(self):
        if self.data:
            self.fields['material'].queryset = (
                Material.objects.filter(is_active=True).select_related('unit')
            )
        super().full_clean()


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
    extra=1,
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
        uploaded = self.cleaned_data.get('attachment')
        if uploaded is False:
            return None
        return validate_doc_attachment(uploaded)


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
                    f'Trùng NPL + vị trí: {material.code} tại {location.display_label()}.'
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
        fields = ['name', 'stocktake_date', 'location', 'notes', 'attachment']
        widgets = {
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'stocktake_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'location': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = source_locations_qs()
        self.fields['notes'].required = False
        self.fields['attachment'].required = False
        if not self.instance.pk:
            self.initial.setdefault('stocktake_date', timezone.localdate())
            default = source_locations_qs().filter(code='MAIN').first()
            if default:
                self.initial.setdefault('location', default.pk)

    def clean_attachment(self):
        uploaded = self.cleaned_data.get('attachment')
        if uploaded is False:
            return None
        return validate_doc_attachment(uploaded)


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


# Django mặc định max_num=1000 — kho lớn có thể vượt ngưỡng khi nhập kiểm kê.
STOCKTAKE_LINE_FORMSET_MAX = 10000

StocktakeLineFormSet = inlineformset_factory(
    Stocktake,
    StocktakeLine,
    form=StocktakeLineForm,
    formset=BaseStocktakeLineFormSet,
    extra=0,
    can_delete=False,
    max_num=STOCKTAKE_LINE_FORMSET_MAX,
)


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['transfer_date', 'from_location', 'to_location', 'notes', 'attachment']
        widgets = {
            'transfer_date': forms.DateInput(attrs={**FORM_CONTROL, 'type': 'date'}),
            'from_location': forms.Select(attrs=FORM_SELECT),
            'to_location': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        self.warehouse_locked = kwargs.pop('warehouse_locked', False)
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['attachment'].required = True
        locations = WarehouseLocation.objects.filter(is_active=True)
        self.fields['from_location'].queryset = locations
        self.fields['to_location'].queryset = locations
        if self.warehouse_locked and self.instance.pk:
            field = self.fields['from_location']
            field.disabled = True
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css} jp-wh-locked'.strip()
            self.initial.setdefault('from_location', self.instance.from_location_id)
        if not self.instance.pk:
            self.initial.setdefault('transfer_date', timezone.localdate())
            default = locations.filter(code='MAIN').first()
            if default:
                self.initial.setdefault('from_location', default.pk)

    def clean(self):
        cleaned = super().clean()
        if self.warehouse_locked and self.instance.pk:
            cleaned['from_location'] = self.instance.from_location
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
        return cleaned

    def clean_attachment(self):
        return clean_required_doc_attachment(self.cleaned_data, self.instance)


class StockTransferLineForm(forms.ModelForm):
    class Meta:
        model = StockTransferLine
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ tên NPL...',
            }),
            'quantity': forms.NumberInput(attrs={
                **FORM_CONTROL,
                'step': '0.001',
                'min': '0.001',
                'inputmode': 'decimal',
            }),
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'class': 'form-control jp-npl-line-notes'}),
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
            self.fields['material'].label_from_instance = lambda material: material.name
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = None
        self.fields['notes'].required = False

    def _from_location_id_for_stock(self) -> str:
        lock = (self.data.get('wh_lock_from') or '').strip()
        if lock.isdigit():
            return lock
        if self.instance.pk and self.instance.transfer_id:
            return str(self.instance.transfer.from_location_id)
        return (self.data.get('from_location') or '').strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        material = cleaned.get('material')
        qty = cleaned.get('quantity')
        from_location_id = self._from_location_id_for_stock()
        if material and qty is not None and from_location_id.isdigit():
            location = WarehouseLocation.objects.filter(
                pk=int(from_location_id),
                is_active=True,
            ).first()
            if location:
                available = balance_qty(material, location)
                if qty > available:
                    self.add_error(
                        'quantity',
                        f'Số lượng chuyển vượt tồn tại kho gửi (tồn {available}).',
                    )
        return cleaned

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
            post_from = (self.data.get('from_location') or '').strip()
            if lock_from and post_from and lock_from != post_from:
                raise ValidationError(
                    'Không thể đổi kho gửi sau khi đã nhập dòng hàng. Xóa hết dòng NPL để đổi kho.',
                )


StockTransferLineFormSet = inlineformset_factory(
    StockTransfer,
    StockTransferLine,
    form=StockTransferLineForm,
    formset=BaseStockTransferLineFormSet,
    extra=1,
    can_delete=True,
)


class StockDisposalForm(forms.ModelForm):
    class Meta:
        model = StockDisposal
        fields = ['disposal_date', 'reason', 'notes', 'attachment']
        widgets = {
            'disposal_date': forms.DateInput(attrs=DOC_DATE_INPUT, format=DOC_DATE_DISPLAY_FORMAT),
            'reason': forms.Select(attrs=FORM_SELECT),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'attachment': FORM_ATTACHMENT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial.setdefault('disposal_date', timezone.localdate())
        self.fields['attachment'].required = False
        self.fields['disposal_date'].input_formats = DOC_DATE_INPUT_FORMATS

    def clean_attachment(self):
        uploaded = self.cleaned_data.get('attachment')
        if uploaded is False:
            return None
        return validate_doc_attachment(uploaded)


class StockDisposalLineForm(forms.ModelForm):
    class Meta:
        model = StockDisposalLine
        fields = ['material', 'quantity', 'location', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                **FORM_SELECT,
                'class': 'form-select jp-npl-material-select',
                'data-placeholder': 'Gõ tên hoặc mã NPL...',
            }),
            'quantity': forms.NumberInput(attrs={**FORM_CONTROL, 'step': '0.001', 'min': '0.001'}),
            'location': forms.Select(attrs=LOCATION_ROW_SELECT),
            'notes': forms.TextInput(attrs={**FORM_CONTROL, 'class': 'form-control jp-npl-line-notes'}),
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
            self.fields['material'].label_from_instance = lambda material: material.name
        else:
            self.fields['material'].queryset = Material.objects.none()
        self.fields['material'].empty_label = None
        self.fields['location'].queryset = source_locations_qs().order_by('code')
        self.fields['location'].label_from_instance = lambda obj: obj.display_label()
        self.fields['notes'].required = False
        default_location = source_locations_qs().filter(code='MAIN').first()
        if default_location and not self.instance.pk:
            self.initial.setdefault('location', default_location.pk)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data
        material = cleaned_data.get('material')
        location = cleaned_data.get('location')
        qty = cleaned_data.get('quantity')
        if material and location and qty is not None:
            available = balance_qty(material, location)
            if qty > available:
                self.add_error(
                    'quantity',
                    f'Số lượng hủy vượt tồn tại vị trí (tồn {available}).',
                )
        return cleaned_data

    def full_clean(self):
        if self.data:
            self.fields['material'].queryset = (
                Material.objects.filter(is_active=True).select_related('unit')
            )
        super().full_clean()


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
        fields = ['code', 'name', 'parent', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'vai-chinh'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'parent': forms.Select(attrs=FORM_SELECT),
            'sort_order': forms.NumberInput(attrs={**FORM_CONTROL, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False
        root_qs = MaterialCategory.objects.filter(is_active=True, parent__isnull=True).order_by('sort_order', 'name')
        self.fields['parent'].queryset = root_qs
        self.fields['parent'].label = 'Nhóm cấp 1'
        self.fields['parent'].required = False
        self.fields['parent'].empty_label = '— Là nhóm cấp 1 —'
        if self.instance.pk:
            self.fields['parent'].queryset = root_qs.exclude(pk=self.instance.pk)

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower()
        return _clean_unique_code(MaterialCategory, 'code', code, self.instance)

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get('parent')
        if self.instance.pk and self.instance.children.exists() and parent:
            raise ValidationError('Nhóm cấp 1 (đã có nhóm cấp 2) không thể thuộc nhóm cấp 1 khác.')
        return cleaned


class MaterialColorForm(forms.ModelForm):
    class Meta:
        model = MaterialColor
        fields = ['code', 'name', 'hex_code', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'xanh-duong'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'hex_code': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': '#3B82F6',
                'class': 'form-control jp-npl-hex-input',
                'autocomplete': 'off',
                'spellcheck': 'false',
            }),
            'sort_order': forms.NumberInput(attrs={**FORM_CONTROL, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower()
        return _clean_unique_code(MaterialColor, 'code', code, self.instance)

    def clean_hex_code(self):
        hex_code = (self.cleaned_data.get('hex_code') or '').strip().upper()
        if not hex_code.startswith('#'):
            hex_code = f'#{hex_code}'
        if not re.fullmatch(r'#[0-9A-F]{6}', hex_code):
            raise ValidationError('Mã hex phải dạng #RRGGBB.')
        return hex_code


class MaterialSpecificationForm(forms.ModelForm):
    class Meta:
        model = MaterialSpecification
        fields = ['code', 'name', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'kho-1m6'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'sort_order': forms.NumberInput(attrs={**FORM_CONTROL, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower()
        return _clean_unique_code(MaterialSpecification, 'code', code, self.instance)


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


class SupplierQuickCreateForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['code', 'name', 'phone']
        widgets = {
            'code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: NCC-VAI-DN'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'phone': forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].required = False

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        return _clean_unique_code(Supplier, 'code', code, self.instance)

    def save(self, commit=True):
        self.instance.is_active = True
        return super().save(commit=commit)


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
