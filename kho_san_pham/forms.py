from django import forms
from django.core.exceptions import ValidationError
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


class TitledCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Checkbox nhiều lựa chọn — title hover theo map mã → tên."""

    def __init__(self, *args, title_map=None, **kwargs):
        self.title_map = title_map or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        key = str(value)
        title = self.title_map.get(key) or self.title_map.get(key.upper()) or label
        option.setdefault('attrs', {})
        option['attrs']['title'] = title
        return option


def parse_vnd_integer(value):
    """Nhận giá VND: 195000, 195.000, 195,000 → 195000. Không lấy phần thập phân."""
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValueError('invalid')
    if isinstance(value, (int, Decimal)):
        d = Decimal(value)
        if d != d.to_integral_value():
            raise ValueError('decimal')
        return d.quantize(Decimal('1'))
    if isinstance(value, float):
        d = Decimal(str(value))
        if d != d.to_integral_value():
            raise ValueError('decimal')
        return d.quantize(Decimal('1'))

    text = (
        str(value)
        .strip()
        .replace('\u00a0', '')
        .replace(' ', '')
        .replace('₫', '')
        .replace('đ', '')
        .replace('VND', '')
        .replace('vnd', '')
        .replace('_', '')
    )
    if not text:
        return None
    if text.startswith('+'):
        text = text[1:]
    if text.startswith('-'):
        raise ValueError('negative')

    has_dot = '.' in text
    has_comma = ',' in text

    if has_dot and has_comma:
        last_dot = text.rfind('.')
        last_comma = text.rfind(',')
        if last_comma > last_dot:
            intpart, frac = text[:last_comma], text[last_comma + 1:]
            intpart = intpart.replace('.', '')
        else:
            intpart, frac = text[:last_dot], text[last_dot + 1:]
            intpart = intpart.replace(',', '')
        if not intpart.isdigit() or (frac and not frac.isdigit()):
            raise ValueError('invalid')
        if frac and int(frac) != 0:
            raise ValueError('decimal')
        text = intpart
    elif has_dot or has_comma:
        sep = '.' if has_dot else ','
        parts = text.split(sep)
        if not parts[0] or not all(p.isdigit() for p in parts):
            raise ValueError('invalid')
        if len(parts) > 2:
            if any(len(p) != 3 for p in parts[1:]):
                raise ValueError('invalid')
            text = ''.join(parts)
        else:
            frac = parts[1]
            if len(frac) == 3:
                text = parts[0] + frac
            elif not frac or int(frac) == 0:
                text = parts[0]
            else:
                raise ValueError('decimal')

    if not text.isdigit():
        raise ValueError('invalid')
    return Decimal(text)


class VndAmountInput(forms.TextInput):
    def format_value(self, value):
        if value in (None, ''):
            return ''
        try:
            parsed = parse_vnd_integer(value)
        except (InvalidOperation, ValueError, TypeError):
            return str(value)
        if parsed is None:
            return ''
        return str(int(parsed))


class VndIntegerField(forms.DecimalField):
    default_error_messages = {
        'invalid': 'Giá bán không phải số. Nhập 195000 hoặc 195.000.',
        'decimal': 'Giá bán là số nguyên, không có số thập phân.',
    }

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return parse_vnd_integer(value)
        except ValueError as exc:
            code = str(exc) if str(exc) in ('decimal', 'invalid') else 'invalid'
            raise ValidationError(self.error_messages.get(code, self.error_messages['invalid']), code=code) from exc


class ProductForm(forms.ModelForm):
    """Form SP — SKU ghép Style-[Màu-]Size."""

    base_price = VndIntegerField(
        required=False,
        min_value=Decimal('0'),
        max_digits=18,
        decimal_places=0,
        label='Giá bán',
        widget=VndAmountInput(attrs={
            **FORM_CONTROL,
            'inputmode': 'decimal',
            'autocomplete': 'off',
            'placeholder': 'VD: 195000 hoặc 195.000',
        }),
    )

    # Không nằm trong Meta.fields: lưu qua set_catalog_qty → sổ kho, không ghi cột thẳng.
    qty_on_hand = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        max_digits=14,
        decimal_places=2,
        label='Tồn xưởng',
        initial=Decimal('0'),
        widget=forms.NumberInput(attrs={**FORM_CONTROL, 'step': '1', 'min': '0'}),
        help_text='Tồn tại kho thành phẩm xưởng (XUONG-TP). Cửa hàng không sửa ở đây.',
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
                'placeholder': 'Tự ghép Style-Size',
                'id': 'id_code',
            }),
            'accounting_code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Mã kế toán'}),
            'kiotviet_code': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'Mã trên KiotViet'}),
            'name': forms.TextInput(attrs=FORM_CONTROL),
            'full_name': forms.TextInput(attrs=FORM_CONTROL),
            'bar_code': forms.TextInput(attrs=FORM_CONTROL),
            'unit': forms.TextInput(attrs={**FORM_CONTROL, 'placeholder': 'VD: Cái, Bộ…'}),
            'category_name': forms.TextInput(attrs=FORM_CONTROL),
            'base_price': VndAmountInput(attrs={
                **FORM_CONTROL,
                'inputmode': 'decimal',
                'autocomplete': 'off',
                'placeholder': 'VD: 195000 hoặc 195.000',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control form-control-sm',
                'accept': 'image/*,.jpg,.jpeg,.png,.gif,.webp',
            }),
            'description': forms.Textarea(attrs=FORM_TEXTAREA),
            'notes': forms.Textarea(attrs=FORM_TEXTAREA),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, clone_from=None, locked_style=None, multi_variant=False, **kwargs):
        self.clone_from = clone_from
        self.locked_style = (locked_style or '').strip().upper() or None
        self.multi_variant = bool(multi_variant) and not getattr(kwargs.get('instance'), 'pk', None)
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
        self.fields['base_price'].localize = False
        self.fields['base_price'].widget.is_localized = False
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
        # Giữ giá trị đang dùng (kể cả khi nhân bản) nếu không còn active
        inst = self.instance
        ref = inst if inst and inst.pk else self.clone_from
        if inst and inst.pk:
            self.fields['qty_on_hand'].initial = inst.qty_on_hand
        if ref and getattr(ref, 'pk', None):
            if ref.color_code and ref.color_code not in {c.code for c in colors}:
                color_choices.append((ref.color_code, f'{ref.color_code} (đang dùng)'))
            if ref.size_label and ref.size_label not in {s.code for s in sizes}:
                size_choices.append((ref.size_label, f'{ref.size_label} (đang dùng)'))
            if ref.catalog_type_id and not ProductType.objects.filter(
                pk=ref.catalog_type_id, is_active=True,
            ).exists():
                self.fields['catalog_type'].queryset = (
                    ProductType.objects.filter(Q(is_active=True) | Q(pk=ref.catalog_type_id))
                    .order_by('sort_order', 'code')
                )
        self._color_name_map = {c.code.upper(): c.name for c in colors}
        if self.clone_from and self.clone_from.color_code:
            self._color_name_map.setdefault(
                self.clone_from.color_code.upper(),
                self.clone_from.color_label or self.clone_from.color_code,
            )
        if self.multi_variant:
            self.variant_existing = self._variant_existing_combos(self.locked_style)
            size_titles = {s.code: (s.name or s.code) for s in sizes}
            design_colors = self._design_color_choices(self.locked_style)
            color_titles = {code: label for code, label in design_colors}
            for code, label in design_colors:
                self._color_name_map[code.upper()] = label
            self.fields['color_codes'] = forms.MultipleChoiceField(
                label='Màu',
                required=False,
                choices=[(code, label) for code, label in design_colors],
                widget=TitledCheckboxSelectMultiple(title_map=color_titles),
            )
            if not self.is_bound:
                self.fields['color_codes'].initial = [code for code, _label in design_colors]
            self.fields['colors_text'] = forms.CharField(
                label='Màu mới',
                required=False,
                widget=forms.TextInput(attrs={
                    **FORM_CONTROL,
                    'id': 'id_colors_text',
                    'placeholder': 'Thêm màu mới, VD: PNK',
                    'autocomplete': 'off',
                }),
            )
            # Đủ size trong form; UI chỉ hiện size còn thiếu theo màu (JS + clean).
            self.fields['size_labels'] = forms.MultipleChoiceField(
                label='Size',
                required=True,
                choices=[(s.code, s.code) for s in sizes],
                widget=TitledCheckboxSelectMultiple(title_map=size_titles),
                error_messages={'required': 'Chọn ít nhất một size chưa có.'},
            )
            self.fields['category_name'].widget.attrs['readonly'] = 'readonly'
            del self.fields['color_code']
            del self.fields['size_label']
            del self.fields['code']
            del self.fields['bar_code']
        else:
            self.fields['color_code'].widget = forms.Select(
                attrs={**FORM_SELECT, 'id': 'id_color_code'},
                choices=color_choices,
            )
            self.fields['size_label'].widget = forms.Select(
                attrs={**FORM_SELECT, 'id': 'id_size_label'},
                choices=size_choices,
            )
        if self.locked_style:
            self.fields['style_code'].initial = self.locked_style
            self.fields['style_code'].widget.attrs['readonly'] = 'readonly'
            if 'code' in self.fields:
                self.fields['code'].required = False

    @staticmethod
    def _design_color_choices(style: str | None) -> list[tuple[str, str]]:
        """Màu colorway trên hồ sơ thiết kế của Style, kèm màu đã có trên SKU."""
        from san_xuat.hub_models import SxColor
        from san_xuat.services.sku_catalog import normalize_token
        from thiet_ke_sp.models import Handover
        from thiet_ke_sp.services.workflow import _colorway_code

        if not style:
            return []
        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(code: str, label: str) -> None:
            token = normalize_token(code)
            if not token or token in seen:
                return
            seen.add(token)
            ordered.append((token, (label or token)[:80]))

        handover = (
            Handover.objects.filter(product_code__iexact=style)
            .select_related('design_version', 'dossier', 'dossier__approved_design_version')
            .first()
        )
        versions = []
        if handover is not None:
            if handover.design_version_id:
                versions.append(handover.design_version)
            approved = getattr(handover.dossier, 'approved_design_version', None)
            if approved is not None and all(approved.pk != dv.pk for dv in versions):
                versions.append(approved)
            for dv in handover.dossier.design_versions.filter(is_current=True):
                if all(dv.pk != item.pk for item in versions):
                    versions.append(dv)
        for dv in versions:
            for cw in dv.colorways.all():
                label = (cw.name or '').strip() or (cw.color_codes or '').strip()
                if not label:
                    continue
                known = SxColor.objects.filter(name__iexact=label).first()
                if known is not None:
                    add(known.code, known.name or label)
                else:
                    add(_colorway_code(label) or 'MAU', label)
        for code, label in (
            Product.objects.filter(style_code__iexact=style)
            .exclude(color_code='')
            .values_list('color_code', 'color_label')
            .distinct()
        ):
            add(code, label or code)
        return ordered

    def _resolve_typed_colors(self, text: str) -> list[str]:
        """Mã hoặc tên màu gõ thêm. Tên trùng danh mục thì lấy mã có sẵn."""
        from san_xuat.hub_models import SxColor
        from san_xuat.services.sku_catalog import normalize_token

        out: list[str] = []
        for raw in self._parse_colors_text(text):
            known = (
                SxColor.objects.filter(code__iexact=raw).first()
                or SxColor.objects.filter(name__iexact=raw).first()
            )
            token = normalize_token(known.code if known is not None else raw)
            if not token or token in out:
                continue
            if known is not None:
                self._color_name_map[token] = known.name or token
            else:
                self._color_name_map.setdefault(token, token)
            out.append(token)
        return out

    @staticmethod
    def _parse_colors_text(text: str) -> list[str]:
        from san_xuat.services.sku_catalog import normalize_token
        import re

        out: list[str] = []
        for part in re.split(r'[,;\s]+', text or ''):
            token = normalize_token(part)
            if token and token not in out:
                out.append(token)
        return out

    @staticmethod
    def _variant_existing_combos(style: str | None) -> list[list[str]]:
        if not style:
            return []
        rows = Product.objects.filter(style_code__iexact=style).values_list('color_code', 'size_label')
        return [
            [(c or '').strip().upper(), (s or '').strip().upper()]
            for c, s in rows
            if (s or '').strip()
        ]

    @staticmethod
    def _size_missing_for_colors(existing: list[list[str]], colors: list[str], size_code: str) -> bool:
        size_u = (size_code or '').strip().upper()
        if not size_u:
            return False
        existing_set = {(c, s) for c, s in existing}
        targets = colors if colors else ['']
        return any((c, size_u) not in existing_set for c in targets)

    def clean_code(self):
        return (self.cleaned_data.get('code') or '').strip().upper()

    def clean_base_price(self):
        value = self.cleaned_data.get('base_price')
        return value if value is not None else Decimal('0')

    def clean_qty_on_hand(self):
        qty = self.cleaned_data.get('qty_on_hand')
        if qty is None:
            # Sửa mà bỏ trống = không đổi tồn. Tạo mới mà bỏ trống = 0.
            return None if self.instance.pk else Decimal('0')
        try:
            qty = Decimal(qty).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError) as exc:
            raise forms.ValidationError('Tồn xưởng không phải số.') from exc
        if qty < 0:
            raise forms.ValidationError('Tồn xưởng không được âm.')
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

        style = self.locked_style or normalize_style(cleaned.get('style_code') or '')
        cleaned['style_code'] = style

        if self.multi_variant:
            colors = []
            for token in [normalize_token(c) for c in (cleaned.get('color_codes') or []) if normalize_token(c)]:
                if token not in colors:
                    colors.append(token)
            for token in self._resolve_typed_colors(cleaned.get('colors_text') or ''):
                if token not in colors:
                    colors.append(token)
            if not colors:
                colors = ['']
            sizes = [normalize_token(s) for s in (cleaned.get('size_labels') or []) if normalize_token(s)]
            if not sizes:
                self.add_error('size_labels', 'Chọn ít nhất một size chưa có.')
                return cleaned
            if not style:
                raise forms.ValidationError('Thiếu mã Style.')

            existing = getattr(self, 'variant_existing', None) or self._variant_existing_combos(style)
            existing_set = {(c, s) for c, s in existing}
            create_rows = []
            skip_rows = []
            invalid_sizes = []
            for size in sizes:
                if not self._size_missing_for_colors(existing, colors, size):
                    invalid_sizes.append(size)
                    continue
                for color in colors:
                    try:
                        code = compose_sku_code(style_code=style, color_code='', size_label=size)
                    except SkuError as exc:
                        raise forms.ValidationError(str(exc)) from exc
                    exists = (color, size) in existing_set
                    row = {
                        'color_code': color,
                        'color_label': self._color_name_map.get(color, '') or color if color else '',
                        'size_label': size,
                        'code': code,
                    }
                    if exists:
                        skip_rows.append(row)
                    else:
                        create_rows.append(row)
            if invalid_sizes:
                self.add_error(
                    'size_labels',
                    'Size đã đủ cho màu đã nhập: ' + ', '.join(invalid_sizes),
                )
                return cleaned
            if not create_rows:
                raise forms.ValidationError(
                    'Mọi cặp màu × size đã chọn đều đã có trong Style. Nhập màu khác hoặc chọn size còn thiếu.',
                )
            cleaned['variant_create'] = create_rows
            cleaned['variant_skip'] = skip_rows
            if not (cleaned.get('name') or '').strip():
                cleaned['name'] = style
            # Nhóm hàng lấy từ Style / SKU gốc — không cho sửa khi thêm hàng loạt.
            locked_cat = ''
            if self.clone_from is not None:
                locked_cat = (self.clone_from.category_name or '').strip()
            if not locked_cat:
                locked_cat = (self.initial.get('category_name') or '').strip()
            cleaned['category_name'] = locked_cat
            return cleaned

        color = normalize_token(cleaned.get('color_code') or '')
        size = normalize_token(cleaned.get('size_label') or '')
        code = (cleaned.get('code') or '').strip().upper()

        cleaned['color_code'] = color
        cleaned['size_label'] = size

        if style and size:
            try:
                composed = compose_sku_code(style_code=style, color_code='', size_label=size)
            except SkuError as exc:
                raise forms.ValidationError(str(exc)) from exc
            if self.locked_style:
                has_size = code.endswith(f'-{size}') or f'-{size}-' in code
                if not code or code == composed or not has_size:
                    code = composed
            elif not code or code == composed:
                code = composed
            cleaned['code'] = code
            cleaned['color_label'] = self._color_name_map.get(color, '') or color if color else ''
        elif not code:
            raise forms.ValidationError(
                'Nhập Style + Size để ghép SKU, hoặc nhập SKU thủ công. Màu là thuộc tính của mã gốc.',
            )
        else:
            cleaned['code'] = code

        if style and size:
            dup = Product.objects.filter(
                style_code__iexact=style,
                color_code__iexact=color,
                size_label__iexact=size,
            )
            if self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                self.add_error('color_code', 'Màu và size này đã có trong Style.')
        else:
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
                display_code = product.code
                sx = get_or_create_sku(
                    style_code=product.style_code,
                    color_code=product.color_code or '',
                    size_label=product.size_label,
                    color_label=product.color_label,
                    style_name=product.name,
                    gender=product.gender,
                    user=getattr(product, 'created_by', None),
                )
                product.sx_sku = sx
                product.code = display_code
            except Exception:  # noqa: BLE001
                pass
        if commit:
            if not (product.bar_code or '').strip():
                from kho_san_pham.services.barcode import allocate_barcode
                product.bar_code = allocate_barcode()
            product.save()
        return product
