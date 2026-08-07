"""Forms đơn đặt hàng sản xuất."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from san_xuat.forms import _product_code_choices


class SalesOrderHeaderForm(forms.Form):
    code = forms.CharField(
        required=False,
        max_length=40,
        label='Số đơn hàng',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Để trống = tự sinh',
        }),
    )
    customer_name = forms.CharField(
        required=False,
        max_length=255,
        label='Khách hàng',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
    )
    request_date = forms.DateField(
        label='Ngày yêu cầu',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm jp-date-vn', 'type': 'date'}),
    )
    due_date = forms.DateField(
        required=False,
        label='Hạn sản xuất',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm jp-date-vn', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        label='Ghi chú',
        widget=forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
    )


class SalesOrderLineForm(forms.Form):
    product_code = forms.ChoiceField(
        label='Mã sản phẩm',
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm jp-sx-product-code-select',
            'data-placeholder': 'Gõ mã SX hoặc tên…',
        }),
    )
    product_name = forms.CharField(
        required=False,
        max_length=255,
        label='Tên',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Số lượng',
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0.01'}),
    )
    qty_scrap_rate = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        min_value=Decimal('0'),
        initial=Decimal('0'),
        label='Tỷ lệ sai hỏng %',
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data = args[0] if args else None
        extra = ''
        if data is not None:
            extra = data.get('product_code') or ''
        elif self.initial:
            extra = self.initial.get('product_code') or ''
        self.fields['product_code'].choices = _product_code_choices(extra)

    def clean_product_code(self):
        code = (self.cleaned_data.get('product_code') or '').strip()
        if not code:
            raise forms.ValidationError('Chọn mã sản phẩm.')
        from san_xuat.services.products import resolve_product_ref

        ref = resolve_product_ref(code)
        if not ref:
            raise forms.ValidationError(f'Mã {code} không có trong kho sản phẩm.')
        return ref.code


SalesOrderLineFormSet = forms.formset_factory(
    SalesOrderLineForm,
    extra=3,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class SalesOrderRejectForm(forms.Form):
    reason = forms.CharField(
        required=False,
        max_length=500,
        label='Lý do từ chối',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nhập lý do…'}),
    )


class KvImportOrdersForm(forms.Form):
    kv_order_ids = forms.CharField(widget=forms.HiddenInput())

    def clean_kv_order_ids(self):
        raw = (self.cleaned_data.get('kv_order_ids') or '').strip()
        ids = [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]
        bad = [p for p in ids if not p.isdigit()]
        if bad:
            raise forms.ValidationError('Danh sách đơn KV không hợp lệ.')
        if not ids:
            raise forms.ValidationError('Chọn ít nhất một đơn KiotViet.')
        return [int(p) for p in ids]
