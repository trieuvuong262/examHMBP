"""Ghép MÃ NHÓM khi import thư viện / routing với nhóm công đoạn đã có trên hệ thống."""

from __future__ import annotations

from dataclasses import dataclass, field

from san_xuat.ie_models import SxOperationGroup
from san_xuat.services.progress_template import GROUPS


def _fold_label(value: str) -> str:
    raw = (value or '').strip().casefold()
    for ch in ('-', '_', '/', '\\', '.', ',', '·', '—'):
        raw = raw.replace(ch, ' ')
    return ' '.join(raw.split())


def _fold_code(value: str) -> str:
    return (value or '').strip().casefold().replace('-', '_').replace(' ', '_')


def _build_import_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {
        'cat': 'CAT',
        'cut': 'CAT',
        'cắt': 'CAT',
        'cắt may': 'CAT',
        'may': 'MAY',
        'sew': 'MAY',
        'sewing': 'MAY',
        'in_ep': 'IN_EP',
        'in-ep': 'IN_EP',
        'inep': 'IN_EP',
        'in ep': 'IN_EP',
        'in ép': 'IN_EP',
        'in - ép': 'IN_EP',
        'theu': 'THEU',
        'thêu': 'THEU',
        'emb': 'THEU',
        'embroidery': 'THEU',
        'ht': 'HT',
        'hoan_thanh': 'HT',
        'hoan thanh': 'HT',
        'ủi': 'HT',
        'ủi gấp': 'HT',
        'ủi - gấp': 'HT',
        'ủi - gấp xếp': 'HT',
        'hoàn thành': 'HT',
        'gh': 'GH',
        'giao_hang': 'GH',
        'giao hang': 'GH',
        'giao hàng': 'GH',
        'giao hàng thành phẩm': 'GH',
    }
    for grp in GROUPS:
        aliases.setdefault(grp.key.casefold(), grp.key)
        aliases.setdefault(grp.label.casefold(), grp.key)
        folded_label = _fold_label(grp.label)
        if folded_label:
            aliases.setdefault(folded_label, grp.key)
    return aliases


_IMPORT_GROUP_ALIASES = _build_import_aliases()


@dataclass
class GroupResolveResult:
    group: SxOperationGroup | None = None
    matched_by: str = ''
    tried: str = ''


@dataclass
class OperationGroupResolver:
    """Index nhóm công đoạn hiện có — dùng lại trong một lần import."""

    by_code: dict[str, SxOperationGroup] = field(default_factory=dict)
    by_name: dict[str, SxOperationGroup] = field(default_factory=dict)
    by_stage: dict[str, SxOperationGroup] = field(default_factory=dict)

    @classmethod
    def build(cls) -> OperationGroupResolver:
        resolver = cls()
        qs = SxOperationGroup.objects.select_related('process_stage').order_by(
            '-is_active', 'sort_order', 'code',
        )
        for grp in qs:
            code = (grp.code or '').strip()
            name = (grp.name or '').strip()
            stage = (grp.process_stage_label or '').strip()
            if not stage and grp.process_stage_id:
                stage = (grp.process_stage.name or '').strip()

            if code:
                for key in {_fold_code(code), code.casefold(), code.upper()}:
                    resolver.by_code.setdefault(key, grp)
            if name:
                for key in {_fold_label(name), name.casefold()}:
                    resolver.by_name.setdefault(key, grp)
            if stage:
                for key in {_fold_label(stage), stage.casefold()}:
                    resolver.by_stage.setdefault(key, grp)
        return resolver

    def _by_code(self, code: str) -> SxOperationGroup | None:
        if not code:
            return None
        folded = _fold_code(code)
        return (
            self.by_code.get(folded)
            or self.by_code.get(code.casefold())
            or self.by_code.get(code.upper())
        )

    def resolve(
        self,
        group_code: str = '',
        *,
        stage_label: str = '',
        op_code: str = '',
    ) -> GroupResolveResult:
        raw = (group_code or '').strip()
        stage = (stage_label or '').strip()
        tried_parts = [p for p in (raw, stage) if p]
        tried = ' / '.join(tried_parts) or (op_code or '').strip()

        if raw:
            hit = self._by_code(raw)
            if hit:
                return GroupResolveResult(group=hit, matched_by='code', tried=tried)

            alias_code = _IMPORT_GROUP_ALIASES.get(_fold_code(raw)) or _IMPORT_GROUP_ALIASES.get(
                _fold_label(raw),
            )
            if alias_code:
                hit = self._by_code(alias_code)
                if hit:
                    return GroupResolveResult(group=hit, matched_by='alias', tried=tried)

            hit = self.by_name.get(_fold_label(raw)) or self.by_name.get(raw.casefold())
            if hit:
                return GroupResolveResult(group=hit, matched_by='name', tried=tried)

        if stage:
            hit = self.by_stage.get(_fold_label(stage)) or self.by_stage.get(stage.casefold())
            if hit:
                return GroupResolveResult(group=hit, matched_by='stage', tried=tried)

        if raw:
            folded_raw = _fold_label(raw)
            for key, grp in self.by_name.items():
                if folded_raw and (folded_raw in key or key in folded_raw):
                    return GroupResolveResult(group=grp, matched_by='name_partial', tried=tried)

        prefix = (op_code or '').strip().upper().split('-', 1)[0]
        prefix_map = {
            'SEW': 'MAY',
            'CUT': 'CAT',
            'CAT': 'CAT',
            'INEP': 'IN_EP',
            'IN': 'IN_EP',
            'THEU': 'THEU',
            'EMB': 'THEU',
            'HT': 'HT',
            'GH': 'GH',
        }
        alias_from_prefix = prefix_map.get(prefix)
        if alias_from_prefix:
            hit = self._by_code(alias_from_prefix)
            if hit:
                return GroupResolveResult(group=hit, matched_by='op_prefix', tried=tried)

        return GroupResolveResult(group=None, tried=tried)


