"""
Xóa dữ liệu test BICH01-2026 (do seed_bich01_stock_card tạo) mà không ảnh hưởng
phiếu do user tạo.

- Chỉ đụng đến các phiếu có số chứa 'BICH01-2026' (PN/PX/PC/PH/KK/DC-BICH01-2026-xxx).
- Hoàn trả tồn kho theo đúng các dòng sổ kho của những phiếu này rồi mới xóa.
- Mặc định chạy thử (dry-run) chỉ liệt kê; thêm --apply mới xóa thật.
- Nếu việc trừ tồn làm số dư âm thì dừng và rollback toàn bộ.

Cách chạy trên VPS:
    python manage.py cleanup_bich01_stock_card            # xem trước
    python manage.py cleanup_bich01_stock_card --apply    # xóa thật
"""

from collections import defaultdict
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kho_npl.models import (
    NplDocAttachment,
    StockAdjustment,
    StockBalance,
    StockDisposal,
    StockIssue,
    StockLedger,
    StockReceipt,
    StockTransfer,
    Stocktake,
)

PATTERN = 'BICH01-2026'
DOC_MODELS = (StockReceipt, StockIssue, StockTransfer, StockDisposal, Stocktake, StockAdjustment)


class Command(BaseCommand):
    help = "Xoa phieu test BICH01-2026 va hoan tra ton kho (mac dinh dry-run, them --apply de xoa that)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Xoa that (mac dinh chi liet ke).')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        with transaction.atomic():
            self._run(apply_changes)
            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    'DRY-RUN: chua xoa gi. Chay lai voi --apply de xoa that.'
                ))
            else:
                self.stdout.write(self.style.SUCCESS('Da xoa xong du lieu test BICH01-2026.'))

    def _run(self, apply_changes: bool):
        ledger = list(StockLedger.objects.filter(ref_number__contains=PATTERN))
        self.stdout.write(f'Dong so kho se xoa: {len(ledger)}')

        deltas: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for entry in ledger:
            deltas[(entry.material_id, entry.location_id)] += entry.qty_delta

        for (material_id, location_id), delta in sorted(deltas.items()):
            balance = StockBalance.objects.select_for_update().filter(
                material_id=material_id, location_id=location_id,
            ).first()
            before = balance.quantity if balance else Decimal('0')
            after = before - delta
            self.stdout.write(
                f'Ton material={material_id} location={location_id}: {before} -> {after}'
            )
            if after < 0:
                raise CommandError(
                    'Hoan tra se lam ton am (phieu user da dung hang test?). '
                    'Da rollback, khong xoa gi ca.'
                )
            if balance:
                balance.quantity = after
                balance.save(update_fields=['quantity', 'updated_at'])

        StockLedger.objects.filter(pk__in=[entry.pk for entry in ledger]).delete()

        for model in DOC_MODELS:
            docs = list(model.objects.filter(number__contains=PATTERN))
            if not docs:
                continue
            doc_pks = [doc.pk for doc in docs]
            content_type = ContentType.objects.get_for_model(model)
            attachment_qs = NplDocAttachment.objects.filter(
                content_type=content_type, object_id__in=doc_pks,
            )
            attachment_files = [att.file for att in attachment_qs if att.file]
            attachment_count = attachment_qs.count()
            attachment_qs.delete()
            direct_files = [doc.attachment for doc in docs if getattr(doc, 'attachment', None)]

            for doc in docs:
                self.stdout.write(f'  Xoa {model.__name__} {doc.number}')
            result = model.objects.filter(pk__in=doc_pks).delete()

            # Xóa file vật lý (storage không rollback được — chỉ làm khi --apply)
            if apply_changes:
                for file_field in attachment_files + direct_files:
                    file_field.delete(save=False)
            self.stdout.write(
                f'{model.__name__}: {len(docs)} phieu, {attachment_count} chung tu dinh kem, deleted={result}'
            )
