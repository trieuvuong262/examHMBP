"""Kiểm chứng hàm ghi sổ kho thành phẩm (kho_san_pham.services.stock).

Mọi thao tác nằm trong một transaction rồi rollback, nên không để lại dữ liệu.

    python scripts/verify_kho_sp_stock.py
    docker compose exec -T web python scripts/verify_kho_sp_stock.py
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from kho_san_pham.choices import (  # noqa: E402
    DOC_TYPE_FG_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_STOCKTAKE,
    MOVEMENT_ADJUST,
    MOVEMENT_PRODUCTION_IN,
    MOVEMENT_SALE_OUT,
    SOURCE_SYSTEM_PORTAL,
    SOURCE_SYSTEM_SALES,
    WAREHOUSE_OWNER_PORTAL,
    WAREHOUSE_OWNER_SALES,
    is_kv_sales_branch_name,
)
from kho_san_pham.models import (  # noqa: E402
    NegativeStockAlert,
    Product,
    StockLedger,
    Warehouse,
)
from kho_san_pham.services.stock import (  # noqa: E402
    RESULT_ALREADY_APPLIED,
    RESULT_APPLIED,
    StockMovementError,
    entries_missing_cost,
    get_qty_on_hand,
    post_movement,
    reverse_movement,
    set_catalog_qty,
    set_warehouse_qty,
)
from san_xuat.hub_models import (  # noqa: E402
    SxFgReceiptLine,
    SxFgReceiptRequest,
    SxProductionOrder,
    SxSku,
)
from san_xuat.services.fg_stock import FgStockError, post_fg_receipt_to_stock  # noqa: E402

PASSED = []
FAILED = []


def check(label, fn):
    try:
        fn()
    except AssertionError as exc:
        FAILED.append(f'{label}: {exc}')
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f'{label}: lỗi ngoài dự kiến {type(exc).__name__}: {exc}')
    else:
        PASSED.append(label)


def expect_error(fn, fragment):
    try:
        fn()
    except StockMovementError as exc:
        assert fragment in str(exc), f'thông báo lỗi thiếu {fragment!r}, nhận: {exc}'
        return
    raise AssertionError(f'đáng lẽ phải báo lỗi có {fragment!r} nhưng không lỗi')


class Fixture:
    """Kho và SKU dùng riêng cho lần kiểm chứng, tên có tiền tố dễ nhận."""

    def __init__(self):
        self.factory = Warehouse.objects.create(
            code='ZZ-VERIFY-XUONG', name='[verify] Kho xưởng', owner_system=WAREHOUSE_OWNER_PORTAL,
        )
        self.store = Warehouse.objects.create(
            code='ZZ-VERIFY-CH', name='[verify] Điểm bán', owner_system=WAREHOUSE_OWNER_SALES,
        )
        self.shirt = Product.objects.create(code='ZZ-VERIFY-TEE-M', name='[verify] Áo thun M')
        self.short = Product.objects.create(code='ZZ-VERIFY-SHRT-L', name='[verify] Quần short L')

        # SKU sản xuất nối vào shirt, để kiểm đường tìm sản phẩm qua FK SxSku
        self.sx_sku = SxSku.objects.create(
            style_code='ZZ-VERIFY-STYLE',
            color_code='ZZV',
            size_label='M',
            sku_code='ZZ-VERIFY-SXSKU-M',
        )
        self.shirt.sx_sku = self.sx_sku
        self.shirt.save(update_fields=['sx_sku'])

        self.mo = SxProductionOrder.objects.create(
            code='ZZ-VERIFY-LSX-001',
            product_code='ZZ-VERIFY-STYLE',
            product_name='[verify] Mã hàng kiểm chứng',
            qty=Decimal('100.00'),
            order_date=timezone.localdate(),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        self._fg_seq = 0

    def make_fg_receipt(self, rows, *, status='done', sku=None):
        """Tạo YCNTP kèm dòng. ``rows`` là danh sách ``(sku_code, qty)``."""
        self._fg_seq += 1
        req = SxFgReceiptRequest.objects.create(
            code=f'ZZ-VERIFY-YCNTP-{self._fg_seq:03d}',
            production_order=self.mo,
            request_date=timezone.localdate(),
            qty=sum((Decimal(q) for _, q in rows), Decimal('0')),
            status=status,
            warehouse=self.factory,
        )
        for sku_code, qty in rows:
            SxFgReceiptLine.objects.create(
                receipt=req,
                sku=sku,
                sku_code=sku_code,
                qty=Decimal(qty),
            )
        return req

    def receive(self, *, product=None, qty='100.00', doc_code='YCNTP-V1', line_no=1, warehouse=None,
                unit_cost='85000.00'):
        return post_movement(
            product=product or self.shirt,
            warehouse=warehouse or self.factory,
            kind=MOVEMENT_PRODUCTION_IN,
            qty_delta=Decimal(qty),
            unit_cost=None if unit_cost is None else Decimal(unit_cost),
            source_system=SOURCE_SYSTEM_PORTAL,
            source_doc_type=DOC_TYPE_FG_RECEIPT,
            source_doc_code=doc_code,
            source_line_no=line_no,
            occurred_at=timezone.now(),
        )

    def sell(self, *, qty='-2.00', doc_code='HD-V1', line_no=1, warehouse=None):
        return post_movement(
            product=self.shirt,
            warehouse=warehouse or self.store,
            kind=MOVEMENT_SALE_OUT,
            qty_delta=Decimal(qty),
            source_system=SOURCE_SYSTEM_SALES,
            source_doc_type=DOC_TYPE_INVOICE,
            source_doc_code=doc_code,
            source_line_no=line_no,
            occurred_at=timezone.now(),
        )

    def seed_store(self, qty='10.00', doc_code='KK-V-DAUKY'):
        return post_movement(
            product=self.shirt,
            warehouse=self.store,
            kind=MOVEMENT_ADJUST,
            qty_delta=Decimal(qty),
            source_system=SOURCE_SYSTEM_SALES,
            source_doc_type=DOC_TYPE_STOCKTAKE,
            source_doc_code=doc_code,
            occurred_at=timezone.now(),
        )


def run_checks():
    fx = Fixture()

    def sp_isolated(fn):
        """Chạy một kiểm tra trong savepoint riêng để nó không ảnh hưởng cái sau."""
        def wrapped():
            sid = transaction.savepoint()
            try:
                fn(fx)
            finally:
                transaction.savepoint_rollback(sid)
        return wrapped

    # ---- ghi bình thường

    def nhap_cong_ton(f):
        r = f.receive(qty='120.00')
        assert r.status == RESULT_APPLIED, r.status
        assert r.balance_after == Decimal('120.00'), r.balance_after
        assert not r.is_negative
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('120.00')
        entry = StockLedger.objects.get(pk=r.ledger_id)
        assert entry.balance_after == Decimal('120.00')
        assert entry.unit_cost == Decimal('85000.00')

    def cong_don_nhieu_phat_sinh(f):
        f.receive(qty='100.00', doc_code='YCNTP-V1')
        f.receive(qty='30.00', doc_code='YCNTP-V2')
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('130.00')
        after = list(
            StockLedger.objects.filter(product=f.shirt, warehouse=f.factory)
            .order_by('id').values_list('balance_after', flat=True)
        )
        assert after == [Decimal('100.00'), Decimal('130.00')], after

    def ton_tach_theo_kho(f):
        f.receive(qty='50.00')
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('50.00')
        assert get_qty_on_hand(f.shirt, f.store) == Decimal('0')

    # ---- chống trùng

    def gui_trung_khong_cong_hai_lan(f):
        first = f.receive(qty='100.00')
        second = f.receive(qty='100.00')
        assert first.status == RESULT_APPLIED
        assert second.status == RESULT_ALREADY_APPLIED, second.status
        assert second.ledger_id == first.ledger_id
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('100.00')

    def khac_dong_la_hai_phat_sinh(f):
        f.receive(qty='100.00', doc_code='YCNTP-V9', line_no=1)
        f.receive(product=f.short, qty='40.00', doc_code='YCNTP-V9', line_no=2)
        assert get_qty_on_hand(f.short, f.factory) == Decimal('40.00')

    def dung_lai_khoa_cho_sku_khac_bao_loi(f):
        f.receive(product=f.shirt, doc_code='YCNTP-VX', line_no=1)
        expect_error(
            lambda: f.receive(product=f.short, doc_code='YCNTP-VX', line_no=1),
            'nội dung khác',
        )
        assert get_qty_on_hand(f.short, f.factory) == Decimal('0')

    def dung_lai_khoa_so_luong_khac_bao_loi(f):
        f.receive(qty='100.00', doc_code='YCNTP-VY')
        expect_error(lambda: f.receive(qty='999.00', doc_code='YCNTP-VY'), 'số lượng đã ghi')
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('100.00')

    def hai_he_cung_so_chung_tu_khong_coi_la_trung(f):
        f.receive(doc_code='SO-TRUNG')
        f.seed_store()
        r = f.sell(qty='-1.00', doc_code='SO-TRUNG')
        assert r.status == RESULT_APPLIED, r.status

    # ---- chặn dữ liệu sai

    def xuat_mang_so_duong_bao_loi(f):
        expect_error(lambda: f.sell(qty='2.00'), 'phải âm')

    def nhap_mang_so_am_bao_loi(f):
        expect_error(lambda: f.receive(qty='-5.00'), 'phải dương')

    def so_luong_khong_bao_loi(f):
        expect_error(lambda: f.receive(qty='0.00'), 'khác 0')

    def thieu_gia_thanh_van_ghi_duoc(f):
        # Nhập kho không được chờ module giá thành: tồn vẫn ghi, giá để trống.
        r = f.receive(qty='10.00', unit_cost=None)
        assert r.status == RESULT_APPLIED
        entry = StockLedger.objects.get(pk=r.ledger_id)
        assert entry.unit_cost is None, entry.unit_cost
        assert entries_missing_cost().filter(pk=entry.pk).exists(), 'không truy ra được dòng thiếu giá'

    def gia_thanh_am_bao_loi(f):
        expect_error(lambda: f.receive(unit_cost='-1.00'), 'Giá thành không hợp lệ')

    def ban_hang_ghi_vao_kho_xuong_bao_loi(f):
        expect_error(lambda: f.sell(warehouse=f.factory), 'kho thuộc hệ')

    def nhap_vao_diem_ban_bao_loi(f):
        expect_error(lambda: f.receive(warehouse=f.store), 'kho thuộc hệ')

    def dieu_chinh_duoc_hai_chieu(f):
        f.seed_store(qty='10.00')
        r = post_movement(
            product=f.shirt, warehouse=f.store, kind=MOVEMENT_ADJUST,
            qty_delta=Decimal('-4.00'), source_system=SOURCE_SYSTEM_SALES,
            source_doc_type=DOC_TYPE_STOCKTAKE, source_doc_code='KK-V2',
            occurred_at=timezone.now(),
        )
        assert r.balance_after == Decimal('6.00'), r.balance_after

    # ---- tồn âm

    def ban_qua_ton_van_ghi_va_canh_bao(f):
        r = f.sell(qty='-3.00')
        assert r.status == RESULT_APPLIED
        assert r.is_negative
        assert r.balance_after == Decimal('-3.00')
        alert = NegativeStockAlert.objects.get(ledger_entry_id=r.ledger_id)
        assert alert.product_code == f.shirt.code
        assert alert.warehouse_code == f.store.code
        assert alert.balance_after == Decimal('-3.00')
        assert not alert.is_resolved

    def ban_trong_ton_khong_canh_bao(f):
        f.seed_store(qty='10.00')
        r = f.sell(qty='-4.00')
        assert not r.is_negative
        assert r.balance_after == Decimal('6.00'), r.balance_after
        assert not NegativeStockAlert.objects.filter(ledger_entry_id=r.ledger_id).exists()

    def gui_trung_am_khong_canh_bao_lan_hai(f):
        f.sell(qty='-3.00')
        f.sell(qty='-3.00')
        assert NegativeStockAlert.objects.count() == 1, NegativeStockAlert.objects.count()
        assert get_qty_on_hand(f.shirt, f.store) == Decimal('-3.00')

    # ---- bút toán đảo

    def but_toan_dao_tra_ton_giu_dong_cu(f):
        first = f.receive(qty='100.00')
        entry = StockLedger.objects.get(pk=first.ledger_id)
        r = reverse_movement(entry, reason='Ghi sai số lượng')
        assert r.status == RESULT_APPLIED
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('0.00')
        assert StockLedger.objects.filter(pk=entry.pk).exists(), 'dòng cũ bị mất'

    def but_toan_dao_phai_co_ly_do(f):
        first = f.receive()
        entry = StockLedger.objects.get(pk=first.ledger_id)
        expect_error(lambda: reverse_movement(entry, reason='   '), 'lý do')

    # ---- luồng YCNTP (san_xuat) -> tồn thành phẩm

    def ycntp_ghi_ton_tung_dong(f):
        req = f.make_fg_receipt([(f.shirt.code, '20.00'), (f.short.code, '30.00')])
        result = post_fg_receipt_to_stock(req)
        assert result.posted == 2, result.posted
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('20.00')
        assert get_qty_on_hand(f.short, f.factory) == Decimal('30.00')

    def ycntp_ghi_dung_kho_va_ngay_phieu(f):
        req = f.make_fg_receipt([(f.shirt.code, '5.00')])
        result = post_fg_receipt_to_stock(req)
        entry = StockLedger.objects.get(source_doc_code=req.code)
        assert entry.warehouse_id == f.factory.pk, 'ghi sai kho'
        # occurred_at lưu 00:00 giờ địa phương -> phải so theo giờ địa phương,
        # đọc thô ra UTC sẽ lùi một ngày.
        local_date = timezone.localtime(entry.occurred_at).date()
        assert local_date == req.request_date, f'occurred_at {local_date} != ngày phiếu {req.request_date}'
        assert entry.source_doc_type == 'fg_receipt'
        assert entry.source_system == 'portal'
        assert result.posted == 1

    def ycntp_goi_lai_khong_cong_ton_hai_lan(f):
        req = f.make_fg_receipt([(f.shirt.code, '20.00')])
        post_fg_receipt_to_stock(req)
        second = post_fg_receipt_to_stock(req)
        assert second.posted == 0, second.posted
        assert second.already == 1, second.already
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('20.00')

    def ycntp_chua_hoan_thanh_thi_bao_loi(f):
        req = f.make_fg_receipt([(f.shirt.code, '10.00')], status='draft')
        try:
            post_fg_receipt_to_stock(req)
        except FgStockError as exc:
            assert 'hoàn thành' in str(exc), exc
            return
        raise AssertionError('đáng lẽ phải chặn phiếu chưa hoàn thành')

    def ycntp_sku_khong_co_trong_danh_muc_bao_loi(f):
        req = f.make_fg_receipt([('ZZ-VERIFY-KHONG-TON-TAI', '10.00')])
        try:
            post_fg_receipt_to_stock(req)
        except FgStockError as exc:
            assert 'không có trong kho sản phẩm' in str(exc), exc
            assert StockLedger.objects.filter(source_doc_code=req.code).count() == 0
            return
        raise AssertionError('đáng lẽ phải chặn SKU lạ')

    def ycntp_khong_co_dong_thi_bao_loi(f):
        req = f.make_fg_receipt([])
        try:
            post_fg_receipt_to_stock(req)
        except FgStockError as exc:
            assert 'không có dòng SKU' in str(exc), exc
            return
        raise AssertionError('đáng lẽ phải chặn phiếu không có dòng')

    def ycntp_bo_qua_dong_so_luong_khong(f):
        req = f.make_fg_receipt([(f.shirt.code, '15.00'), (f.short.code, '0.00')])
        result = post_fg_receipt_to_stock(req)
        assert result.posted == 1, result.posted
        assert get_qty_on_hand(f.short, f.factory) == Decimal('0')

    def ycntp_khong_co_gia_thanh_van_ghi(f):
        req = f.make_fg_receipt([(f.shirt.code, '12.00')])
        result = post_fg_receipt_to_stock(req)
        entry = StockLedger.objects.get(source_doc_code=req.code)
        # Mã hàng của LSX kiểm chứng không có trong bảng giá định mức
        assert entry.unit_cost is None, entry.unit_cost
        assert result.missing_cost == 1, result.missing_cost
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('12.00')

    def _set_require_kv(value: bool):
        from san_xuat.hub_models import SxGeneralSettings

        cfg = SxGeneralSettings.load()
        cfg.require_kv_link_for_fg_done = value
        cfg.save(update_fields=['require_kv_link_for_fg_done'])

    def submit_khong_bat_buoc_kv_thi_ghi_ton_luon(f):
        from san_xuat.services.dispatch import submit_fg_receipt

        _set_require_kv(False)
        req = f.make_fg_receipt([(f.shirt.code, '25.00')], status='draft')
        req = submit_fg_receipt(request_id=req.pk)
        assert req.status == SxFgReceiptRequest.STATUS_DONE, req.status
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('25.00'), 'móc nối vào sổ kho không chạy'

    def submit_bat_buoc_kv_thi_chua_ghi_ton(f):
        from san_xuat.services.dispatch import submit_fg_receipt

        _set_require_kv(True)
        req = f.make_fg_receipt([(f.shirt.code, '25.00')], status='draft')
        req = submit_fg_receipt(request_id=req.pk)
        assert req.status == SxFgReceiptRequest.STATUS_SUBMITTED, req.status
        # Chưa hoàn thành thì tuyệt đối chưa được cộng tồn
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('0'), 'ghi tồn quá sớm'

    def submit_sku_la_thi_khong_chuyen_done(f):
        from san_xuat.services.dispatch import DispatchError, submit_fg_receipt

        _set_require_kv(False)
        req = f.make_fg_receipt([('ZZ-VERIFY-KHONG-TON-TAI', '9.00')], status='draft')
        try:
            submit_fg_receipt(request_id=req.pk)
        except DispatchError:
            # Cả việc chuyển trạng thái phải bị hủy theo, không được để phiếu
            # done mà tồn không tăng.
            req.refresh_from_db()
            assert req.status == SxFgReceiptRequest.STATUS_DRAFT, req.status
            return
        raise AssertionError('đáng lẽ phải chặn và giữ phiếu ở nháp')

    def ycntp_noi_qua_sx_sku_khi_co_fk(f):
        req = f.make_fg_receipt([('SAI-MA-HOAN-TOAN', '7.00')], sku=f.sx_sku)
        result = post_fg_receipt_to_stock(req)
        # sku_code sai nhưng FK SxSku đúng -> vẫn tìm ra sản phẩm
        assert result.posted == 1, result.posted
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('7.00')

    def danh_muc_bam_ton_xuong_sau_nhap(f):
        f.receive(qty='40.00')
        f.shirt.refresh_from_db()
        assert f.shirt.qty_on_hand == Decimal('40.00'), f.shirt.qty_on_hand

    def ban_hang_khong_doi_ton_danh_muc(f):
        f.receive(qty='40.00')
        f.seed_store(qty='10.00')
        f.sell(qty='-4.00')
        f.shirt.refresh_from_db()
        assert f.shirt.qty_on_hand == Decimal('40.00'), f.shirt.qty_on_hand

    def nhap_ton_danh_muc_ghi_so(f):
        set_catalog_qty(f.shirt, Decimal('25.00'), warehouse=f.factory)
        f.shirt.refresh_from_db()
        assert f.shirt.qty_on_hand == Decimal('25.00')
        assert get_qty_on_hand(f.shirt, f.factory) == Decimal('25.00')

    def nhap_ton_danh_muc_giong_so_thi_bo_qua(f):
        set_catalog_qty(f.shirt, Decimal('25.00'), warehouse=f.factory)
        second = set_catalog_qty(f.shirt, Decimal('25.00'), warehouse=f.factory)
        assert second is None
        assert StockLedger.objects.filter(source_doc_type='stocktake').count() == 1

    def nhap_ton_danh_muc_am_bao_loi(f):
        expect_error(lambda: set_catalog_qty(f.shirt, Decimal('-1'), warehouse=f.factory), 'không được âm')

    def nhap_ton_cua_hang_khong_doi_danh_muc(f):
        f.receive(qty='40.00')
        set_warehouse_qty(f.shirt, Decimal('12.00'), warehouse=f.store)
        f.shirt.refresh_from_db()
        assert f.shirt.qty_on_hand == Decimal('40.00'), f.shirt.qty_on_hand
        assert get_qty_on_hand(f.shirt, f.store) == Decimal('12.00')

    def nhap_ton_cua_hang_cho_phep_am(f):
        set_warehouse_qty(f.shirt, Decimal('-3.00'), warehouse=f.store)
        assert get_qty_on_hand(f.shirt, f.store) == Decimal('-3.00')

    def nhan_chi_nhanh_kv_cua_hang(f):
        assert is_kv_sales_branch_name('Chi nhánh trung tâm')
        assert is_kv_sales_branch_name('Kho bán hàng')
        assert not is_kv_sales_branch_name('Xưởng sản xuất')
        assert not is_kv_sales_branch_name('Đơn sản xuất')
        assert not is_kv_sales_branch_name('Kho sản xuất 19 CL')

    cases = [
        ('nhập thành phẩm cộng tồn và ghi sổ', nhap_cong_ton),
        ('nhiều phát sinh cộng dồn, balance_after bám theo', cong_don_nhieu_phat_sinh),
        ('tồn tách riêng theo kho', ton_tach_theo_kho),
        ('gửi trùng không cộng tồn lần hai', gui_trung_khong_cong_hai_lan),
        ('cùng số chứng từ khác dòng là hai phát sinh', khac_dong_la_hai_phat_sinh),
        ('dùng lại khóa cho SKU khác thì báo lỗi', dung_lai_khoa_cho_sku_khac_bao_loi),
        ('dùng lại khóa với số lượng khác thì báo lỗi', dung_lai_khoa_so_luong_khac_bao_loi),
        ('hai hệ cùng số chứng từ không coi là trùng', hai_he_cung_so_chung_tu_khong_coi_la_trung),
        ('xuất bán mang số dương thì báo lỗi', xuat_mang_so_duong_bao_loi),
        ('nhập mang số âm thì báo lỗi', nhap_mang_so_am_bao_loi),
        ('số lượng bằng 0 thì báo lỗi', so_luong_khong_bao_loi),
        ('thiếu giá thành vẫn ghi tồn, truy ra được để điền bù', thieu_gia_thanh_van_ghi_duoc),
        ('giá thành âm thì báo lỗi', gia_thanh_am_bao_loi),
        ('bán hàng không ghi được vào kho xưởng', ban_hang_ghi_vao_kho_xuong_bao_loi),
        ('nhập thành phẩm không ghi được vào điểm bán', nhap_vao_diem_ban_bao_loi),
        ('điều chỉnh đi được cả hai chiều', dieu_chinh_duoc_hai_chieu),
        ('bán quá tồn vẫn ghi và tạo cảnh báo', ban_qua_ton_van_ghi_va_canh_bao),
        ('bán trong tồn thì không cảnh báo', ban_trong_ton_khong_canh_bao),
        ('gửi trùng phát sinh âm không cảnh báo lần hai', gui_trung_am_khong_canh_bao_lan_hai),
        ('bút toán đảo trả tồn về, giữ dòng cũ', but_toan_dao_tra_ton_giu_dong_cu),
        ('bút toán đảo phải có lý do', but_toan_dao_phai_co_ly_do),
        ('YCNTP ghi tồn cho từng dòng', ycntp_ghi_ton_tung_dong),
        ('YCNTP ghi đúng kho và ngày phiếu', ycntp_ghi_dung_kho_va_ngay_phieu),
        ('YCNTP gọi lại không cộng tồn hai lần', ycntp_goi_lai_khong_cong_ton_hai_lan),
        ('YCNTP chưa hoàn thành thì chặn', ycntp_chua_hoan_thanh_thi_bao_loi),
        ('YCNTP có SKU lạ thì chặn, không ghi gì', ycntp_sku_khong_co_trong_danh_muc_bao_loi),
        ('YCNTP không có dòng thì chặn', ycntp_khong_co_dong_thi_bao_loi),
        ('YCNTP bỏ qua dòng số lượng 0', ycntp_bo_qua_dong_so_luong_khong),
        ('YCNTP không có giá thành vẫn ghi tồn', ycntp_khong_co_gia_thanh_van_ghi),
        ('YCNTP nối qua FK SxSku khi sku_code sai', ycntp_noi_qua_sx_sku_khi_co_fk),
        ('gửi YCNTP (không bắt buộc KV) ghi tồn luôn', submit_khong_bat_buoc_kv_thi_ghi_ton_luon),
        ('gửi YCNTP (bắt buộc KV) chưa ghi tồn', submit_bat_buoc_kv_thi_chua_ghi_ton),
        ('gửi YCNTP có SKU lạ thì giữ phiếu ở nháp', submit_sku_la_thi_khong_chuyen_done),
        ('danh mục bám tồn xưởng sau nhập thành phẩm', danh_muc_bam_ton_xuong_sau_nhap),
        ('bán hàng không đổi tồn trên danh mục', ban_hang_khong_doi_ton_danh_muc),
        ('nhập tồn danh mục ghi sổ và cột Product', nhap_ton_danh_muc_ghi_so),
        ('nhập tồn danh mục giống số thì bỏ qua', nhap_ton_danh_muc_giong_so_thi_bo_qua),
        ('nhập tồn danh mục âm thì báo lỗi', nhap_ton_danh_muc_am_bao_loi),
        ('nhập tồn cửa hàng không đổi cột danh mục', nhap_ton_cua_hang_khong_doi_danh_muc),
        ('nhập tồn cửa hàng cho phép âm', nhap_ton_cua_hang_cho_phep_am),
        ('nhận chi nhánh KV cửa hàng vs xưởng', nhan_chi_nhanh_kv_cua_hang),
    ]

    for label, fn in cases:
        check(label, sp_isolated(fn))


def main():
    with transaction.atomic():
        run_checks()
        transaction.set_rollback(True)

    for label in PASSED:
        print(f'  OK   {label}')
    for label in FAILED:
        print(f'  FAIL {label}')
    print(f'\n{len(PASSED)} đạt / {len(FAILED)} lỗi')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
