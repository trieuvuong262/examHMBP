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
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm jp-so-customer-select',
            'data-placeholder': 'Gõ tên, mã KH hoặc SĐT…',
        }),
    )
    request_date = forms.DateField(
        label='Ngày dự kiến thực hiện',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm jp-date-vn', 'type': 'date'}),
    )
    due_date = forms.DateField(
        label='Ngày dự kiến hoàn thành',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm jp-date-vn', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        label='Ghi chú',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
    )
    attachment = forms.FileField(
        required=False,
        label='File đính kèm',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control form-control-sm',
            'accept': 'image/*,.pdf,.doc,.docx,.xls,.xlsx',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        extra = ''
        data = args[0] if args else None
        if data is not None:
            extra = (data.get('customer_name') or '').strip()
        elif self.initial:
            extra = (self.initial.get('customer_name') or '').strip()
        # Không thêm option value="" — TomSelect sẽ ẩn placeholder nếu option rỗng đang selected.
        choices = [(extra, extra)] if extra else []
        self.fields['customer_name'].widget.choices = choices
        self.fields['customer_name'].choices = choices


class SalesOrderLineForm(forms.Form):
    product_code = forms.ChoiceField(
        label='Sản phẩm',
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm jp-sx-product-code-select',
            'data-placeholder': 'Gõ tên sản phẩm…',
            'data-label-mode': 'name',
        }),
    )
    product_name = forms.CharField(
        required=False,
        max_length=255,
        label='Tên',
        widget=forms.HiddenInput(attrs={
            'class': 'jp-so-product-name',
        }),
    )
    bom_version_id = forms.CharField(
        required=False,
        label='BOM (NVL + công đoạn)',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm jp-so-bom-select',
        }),
    )
    routing_id = forms.CharField(
        required=False,
        label='Routing',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm jp-so-routing-select',
            'aria-label': 'Routing',
        }),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Số lượng',
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm jp-so-qty-total',
            'step': '0.01',
            'min': '0.01',
            'readonly': True,
            'tabindex': '-1',
        }),
    )
    size_qtys = forms.CharField(
        required=False,
        label='SL theo size',
        widget=forms.HiddenInput(attrs={'class': 'jp-so-size-qtys-json'}),
    )
    applied_smv_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'class': 'jp-so-smv-json'}),
    )
    applied_bom_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'class': 'jp-so-bom-json'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        extra = ''
        bom_extra = ''
        routing_extra = ''
        if self.is_bound:
            # Formset truyền data=… + prefix=lines-N — phải đọc qua add_prefix.
            extra = (self.data.get(self.add_prefix('product_code')) or '').strip()
            bom_extra = (self.data.get(self.add_prefix('bom_version_id')) or '').strip()
            routing_extra = (self.data.get(self.add_prefix('routing_id')) or '').strip()
        elif self.initial:
            extra = (self.initial.get('product_code') or '').strip()
            bom_extra = str(self.initial.get('bom_version_id') or '').strip()
            routing_extra = str(self.initial.get('routing_id') or '').strip()
        self.fields['product_code'].choices = _product_code_choices(extra)
        self.fields['bom_version_id'].widget.choices = _optional_id_choices(bom_extra, '— BOM —')
        self.fields['routing_id'].widget.choices = _optional_id_choices(routing_extra, '— Routing —')
        if self.initial and isinstance(self.initial.get('size_qtys'), dict):
            import json
            self.initial['size_qtys'] = json.dumps(
                self.initial['size_qtys'], ensure_ascii=False, separators=(',', ':'),
            )

    def clean_product_code(self):
        code = (self.cleaned_data.get('product_code') or '').strip()
        if not code:
            raise forms.ValidationError('Chọn sản phẩm.')
        from san_xuat.services.products import resolve_product_ref

        ref = resolve_product_ref(code)
        if not ref:
            raise forms.ValidationError(f'Không tìm thấy sản phẩm {code}.')
        return ref.code

    def clean_bom_version_id(self):
        return _clean_optional_pk(self.cleaned_data.get('bom_version_id'), 'BomVersion')

    def clean_routing_id(self):
        return _clean_optional_pk(self.cleaned_data.get('routing_id'), 'SxRouting')

    def clean_size_qtys(self):
        from san_xuat.services.sales_orders import normalize_size_qtys
        import json

        raw = self.cleaned_data.get('size_qtys') or ''
        size_map = normalize_size_qtys(raw)
        # Lưu lại dạng JSON gọn để view đọc
        return json.dumps({k: float(v) for k, v in size_map.items()}, ensure_ascii=False)


def _optional_id_choices(extra_value: str = '', empty_label: str = '—') -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [('', empty_label)]
    val = (extra_value or '').strip()
    if val and val != '__create__':
        choices.append((val, val))
    return choices


def _clean_optional_pk(raw, model_name: str) -> int | None:
    val = (str(raw or '')).strip()
    if not val or val == '__create__':
        return None
    try:
        pk = int(val)
    except (TypeError, ValueError):
        raise forms.ValidationError('Giá trị không hợp lệ.') from None
    if model_name == 'BomVersion':
        from san_xuat.models import BomVersion
        if not BomVersion.objects.filter(pk=pk).exists():
            raise forms.ValidationError('Phiên bản BOM không tồn tại.')
    elif model_name == 'SxRouting':
        from san_xuat.ie_models import SxRouting
        if not SxRouting.objects.filter(pk=pk).exists():
            raise forms.ValidationError('Routing không tồn tại.')
    return pk


SalesOrderLineFormSet = forms.formset_factory(
    SalesOrderLineForm,
    extra=0,
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
