"""Ghi sổ kho thành phẩm.

``post_movement`` là **đường ghi tồn duy nhất**. Có một chỗ nào cập nhật
``StockBalance`` trực tiếp là mất luôn bảo đảm ``balance_after`` trong sổ khớp
với số dư.

Thiết kế: docs/integrations/central-product/inventory-schema.md
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from kho_san_pham.choices import (
    MOVEMENT_ADJUST,
    MOVEMENT_DIRECTION,
    MOVEMENT_PRODUCTION_IN,
    MOVEMENT_SALE_OUT,
    MOVEMENT_SALE_RETURN_IN,
    WAREHOUSE_OWNER_PORTAL,
    WAREHOUSE_OWNER_SALES,
)
from kho_san_pham.models import NegativeStockAlert, StockBalance, StockLedger, Warehouse

RESULT_APPLIED = 'applied'
RESULT_ALREADY_APPLIED = 'already_applied'

# Loại phát sinh chỉ hợp lệ ở kho do một hệ nhất định sở hữu. Chuyển kho và
# điều chỉnh cố ý để trống: chuyển kho hợp lệ ở cả hai đầu, còn điều chỉnh thì
# người vận hành nào cũng có thể phải làm.
MOVEMENT_REQUIRED_OWNER = {
    MOVEMENT_PRODUCTION_IN: WAREHOUSE_OWNER_PORTAL,
    MOVEMENT_SALE_OUT: WAREHOUSE_OWNER_SALES,
    MOVEMENT_SALE_RETURN_IN: WAREHOUSE_OWNER_SALES,
}


class StockMovementError(Exception):
    """Phát sinh không hợp lệ — cần người sửa, không phải lỗi tạm thời.

    Bên gửi nhận lỗi này thì **không** được thử lại y nguyên: gửi lại cũng sai.
    """


@dataclass(frozen=True)
class MovementResult:
    status: str
    balance_after: Decimal
    ledger_id: int
    is_negative: bool

    @property
    def was_applied(self) -> bool:
        return self.status == RESULT_APPLIED


def _describe_conflicts(existing: StockLedger, *, product, warehouse, kind, qty_delta) -> list[str]:
    """Những điểm khác nhau giữa phát sinh đang gửi và dòng đã ghi cùng khóa."""
    conflicts = []
    if existing.product_id != product.pk:
        conflicts.append(f'SKU đã ghi là {existing.product.code}, đang gửi {product.code}')
    if existing.warehouse_id != warehouse.pk:
        conflicts.append(f'kho đã ghi là {existing.warehouse.code}, đang gửi {warehouse.code}')
    if existing.kind != kind:
        conflicts.append(f'loại đã ghi là {existing.kind}, đang gửi {kind}')
    if existing.qty_delta != qty_delta:
        conflicts.append(f'số lượng đã ghi là {existing.qty_delta}, đang gửi {qty_delta}')
    return conflicts


def _validate(*, kind, qty_delta, unit_cost, warehouse, occurred_at):
    if kind not in MOVEMENT_DIRECTION:
        raise StockMovementError(f'Loại phát sinh không hợp lệ: {kind!r}.')
    if occurred_at is None:
        raise StockMovementError('Thiếu thời điểm phát sinh (occurred_at).')
    if qty_delta is None or qty_delta == 0:
        raise StockMovementError('Số lượng biến động phải khác 0.')

    direction = MOVEMENT_DIRECTION[kind]
    if direction > 0 and qty_delta < 0:
        raise StockMovementError(f'{kind}: là phát sinh nhập nên số lượng phải dương (nhận {qty_delta}).')
    if direction < 0 and qty_delta > 0:
        raise StockMovementError(f'{kind}: là phát sinh xuất nên số lượng phải âm (nhận {qty_delta}).')

    required_owner = MOVEMENT_REQUIRED_OWNER.get(kind)
    if required_owner and warehouse.owner_system != required_owner:
        raise StockMovementError(
            f'{kind}: không ghi được vào kho {warehouse.code} '
            f'(kho thuộc hệ {warehouse.owner_system}, cần {required_owner}).'
        )

    # Không bắt buộc có giá thành: nhập kho không được chờ module giá thành.
    # ``None`` = chưa biết giá, khác hẳn 0 = miễn phí. Giữ được phân biệt này thì
    # sau còn truy ra dòng nào cần điền bù; ghi 0 cho "chưa biết" là dữ liệu sai.
    if unit_cost is not None and unit_cost < 0:
        raise StockMovementError(f'Giá thành không hợp lệ: {unit_cost}.')


@transaction.atomic
def post_movement(
    *,
    product,
    warehouse: Warehouse,
    kind: str,
    qty_delta: Decimal,
    source_system: str,
    source_doc_type: str,
    source_doc_code: str,
    occurred_at,
    source_line_no: int = 1,
    unit_cost: Decimal | None = None,
    created_by=None,
    actor: str = '',
    notes: str = '',
) -> MovementResult:
    """Ghi một phát sinh vào sổ kho và cập nhật số dư.

    Gọi lại với cùng bộ khóa ``source_*`` sẽ trả về ``already_applied`` mà không
    cộng tồn lần hai — bên gửi cứ thử lại thoải mái khi mạng lỗi.

    Raises:
        StockMovementError: phát sinh không hợp lệ (bên gửi phải sửa rồi mới gửi lại).
    """
    _validate(
        kind=kind,
        qty_delta=qty_delta,
        unit_cost=unit_cost,
        warehouse=warehouse,
        occurred_at=occurred_at,
    )

    source_key = {
        'source_system': source_system,
        'source_doc_type': source_doc_type,
        'source_doc_code': source_doc_code,
        'source_line_no': source_line_no,
    }

    # Khóa dòng số dư TRƯỚC khi kiểm chống trùng. Hai request đẩy trùng cùng một
    # phát sinh thì nhất thiết cùng (SKU, kho), nên chúng tuần tự hóa ở đây —
    # kiểm sau khi có khóa mới thấy được dòng mà request kia vừa ghi.
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        product=product,
        warehouse=warehouse,
        defaults={'qty_on_hand': Decimal('0')},
    )

    existing = StockLedger.objects.filter(**source_key).first()
    if existing is not None:
        # Cùng khóa nhưng khác nội dung nghĩa là bên gửi dùng lại số chứng từ cho
        # một phát sinh khác — không phải gửi trùng. Trả "đã ghi" ở đây là âm
        # thầm làm mất phát sinh mới, nên phải báo lỗi.
        conflicts = _describe_conflicts(
            existing,
            product=product,
            warehouse=warehouse,
            kind=kind,
            qty_delta=qty_delta,
        )
        if conflicts:
            raise StockMovementError(
                f'Chứng từ {source_doc_code}#{source_line_no} ({source_system}/{source_doc_type}) '
                f'đã ghi với nội dung khác: {"; ".join(conflicts)}. '
                'Mỗi dòng chứng từ phải có số riêng.'
            )
        return MovementResult(
            status=RESULT_ALREADY_APPLIED,
            balance_after=existing.balance_after,
            ledger_id=existing.pk,
            is_negative=existing.balance_after < 0,
        )

    balance.qty_on_hand += qty_delta
    balance.save(update_fields=['qty_on_hand', 'updated_at'])

    try:
        with transaction.atomic():
            entry = StockLedger.objects.create(
                product=product,
                warehouse=warehouse,
                kind=kind,
                qty_delta=qty_delta,
                balance_after=balance.qty_on_hand,
                unit_cost=unit_cost,
                occurred_at=occurred_at,
                created_by=created_by,
                actor=(actor or '').strip(),
                notes=(notes or '').strip(),
                **source_key,
            )
    except IntegrityError as exc:
        # Đã giữ khóa số dư và đã kiểm chống trùng, nên tới đây chỉ còn một khả
        # năng: bên gửi dùng lại cùng số chứng từ cho một SKU hoặc kho khác.
        # Đó là dữ liệu sai, không phải gửi trùng — báo rõ thay vì âm thầm bỏ qua.
        raise StockMovementError(
            f'Chứng từ {source_doc_code}#{source_line_no} ({source_system}/{source_doc_type}) '
            f'đã dùng cho một SKU hoặc kho khác. Số chứng từ phải là duy nhất cho mỗi dòng.'
        ) from exc

    is_negative = balance.qty_on_hand < 0
    if is_negative:
        NegativeStockAlert.objects.create(
            ledger_entry=entry,
            product_code=product.code,
            warehouse_code=warehouse.code,
            balance_after=balance.qty_on_hand,
        )

    return MovementResult(
        status=RESULT_APPLIED,
        balance_after=balance.qty_on_hand,
        ledger_id=entry.pk,
        is_negative=is_negative,
    )


def get_qty_on_hand(product, warehouse) -> Decimal:
    """Tồn hiện tại. Trả 0 khi chưa có phát sinh nào."""
    balance = StockBalance.objects.filter(product=product, warehouse=warehouse).only('qty_on_hand').first()
    return balance.qty_on_hand if balance else Decimal('0')


def entries_missing_cost():
    """Phát sinh nhập thành phẩm chưa có giá thành — cần điền bù.

    Tồn kho vẫn đúng khi thiếu giá; chỉ giá vốn là chưa tính được. Hàm này để
    những dòng đó không biến mất khỏi tầm nhìn.
    """
    return (
        StockLedger.objects
        .filter(kind=MOVEMENT_PRODUCTION_IN, unit_cost__isnull=True)
        .select_related('product', 'warehouse')
    )


@transaction.atomic
def reverse_movement(
    entry: StockLedger,
    *,
    reason: str,
    created_by=None,
) -> MovementResult:
    """Ghi bút toán đảo cho một phát sinh đã ghi sai.

    Sổ kho là chỉ-ghi-thêm nên không sửa và không xóa dòng cũ: dòng sai vẫn nằm
    đó, kèm một dòng ngược chiều. Mất lịch sử là mất khả năng giải thích vì sao
    tồn ra con số hiện tại.
    """
    if not reason.strip():
        raise StockMovementError('Bút toán đảo phải có lý do.')

    return post_movement(
        product=entry.product,
        warehouse=entry.warehouse,
        kind=MOVEMENT_ADJUST,
        qty_delta=-entry.qty_delta,
        source_system=entry.source_system,
        source_doc_type=entry.source_doc_type,
        source_doc_code=f'{entry.source_doc_code}~REV',
        source_line_no=entry.source_line_no,
        occurred_at=entry.occurred_at,
        created_by=created_by,
        actor=entry.actor,
        notes=f'Đảo {entry.source_doc_code}#{entry.source_line_no}: {reason.strip()}'[:255],
    )
