"""Điều kiện Go đọc từ hồ sơ thiết kế, sản xuất, kho và kênh bán. Không nhập lại số liệu."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace

from django.db.models import Count
from django.db.models.functions import Upper
from django.utils import timezone

from kho_san_pham.models import Product
from san_xuat.models import BomVersion, CostingSnapshot, SxProductionOrder, SxProductStockPolicy, TechDocDesignFile
from thiet_ke_sp.models import Attachment, Colorway, DesignVersion, SampleVersion, TechnicalPack
from thiet_ke_sp.models import Status as DossierStatus

from .models import CLOSED_TASK_STATUSES, LaunchRisk, RiskSeverity, TaskGroup

VIDEO_EXT = ('.mp4', '.mov', '.webm', '.m4v', '.avi')
IMAGE_KINDS = frozenset({'front', 'colorway', 'sample_photo', 'product_photo'})
PRICE_OK_STATUSES = frozenset({
    DossierStatus.APPROVED, DossierStatus.HANDED_OVER, DossierStatus.CLOSED,
})
MO_STARTED = frozenset({
    SxProductionOrder.STATUS_RELEASED,
    SxProductionOrder.STATUS_IN_PROGRESS,
    SxProductionOrder.STATUS_DONE,
})


def _join(parts: list[str]) -> str:
    text = '; '.join(parts[:6])
    if len(parts) > 6:
        text += f' … (+{len(parts) - 6})'
    return text


def _is_video(name: str) -> bool:
    lower = (name or '').lower()
    return lower.endswith(VIDEO_EXT)


def _empty_fact() -> SimpleNamespace:
    return SimpleNamespace(
        design_label='Chưa có', sample_label='Chưa có', colorways='—',
        techpack_label='Chưa có', bom_label='Chưa có', cost=None, cost_label='Chưa khóa',
        sku_count=0, barcode_count=0, retail=None, wholesale=None,
        stock=Decimal('0'), stock_min=None, mo_label='Chưa có lệnh sản xuất',
        image_ok=False, video_ok=False, content_ok=False,
        channel_label='Chưa tạo trên kênh bán', kiot_count=0,
        design_gap='', lock_gap='', price_gap='', mo_gap='', stock_gap='', media_gap='', channel_gap='',
    )


def _load_links(plan):
    return list(plan.products.select_related(
        'dossier__approved_design_version',
        'dossier__final_sample_version',
        'dossier__handover__tech_doc',
    ))


def build_facts(links) -> dict[int, SimpleNamespace]:
    dossiers = [link.dossier for link in links]
    facts = {d.pk: _empty_fact() for d in dossiers}
    if not dossiers:
        return facts

    version_ids = [d.approved_design_version_id for d in dossiers if d.approved_design_version_id]
    sample_ids = [d.final_sample_version_id for d in dossiers if d.final_sample_version_id]
    colorways: dict[int, list[str]] = defaultdict(list)
    if version_ids:
        for name, version_id in Colorway.objects.filter(design_version_id__in=version_ids).values_list('name', 'design_version_id'):
            colorways[version_id].append(name)
    packs = {}
    if sample_ids:
        packs = {
            pack.sample_version_id: pack
            for pack in TechnicalPack.objects.filter(sample_version_id__in=sample_ids).annotate(line_count=Count('material_lines'))
        }

    codes = sorted({(d.official_product_code or '').strip().upper() for d in dossiers} - {''})
    skus: dict[str, list] = defaultdict(list)
    if codes:
        for row in (
            Product.objects.annotate(style_u=Upper('style_code'))
            .filter(style_u__in=codes)
            .values('style_u', 'qty_on_hand', 'base_price', 'bar_code', 'kiotviet_id', 'allows_sale', 'description', 'image', 'image_url')
        ):
            skus[row['style_u']].append(row)

    tech_ids = []
    dossier_by_tech: dict[int, int] = {}
    for dossier in dossiers:
        handover = getattr(dossier, 'handover', None)
        if handover is not None and handover.tech_doc_id:
            tech_ids.append(handover.tech_doc_id)
            dossier_by_tech[handover.tech_doc_id] = dossier.pk
    boms: dict[int, list] = defaultdict(list)
    snap_cost: dict[int, Decimal] = {}
    if tech_ids:
        for bom in BomVersion.objects.filter(tech_doc_id__in=tech_ids, status=BomVersion.STATUS_ACTIVE).annotate(snap_count=Count('costing_snapshots')):
            boms[bom.tech_doc_id].append(bom)
        for snap in (
            CostingSnapshot.objects.filter(bom__tech_doc_id__in=tech_ids, bom__status=BomVersion.STATUS_ACTIVE)
            .select_related('bom').order_by('-created_at')
        ):
            snap_cost.setdefault(snap.bom.tech_doc_id, snap.total_cost)

    orders: dict[str, list] = defaultdict(list)
    policies = {}
    if codes:
        for order in (
            SxProductionOrder.objects.annotate(code_u=Upper('product_code'))
            .filter(code_u__in=codes)
            .exclude(status=SxProductionOrder.STATUS_CANCELLED)
            .exclude(is_sample=True)
        ):
            orders[(order.product_code or '').strip().upper()].append(order)
        policies = {
            row.code_u: row
            for row in SxProductStockPolicy.objects.annotate(code_u=Upper('product_code')).filter(code_u__in=codes, is_active=True)
        }

    images: dict[int, bool] = defaultdict(bool)
    videos: dict[int, bool] = defaultdict(bool)
    for dossier_id, kind, original_name, file_name in Attachment.objects.filter(
        dossier_id__in=facts, is_deleted=False, is_current=True,
    ).values_list('dossier_id', 'kind', 'original_name', 'file'):
        if kind in IMAGE_KINDS:
            images[dossier_id] = True
        if _is_video(original_name) or _is_video(file_name):
            videos[dossier_id] = True
    gallery: dict[int, bool] = defaultdict(bool)
    if tech_ids:
        for tech_id, file_name, purpose in TechDocDesignFile.objects.filter(tech_doc_id__in=tech_ids).values_list('tech_doc_id', 'file', 'purpose'):
            dossier_id = dossier_by_tech.get(tech_id)
            if not dossier_id:
                continue
            if purpose == TechDocDesignFile.PURPOSE_GALLERY or not _is_video(file_name):
                if purpose == TechDocDesignFile.PURPOSE_GALLERY:
                    gallery[dossier_id] = True
            if _is_video(file_name):
                videos[dossier_id] = True

    today = timezone.localdate()
    for link in links:
        dossier = link.dossier
        fact = facts[dossier.pk]
        code = (dossier.official_product_code or '').strip().upper()
        version = dossier.approved_design_version
        sample = dossier.final_sample_version
        reopening = dossier.status == DossierStatus.LIBRARY_REOPEN
        if version is not None:
            fact.design_label = f'{version.label} · {version.get_state_display()}'
        if sample is not None:
            fact.sample_label = f'{sample.label} · {sample.get_state_display()}'
        names = colorways.get(dossier.approved_design_version_id) or []
        if names:
            fact.colorways = ', '.join(names[:8])
        design_ok = version is not None and version.state == DesignVersion.STATE_APPROVED and not reopening
        sample_ok = sample is not None and sample.state == SampleVersion.STATE_PASSED and not reopening
        if reopening:
            fact.design_gap = 'đang chỉnh sau hoàn thành'
        elif not design_ok and not sample_ok:
            fact.design_gap = 'chưa duyệt thiết kế và mẫu chuẩn'
        elif not design_ok:
            fact.design_gap = 'thiết kế chưa duyệt'
        elif not sample_ok:
            fact.design_gap = 'mẫu chuẩn chưa đạt'

        handover = getattr(dossier, 'handover', None)
        tech_doc = getattr(handover, 'tech_doc', None) if handover is not None else None
        pack = packs.get(dossier.final_sample_version_id)
        if pack is not None:
            fact.techpack_label = 'Hồ sơ kỹ thuật mẫu' + (f' · {pack.line_count} dòng NPL' if pack.line_count else '')
        elif tech_doc is not None:
            fact.techpack_label = f'Tài liệu SX {tech_doc.product_code}'
        active = boms.get(tech_doc.pk, []) if tech_doc is not None else []
        if active:
            fact.bom_label = ', '.join(bom.version_label for bom in active[:3])
        elif pack is not None and pack.line_count:
            fact.bom_label = f'Định mức mẫu ({pack.line_count} dòng)'
        cost = snap_cost.get(tech_doc.pk) if tech_doc is not None else None
        if cost is None and dossier.post_sample_cost is not None:
            cost = dossier.post_sample_cost
        fact.cost = cost
        fact.cost_label = 'Đã khóa' if cost is not None else 'Chưa khóa'
        sku_rows = skus.get(code, [])
        fact.sku_count = len(sku_rows)
        fact.barcode_count = sum(1 for row in sku_rows if (row['bar_code'] or '').strip())
        missing = []
        if pack is None and tech_doc is None:
            missing.append('techpack')
        if not active and not (pack is not None and pack.line_count):
            missing.append('BOM')
        if cost is None:
            missing.append('giá thành')
        if not code or not sku_rows:
            missing.append('SKU')
        elif fact.barcode_count < fact.sku_count:
            missing.append('mã vạch')
        if missing:
            fact.lock_gap = 'thiếu ' + ', '.join(missing)

        retail = next((row['base_price'] for row in sku_rows if row['base_price'] and row['base_price'] > 0), None)
        if retail is None and dossier.proposed_retail_price:
            retail = dossier.proposed_retail_price
        wholesale = dossier.proposed_wholesale_price
        fact.retail = retail
        fact.wholesale = wholesale
        price_bits = []
        if dossier.status not in PRICE_OK_STATUSES:
            price_bits.append('hồ sơ chưa ở trạng thái đã duyệt')
        if not retail or retail <= 0:
            price_bits.append('chưa có giá bán lẻ')
        if not wholesale or wholesale <= 0:
            price_bits.append('chưa có giá sỉ / chính sách đại lý')
        if price_bits:
            fact.price_gap = ', '.join(price_bits)

        live = orders.get(code, [])
        overdue = [order for order in live if order.status != SxProductionOrder.STATUS_DONE and order.due_date and order.due_date < today]
        started = [order for order in live if order.status in MO_STARTED]
        if not code or not live:
            fact.mo_gap = 'chưa có lệnh sản xuất'
        elif overdue:
            fact.mo_label = f'{len(live)} lệnh · {len(overdue)} trễ hạn'
            fact.mo_gap = 'lệnh trễ hạn ' + ', '.join(order.code for order in overdue[:3])
        elif not started:
            fact.mo_label = f'{len(live)} lệnh còn nháp'
            fact.mo_gap = 'lệnh sản xuất còn nháp'
        else:
            done = sum(1 for order in live if order.status == SxProductionOrder.STATUS_DONE)
            fact.mo_label = f'{len(live)} lệnh · {done} hoàn thành'

        fact.stock = sum((row['qty_on_hand'] or Decimal('0') for row in sku_rows), Decimal('0'))
        policy = policies.get(code)
        if policy is not None and policy.min_stock and policy.min_stock > 0:
            fact.stock_min = policy.min_stock
        elif link.planned_qty is not None:
            fact.stock_min = Decimal(link.planned_qty)
        if fact.stock_min is None:
            fact.stock_gap = 'chưa có mức tồn tối thiểu'
        elif fact.stock < fact.stock_min:
            fact.stock_gap = f'tồn {fact.stock:,.0f} / tối thiểu {fact.stock_min:,.0f}'

        sku_image = any((row['image'] or row['image_url']) for row in sku_rows)
        fact.image_ok = images[dossier.pk] or gallery[dossier.pk] or sku_image
        fact.video_ok = videos[dossier.pk]
        descriptions = [dossier.description or '']
        descriptions.extend(row['description'] or '' for row in sku_rows)
        if tech_doc is not None:
            descriptions.append(tech_doc.description or '')
        fact.content_ok = any(part.strip() for part in descriptions)
        media_bits = []
        if not fact.image_ok:
            media_bits.append('thiếu hình ảnh')
        if not fact.video_ok:
            media_bits.append('thiếu video')
        if not fact.content_ok:
            media_bits.append('thiếu nội dung')
        if media_bits:
            fact.media_gap = ', '.join(media_bits)

        fact.kiot_count = sum(1 for row in sku_rows if row['kiotviet_id'])
        on_sale = sum(1 for row in sku_rows if row['allows_sale'] is True)
        if fact.sku_count:
            fact.channel_label = f'{fact.sku_count} SKU · {fact.kiot_count} KiotViet · {on_sale} đang cho bán'
        if not code or (fact.kiot_count == 0 and on_sale == 0):
            fact.channel_gap = 'chưa tạo hoặc chưa mở bán trên kênh'
    return facts


def _gate(label: str, gaps: list[str]) -> dict:
    return {
        'label': label,
        'ok': not gaps,
        'note': _join(gaps),
        'task': None,
        'data': True,
    }


def gate_pack(plan, links=None, tasks=None) -> list[dict]:
    cached = getattr(plan, '_gate_rows', None)
    facts = getattr(plan, '_launch_facts', None)
    if cached is not None and facts is not None:
        if links is not None:
            for link in links:
                link.fact = facts.get(link.dossier_id)
        return cached

    if links is None:
        links = _load_links(plan)
    if tasks is None:
        tasks = list(plan.tasks.all())
    facts = build_facts(links)
    for link in links:
        link.fact = facts.get(link.dossier_id)

    def collect(attr: str) -> list[str]:
        found = []
        for link in links:
            gap = getattr(link.fact, attr, '')
            if gap:
                found.append(f'{link.dossier.code}: {gap}')
        return found

    if not links:
        empty = ['Chưa gắn sản phẩm']
        rows = [
            _gate('Thiết kế và mẫu chuẩn đã duyệt', empty),
            _gate('Techpack, BOM, giá thành và SKU đã khóa', empty),
            _gate('Giá bán và chính sách đại lý đã duyệt', empty),
            _gate('Sản xuất đúng tiến độ', empty),
            _gate('Tồn kho đạt mức tối thiểu', empty),
            _gate('Hình ảnh, video và nội dung đã sẵn sàng', empty),
            _gate('Sản phẩm đã được tạo trên các kênh bán', empty),
        ]
    else:
        rows = [
            _gate('Thiết kế và mẫu chuẩn đã duyệt', collect('design_gap')),
            _gate('Techpack, BOM, giá thành và SKU đã khóa', collect('lock_gap')),
            _gate('Giá bán và chính sách đại lý đã duyệt', collect('price_gap')),
            _gate('Sản xuất đúng tiến độ', collect('mo_gap')),
            _gate('Tồn kho đạt mức tối thiểu', collect('stock_gap')),
            _gate('Hình ảnh, video và nội dung đã sẵn sàng', collect('media_gap')),
            _gate('Sản phẩm đã được tạo trên các kênh bán', collect('channel_gap')),
        ]

    logistics = [task for task in tasks if task.group == TaskGroup.LOGISTICS and task.is_go_blocker and not task.is_condition]
    if not logistics:
        rows.append(_gate('Kho vận và giao hàng đã sẵn sàng', ['Chưa có đầu việc kho vận bắt buộc']))
    else:
        pending = [task for task in logistics if task.status not in CLOSED_TASK_STATUSES]
        rows.append(_gate('Kho vận và giao hàng đã sẵn sàng', [task.title for task in pending]))

    for task in tasks:
        if task.is_go_blocker and not task.is_condition and task.group != TaskGroup.LOGISTICS:
            rows.append({
                'label': task.title,
                'ok': task.status in CLOSED_TASK_STATUSES,
                'note': f'{task.milestone} · {task.get_status_display()}',
                'task': task,
                'data': False,
            })
    high = plan.risks.filter(state=LaunchRisk.STATE_OPEN, severity=RiskSeverity.HIGH).count()
    rows.append({
        'label': 'Không còn rủi ro mức Cao đang mở',
        'ok': high == 0,
        'note': f'{high} rủi ro mức Cao' if high else '',
        'task': None,
        'data': False,
    })
    plan._gate_rows = rows
    plan._launch_facts = facts
    return rows
