"""Chuẩn hóa quy cách chữ cũ thành cấp ĐVT và đổi toàn bộ dữ liệu về ĐVT lẻ."""
import re
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kho_npl.models import (
    Material,
    MaterialSpecification,
    MaterialSpecificationLevel,
    Unit,
)
from kho_npl.services.uom import rebase_material_base as convert_material_base


UNIT_NAMES = {
    'cai': 'Cái',
    'kg': 'Kg',
    'met': 'Mét',
    'cuon': 'Cuộn',
    'goi': 'Gói',
    'hop': 'Hộp',
    'bao': 'Bao',
    'bich': 'Bịch',
    'cay': 'Cây',
    'soi': 'Sợi',
    'to': 'Tờ',
    'bo': 'Bộ',
    'can': 'Can',
    'lit': 'Lít',
    'thung': 'Thùng',
}


def _number(value):
    return Decimal(str(value).replace(',', '.'))


def infer_levels(name, current_unit_code=''):
    """Trả về ([(mã ĐVT, hệ số với cấp dưới)], diễn giải), hoặc None."""
    text = (name or '').strip().lower()
    compact = re.sub(r'\s+', '', text).replace('–', '-')

    match = re.search(r'1bao=10bịch.*?1bịch=.*?(\d+(?:[.,]\d+)?)c', compact)
    if match:
        return [('cai', Decimal('1')), ('bich', _number(match.group(1))), ('bao', Decimal('10'))], 'bao-bịch-cái'

    match = re.search(r'1cây.*?(\d+(?:[.,]\d+)?)kg.*?(\d+(?:[.,]\d+)?)cái', compact)
    if match:
        kg_per_cay = _number(match.group(1))
        total_cai = _number(match.group(2))
        return [
            ('cai', Decimal('1')),
            ('kg', total_cai / kg_per_cay),
            ('cay', kg_per_cay),
        ], 'cây-kg-cái'

    direct_patterns = (
        (r'1cuộn=(\d+(?:[.,]\d+)?)c', 'cai', 'cuon'),
        (r'1cuộn=(\d+(?:[.,]\d+)?)m$', 'met', 'cuon'),
        (r'1cây=(\d+(?:[.,]\d+)?)tờ$', 'to', 'cay'),
        (r'1thùng=(\d+(?:[.,]\d+)?)(?:cái|c)$', 'cai', 'thung'),
        (r'1can=(\d+(?:[.,]\d+)?)lít$', 'lit', 'can'),
        (r'1gói=(\d+(?:[.,]\d+)?)cái', 'cai', 'goi'),
        (r'1hộp=(\d+(?:[.,]\d+)?)c', 'cai', 'hop'),
        (r'1kg=(\d+(?:[.,]\d+)?)cái', 'cai', 'kg'),
        (r'1kg/(\d+(?:[.,]\d+)?)sợi', 'soi', 'kg'),
    )
    for pattern, base_code, outer_code in direct_patterns:
        match = re.search(pattern, compact)
        if match:
            return [
                (base_code, Decimal('1')),
                (outer_code, _number(match.group(1))),
            ], f'{outer_code}-{base_code}'

    # Chuỗi vải có thể chứa khổ "1m65"; chỉ phần 1kg/Nm là hệ số ĐVT.
    match = re.search(r'1kg/(\d+(?:[.,]\d+)?)m(?:$|[^a-z])', compact)
    if match:
        return [('met', Decimal('1')), ('kg', _number(match.group(1)))], 'kg-mét'

    match = re.fullmatch(r'(?:1)?gói=?(\d+(?:[.,]\d+)?)', compact)
    if match:
        return [('cai', Decimal('1')), ('goi', _number(match.group(1)))], 'gói-cái'

    match = re.fullmatch(r'(?:1)?hộp=?(\d+(?:[.,]\d+)?)', compact)
    if match:
        return [('cai', Decimal('1')), ('hop', _number(match.group(1)))], 'hộp-cái'

    match = re.fullmatch(r'bộ=?(\d+(?:[.,]\d+)?)cái', compact)
    if match:
        return [('cai', Decimal('1')), ('bo', _number(match.group(1)))], 'bộ-cái'

    match = re.fullmatch(r'cuộn=?(\d+(?:[.,]\d+)?)(m|tem|kg)', compact)
    if match:
        base_code = {'m': 'met', 'tem': 'cai', 'kg': 'kg'}[match.group(2)]
        return [(base_code, Decimal('1')), ('cuon', _number(match.group(1)))], f'cuộn-{base_code}'

    if current_unit_code:
        # "1m/4g", "cái", "cuộn" và các quy cách không phải đóng gói:
        # giữ đúng ĐVT hiện đang được nhân viên dùng, không suy diễn đổi chiều.
        return [(current_unit_code, Decimal('1'))], 'giữ ĐVT hiện tại'
    if compact in {'a4sheet'}:
        return [('to', Decimal('1'))], 'tờ'
    if compact in {'1mét'}:
        return [('met', Decimal('1'))], 'mét'
    return None


def _factor_for_code(levels, code):
    factor = Decimal('1')
    for unit_code, qty in levels:
        factor *= qty
        if unit_code == code:
            return factor
    return None


