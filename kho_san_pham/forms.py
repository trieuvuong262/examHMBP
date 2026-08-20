from django import forms
from django.db.models import Q
from decimal import Decimal, InvalidOperation

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
    """Form SP — SKU ghép Style-[Màu-]Size."""

    # Không nằm trong Meta.fields: lưu qua set_catalog_qty → sổ kho, không ghi cột thẳng.
    qty_on_hand = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        max_digits=14,
        decimal_places=2,
        label='Tồn kho',
        initial=Decimal('0'),
        widget=forms.NumberInput(attrs={**FORM_CONTROL, 'step': '1', 'min': '0'}),
        help_text='Tồn tại kho thành phẩm xưởng. Để trống = 0 khi tạo mới, giữ nguyên khi sửa.',
    )

    class Meta:
        model = Product
        fields = [
            'product_type',
            'catalog_type',
            'style_code',
            'color_code',
            'size_label',
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
            'catalog_type': forms.Select(attrs=FORM_SELECT),
            'style_code': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': 'VD: JP-TEE-260001',
                'autocomplete': 'off',
                'id': 'id_style_code',
            }),
            'color_code': forms.Select(attrs={**FORM_SELECT, 'id': 'id_color_code'}),
            'size_label': forms.Select(attrs={**FORM_SELECT, 'id': 'id_size_label'}),
            'code': forms.TextInput(attrs={
                **FORM_CONTROL,
                'placeholder': 'Tự ghép Style-[Màu-]Size',
                'id': 'id_code',
            }),
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
        from kho_san_pham.catalog_models import ProductType
        from san_xuat.hub_models import SxColor, SxSize

        self.fields['product_type'].choices = PRODUCT_TYPE_CHOICES
        self.fields['catalog_type'].queryset = ProductType.objects.filter(is_active=True).order_by(
            'sort_order', 'code',
        )
        self.fields['catalog_type'].required = False
        self.fields['catalog_type'].empty_label = '— Loại mã —'
        self.fields['style_code'].required = False
        self.fields['color_code'].required = False
        self.fields['size_label'].required = False
        self.fields['accounting_code'].required = False
        self.fields['kiotviet_code'].required = False
        self.fields['full_name'].required = False
        self.fields['bar_code'].required = False
        self.fields['unit'].required = False
        self.fields['category_name'].required = False
        self.fields['base_price'].required = False
        self.fields['qty_on_hand'].required = False
        self.fields['image'].required = False
        self.fields['description'].required = False
        self.fields['notes'].required = False
        self.fields['is_active'].required = False
        if not (self.instance and self.instance.pk):
            self.fields['is_active'].initial = True
        self.fields['code'].label = 'SKU'
        self.fields['style_code'].label = 'Style'
        self.fields['catalog_type'].label = 'Loại mã'

        colors = list(SxColor.objects.filter(is_active=True).order_by('sort_order', 'code'))
        sizes = list(SxSize.objects.filter(is_active=True).order_by('sort_order', 'code'))
        color_choices = [('', '— Không màu —')] + [
            (c.code, f'{c.code} — {c.name}') for c in colors
        ]
        size_choices = [('', '— Chọn size —')] + [
            (s.code, s.name or s.code) for s in sizes
        ]
        # Giữ giá trị đang dùng nếu không còn active
        inst = self.instance
        if inst and inst.pk:
            self.fields['qty_on_hand'].initial = inst.qty_on_hand
            if inst.color_code and inst.color_code not in {c.code for c in colors}:
                color_choices.append((inst.color_code, f'{inst.color_code} (đang dùng)'))
            if inst.size_label and inst.size_label not in {s.code for s in sizes}:
                size_choices.append((inst.size_label, f'{inst.size_label} (đang dùng)'))
            if inst.catalog_type_id and not ProductType.objects.filter(
                pk=inst.catalog_type_id, is_active=True,
            ).exists():
                self.fields['catalog_type'].queryset = (
                    ProductType.objects.filter(Q(is_active=True) | Q(pk=inst.catalog_type_id))
                    .order_by('sort_order', 'code')
                )
        self.fields['color_code'].widget = forms.Select(
            attrs={**FORM_SELECT, 'id': 'id_color_code'},
            choices=color_choices,
        )
        self.fields['size_label'].widget = forms.Select(
            attrs={**FORM_SELECT, 'id': 'id_size_label'},
            choices=size_choices,
        )
        self._color_name_map = {c.code.upper(): c.name for c in colors}

    def clean_code(self):
        return (self.cleaned_data.get('code') or '').strip().upper()

    def clean_qty_on_hand(self):
        qty = self.cleaned_data.get('qty_on_hand')
        if qty is None:
            # Sửa mà bỏ trống = không đổi tồn. Tạo mới mà bỏ trống = 0.
            return None if self.instance.pk else Decimal('0')
        try:
            qty = Decimal(qty).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError) as exc:
            raise forms.ValidationError('Tồn kho không phải số.') from exc
        if qty < 0:
            raise forms.ValidationError('Tồn kho không được âm.')
        return qty

    def clean_accounting_code(self):
        # Cùng mã KT dùng chung nhiều SKU / size (theo file HĐ–tem nhãn).
        return (self.cleaned_data.get('accounting_code') or '').strip()

    def clean_kiotviet_code(self):
        return (self.cleaned_data.get('kiotviet_code') or '').strip()

    def clean_product_type(self):
        value = self.cleaned_data.get('product_type') or PRODUCT_TYPE_HANG_HOA
        if value not in {PRODUCT_TYPE_THANH_PHAM, PRODUCT_TYPE_HANG_HOA}:
            raise forms.ValidationError('Loại sản phẩm không hợp lệ.')
        return value

    def clean(self):
        cleaned = super().clean()

        from san_xuat.services.sku_catalog import SkuError, compose_sku_code, normalize_style, normalize_token

        style = normalize_style(cleaned.get('style_code') or '')
        color = normalize_token(cleaned.get('color_code') or '')
        size = normalize_token(cleaned.get('size_label') or '')
        code = (cleaned.get('code') or '').strip().upper()

        cleaned['style_code'] = style
        cleaned['color_code'] = color
        cleaned['size_label'] = size

        if style and size:
            try:
                composed = compose_sku_code(style_code=style, color_code=color, size_label=size)
            except SkuError as exc:
                raise forms.ValidationError(str(exc)) from exc
            if not code or code == composed:
                code = composed
            cleaned['code'] = code
            cleaned['color_label'] = self._color_name_map.get(color, '') or color if color else ''
        elif not code:
            raise forms.ValidationError(
                'Nhập Style + Size để ghép SKU (màu tùy chọn), hoặc nhập SKU thủ công.',
            )
        else:
            cleaned['code'] = code

        qs = Product.objects.filter(code__iexact=cleaned['code'])
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error('code', 'SKU đã tồn tại.')

        if not (cleaned.get('name') or '').strip():
            cleaned['name'] = style or cleaned['code']

        return cleaned

    def save(self, commit=True):
        product = super().save(commit=False)
        product.color_label = self.cleaned_data.get('color_label') or product.color_label
        # Đồng bộ SxSku khi đủ Style + Size (màu optional)
        if product.style_code and product.size_label:
            try:
                from san_xuat.services.sku_catalog import get_or_create_sku
                sx = get_or_create_sku(
                    style_code=product.style_code,
                    color_code=product.color_code or '',
                    size_label=product.size_label,
                    color_label=product.color_label,
                    style_name=product.name,
                    sku_code=product.code,
                    gender=product.gender,
                    user=getattr(product, 'created_by', None),
                )
                product.sx_sku = sx
                product.code = sx.sku_code
            except Exception:  # noqa: BLE001
                pass
        if commit:
            if not (product.bar_code or '').strip():
                from kho_san_pham.services.barcode import allocate_barcode
                product.bar_code = allocate_barcode()
            product.save()
        return product