def resolve_operation_group_for_import(
    group_code: str = '',
    *,
    stage_label: str = '',
    op_code: str = '',
    resolver: OperationGroupResolver | None = None,
) -> GroupResolveResult:
    if resolver is None:
        resolver = OperationGroupResolver.build()
    return resolver.resolve(group_code, stage_label=stage_label, op_code=op_code)


def rematch_operations_to_groups(
    *,
    dry_run: bool = False,
    only_auto: bool = False,
    excel_path: str = '',
) -> tuple[int, int, list[str]]:
    """Gán lại group cho SxOperation theo mã nhóm / khâu SX / mã CĐ."""
    from django.db import transaction

    from san_xuat.ie_models import SxOperation

    resolver = OperationGroupResolver.build()
    excel_map: dict[tuple[str, str], str] = {}
    warnings: list[str] = []

    if excel_path:
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError('Thiếu thư viện openpyxl.') from exc
        from san_xuat.services.operation_master import SHEET_LIB, _sheet_dicts, _s

        wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
        if SHEET_LIB not in wb.sheetnames:
            raise ValueError(f'Không thấy sheet {SHEET_LIB} trong file Excel.')
        for rec in _sheet_dicts(wb[SHEET_LIB]):
            op_code = _s(rec.get('MÃ CÔNG ĐOẠN'))
            if not op_code:
                continue
            op_rev = _s(rec.get('PHIÊN BẢN')) or 'R01'
            group_code = _s(rec.get('MÃ NHÓM'))
            if group_code:
                excel_map[(op_code, op_rev)] = group_code

    qs = SxOperation.objects.select_related('group').order_by('op_code', 'op_rev')
    if only_auto:
        qs = qs.filter(group__code__istartswith='AUTO-')

    checked = 0
    updated = 0
    with transaction.atomic():
        for op in qs:
            checked += 1
            current_code = (op.group.code if op.group_id else '').strip()
            source_code = excel_map.get((op.op_code, op.op_rev), current_code)
            stage_label = (op.process_stage_label or '').strip()
            resolved = resolver.resolve(
                source_code,
                stage_label=stage_label,
                op_code=op.op_code,
            )
            if not resolved.group or resolved.group.pk == op.group_id:
                continue
            updated += 1
            warnings.append(
                f'{op.op_code}/{op.op_rev}: {current_code or "—"} → {resolved.group.code} '
                f'({resolved.matched_by})',
            )
            if not dry_run:
                op.group = resolved.group
                op.save(update_fields=['group'])
        if dry_run:
            transaction.set_rollback(True)

    return checked, updated, warnings