def _convert_json(value, factors_by_code):
    changed = False
    if isinstance(value, list):
        result = []
        for item in value:
            new_item, item_changed = _convert_json(item, factors_by_code)
            result.append(new_item)
            changed = changed or item_changed
        return result, changed
    if not isinstance(value, dict):
        return value, False

    result = dict(value)
    material_code = str(value.get('material_code') or '').strip().lower()
    factor = factors_by_code.get(material_code)
    owns_material = factor is not None
    for key, item in value.items():
        if owns_material and isinstance(item, (int, float, Decimal, str)):
            try:
                number = Decimal(str(item))
            except Exception:
                number = None
            if number is not None and (key == 'qty' or key.startswith('qty_') or key.endswith('_qty')):
                converted = number * factor
                result[key] = str(converted) if isinstance(item, str) else float(converted)
                changed = True
            elif number is not None and 'unit_price' in key:
                converted = number / factor
                result[key] = str(converted) if isinstance(item, str) else float(converted)
                changed = True
        new_item, item_changed = _convert_json(result[key], factors_by_code)
        result[key] = new_item
        changed = changed or item_changed
    return result, changed


def _convert_all_json_snapshots(factors_by_code):
    # Chỉ snapshot BOM này chứa material_code + qty. Các JSON khác là size,
    # cấu hình hoặc audit lịch sử, không được phép sửa.
    try:
        model = apps.get_model('san_xuat', 'SxSalesOrderLine')
    except LookupError:
        return
    field_name = 'bom_line_overrides'
    changed_rows = []
    for obj in model.objects.exclude(**{field_name: []}).iterator():
        converted, changed = _convert_json(getattr(obj, field_name), factors_by_code)
        if changed:
            setattr(obj, field_name, converted)
            changed_rows.append(obj)
        if len(changed_rows) >= 500:
            model.objects.bulk_update(changed_rows, [field_name])
            changed_rows = []
    if changed_rows:
        model.objects.bulk_update(changed_rows, [field_name])


class Command(BaseCommand):
    help = 'Chuẩn hóa free-text quy cách NPL thành 1-3 cấp; mặc định chỉ dry-run.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi vào cơ sở dữ liệu.')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        changes = []
        deactivated = []
        errors = []

        specs = (
            MaterialSpecification.objects
            .prefetch_related('materials__unit', 'levels__unit')
            .order_by('code')
        )
        for spec in specs:
            materials = list(spec.materials.all())
            old_codes = {material.unit.code for material in materials}
            if len(old_codes) > 1:
                errors.append(f'{spec.code}: đang dùng nhiều ĐVT cơ sở {sorted(old_codes)}')
                continue
            current_code = next(iter(old_codes), '')
            inferred = infer_levels(spec.name, current_code)
            if inferred is None:
                if not materials:
                    deactivated.append(spec)
                    continue
                errors.append(f'{spec.code}: không suy luận được "{spec.name}"')
                continue
            levels, reason = inferred
            old_factor = _factor_for_code(levels, current_code) if current_code else Decimal('1')
            if materials and old_factor is None:
                errors.append(f'{spec.code}: ĐVT cũ {current_code} không có trong công thức {levels}')
                continue
            changes.append((spec, materials, levels, reason, old_factor))

        self.stdout.write(f'Chế độ: {"APPLY" if apply_changes else "DRY-RUN"}')
        for spec, materials, levels, reason, old_factor in changes:
            formula = ' -> '.join(
                f'{code} x{qty.normalize()}' if index else code
                for index, (code, qty) in enumerate(levels)
            )
            self.stdout.write(
                f'OK {spec.code}: "{spec.name}" => {formula}; '
                f'{len(materials)} NPL; đổi SL x{old_factor.normalize()} ({reason})'
            )
        for spec in deactivated:
            self.stdout.write(f'TẮT {spec.code}: "{spec.name}" (không có NPL, không phải công thức ĐVT)')
        for message in errors:
            self.stderr.write(f'LỖI {message}')
        if errors:
            raise CommandError(f'Có {len(errors)} quy cách không an toàn; chưa ghi dữ liệu.')
        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f'Dry-run xong: {len(changes)} quy cách, {len(deactivated)} mục sẽ tắt. '
                'Chạy lại với --apply để ghi.'
            ))
            return

        with transaction.atomic():
            units = {}
            required_codes = {code for _, _, levels, _, _ in changes for code, _ in levels}
            for code in required_codes:
                unit, _ = Unit.objects.get_or_create(
                    code=code,
                    defaults={'name': UNIT_NAMES.get(code, code.replace('-', ' ').title()), 'is_active': True},
                )
                if not unit.is_active:
                    unit.is_active = True
                    unit.save(update_fields=['is_active'])
                units[code] = unit

            for spec, materials, levels, _, old_factor in changes:
                old_base = materials[0].unit if materials else None
                new_base = units[levels[0][0]]
                if old_base and old_base.pk != new_base.pk:
                    for material in materials:
                        convert_material_base(material, old_base, old_factor)

                MaterialSpecificationLevel.objects.filter(specification=spec).delete()
                MaterialSpecificationLevel.objects.bulk_create([
                    MaterialSpecificationLevel(
                        specification=spec,
                        level=index,
                        unit=units[code],
                        qty_in_next_lower=qty,
                    )
                    for index, (code, qty) in enumerate(levels, start=1)
                ])
                if materials:
                    Material.objects.filter(pk__in=[m.pk for m in materials]).update(unit=new_base)

            changed_factors = {
                material.code.lower(): old_factor
                for _, materials, levels, _, old_factor in changes
                if materials and materials[0].unit.code != levels[0][0]
                for material in materials
            }
            _convert_all_json_snapshots(changed_factors)
            MaterialSpecification.objects.filter(pk__in=[s.pk for s in deactivated]).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f'Đã chuẩn hóa {len(changes)} quy cách; tắt {len(deactivated)} mục không dùng/không phải ĐVT.'
        ))
