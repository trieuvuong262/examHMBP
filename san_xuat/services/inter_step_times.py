"""Thời gian kiểm đếm + vận chuyển khi chuyển sang tổ khác.

Mỗi khoảng giữa hai tổ liền kề:
  kiểm đếm (count_minutes) + vận chuyển (transfer_minutes).

Cùng tổ (nhiều công đoạn) không phát sinh trung gian.
Đơn vị: phút / khoảng (theo lô, không nhân SMV). 0 = không phát sinh.

Mặc định theo cặp bộ phận (Cắt→May khác May→Ủi) trên trang Thời gian trung gian;
nếu chưa khai báo cặp thì dùng mặc định chung. Từng đơn ghi đè bằng nút + trên bảng kế hoạch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from san_xuat.services.sx_settings import sx_decimal, sx_int
from san_xuat.services.work_calendar import is_working_day

_Q2 = Decimal('0.01')


def _q(value, places: str = '0.01') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


def _norm_slug(value) -> str | None:
    s = (value or '').strip().lower()
    return s or None


def hop_pair_map() -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """Cặp bộ phận đã khai báo → (kiểm đếm, vận chuyển)."""
    from san_xuat.hub_models import SxInterStepHop

    rows = SxInterStepHop.objects.values_list(
        'from_slug', 'to_slug', 'count_minutes', 'transfer_minutes',
    )
    return {
        (_norm_slug(a) or '', _norm_slug(b) or ''): (max(_q(c), Decimal('0')), max(_q(t), Decimal('0')))
        for a, b, c, t in rows
        if _norm_slug(a) and _norm_slug(b)
    }


def _global_hop_minutes() -> tuple[Decimal, Decimal]:
    count = max(_q(sx_decimal('plan_count_minutes', '0')), Decimal('0'))
    transfer = max(_q(sx_decimal('plan_transfer_minutes', '0')), Decimal('0'))
    return count, transfer


def default_hop_minutes(
    from_slug: str | None = None,
    to_slug: str | None = None,
    *,
    pairs: dict[tuple[str, str], tuple[Decimal, Decimal]] | None = None,
) -> tuple[Decimal, Decimal]:
    """Mặc định theo cặp bộ phận; thiếu cặp thì dùng mặc định chung."""
    src = _norm_slug(from_slug)
    dst = _norm_slug(to_slug)
    mapping = pairs if pairs is not None else hop_pair_map()
    if src and dst and src != dst:
        pair = mapping.get((src, dst))
        if pair is not None:
            return pair
    return _global_hop_minutes()


def resolve_hop_minutes(
    count,
    transfer,
    *,
    fill_default: bool = False,
    from_slug: str | None = None,
    to_slug: str | None = None,
    pairs: dict[tuple[str, str], tuple[Decimal, Decimal]] | None = None,
) -> tuple[Decimal, Decimal]:
    """Lấy phút hop. fill_default=True chỉ khi seed hàng mới (cả hai còn 0)."""
    c = max(_q(count), Decimal('0'))
    t = max(_q(transfer), Decimal('0'))
    if fill_default and c == 0 and t == 0:
        return default_hop_minutes(from_slug, to_slug, pairs=pairs)
    return c, t


def resolve_adjacent_hop(
    step,
    nxt,
    *,
    fill_default: bool = False,
    pairs: dict[tuple[str, str], tuple[Decimal, Decimal]] | None = None,
) -> tuple[Decimal, Decimal]:
    """Hop từ bước hiện tại sang bước kế — mặc định theo cặp bộ phận."""
    return resolve_hop_minutes(
        _step_attr(step, 'count_minutes'),
        _step_attr(step, 'transfer_minutes'),
        fill_default=fill_default,
        from_slug=_step_team_slug(step),
        to_slug=_step_team_slug(nxt) if nxt is not None else None,
        pairs=pairs,
    )


def hop_buffer_minutes(steps) -> Decimal:
    """Tổng kiểm đếm + vận chuyển các khoảng *khác tổ* (bỏ qua CĐ liền kề cùng tổ)."""
    rows = list(steps or [])
    if len(rows) < 2:
        return Decimal('0')
    pairs = hop_pair_map()
    total = Decimal('0')
    for i, step in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        if not is_inter_team_hop(step, nxt):
            continue
        c, t = resolve_adjacent_hop(step, nxt, fill_default=True, pairs=pairs)
        total += c + t
    return _q(total)


def minutes_per_shift() -> Decimal:
    hours = sx_int('oee_shift_hours', 8, min_v=1, max_v=24)
    return _q(Decimal(hours) * Decimal('60'))


def add_working_minutes(start: date, minutes: Decimal, *, minutes_per_day: Decimal | None = None) -> date:
    """Ngày làm việc khi cộng thêm ``minutes`` (làm tròn lên ngày nếu > 0)."""
    mins = _q(minutes)
    if mins <= 0:
        return start
    per_day = minutes_per_day if minutes_per_day is not None else minutes_per_shift()
    if per_day <= 0:
        per_day = Decimal('480')
    days_need = int((mins / per_day).to_integral_value(rounding=ROUND_CEILING))
    days_need = max(1, days_need)
    day = start
    remaining = days_need
    # start đã là ngày làm việc (hoặc không) — bước sang ngày kế nếu cần đủ số ngày
    guard = 0
    while remaining > 0 and guard < 800:
        if is_working_day(day):
            remaining -= 1
            if remaining == 0:
                return day
        day += timedelta(days=1)
        guard += 1
    return day


def schedule_span(*, start: date, lead_minutes: Decimal) -> tuple[date, date]:
    """(ngày bắt đầu, ngày kết thúc) theo lịch làm việc + quỹ phút/ca."""
    if lead_minutes <= 0:
        return start, start
    end = add_working_minutes(start, lead_minutes)
    return start, end


@dataclass
class PlanHop:
    step_id: int
    from_name: str
    to_name: str
    count_minutes: Decimal
    transfer_minutes: Decimal

    @property
    def buffer_minutes(self) -> Decimal:
        return _q(self.count_minutes + self.transfer_minutes)

    @property
    def is_set(self) -> bool:
        return self.buffer_minutes > 0


def hops_from_steps(steps) -> list[PlanHop]:
    rows = list(steps or [])
    hops: list[PlanHop] = []
    for i, step in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        if not is_inter_team_hop(step, nxt):
            continue
        c, t = resolve_adjacent_hop(step, nxt, fill_default=False)
        hops.append(PlanHop(
            step_id=int(_step_attr(step, 'pk', 0) or 0),
            from_name=(_step_attr(step, 'process_name') or '').strip(),
            to_name=(_step_attr(nxt, 'process_name') or '').strip(),
            count_minutes=c,
            transfer_minutes=t,
        ))
    return hops


def _step_attr(step, name: str, default=None):
    if isinstance(step, dict):
        return step.get(name, default)
    return getattr(step, name, default)


def _step_team_slug(step) -> str | None:
    """Slug bộ phận chuẩn (cat/may/ht/…) từ tổ hoặc tên công đoạn."""
    if step is None:
        return None
    wc = _step_attr(step, 'work_center')
    if wc is not None:
        from san_xuat.services.capacity_from_hrm import team_slug_for_work_center

        slug = team_slug_for_work_center(wc)
        if slug:
            return _norm_slug(slug)
    name = (_step_attr(step, 'process_name') or '').strip()
    if name:
        from san_xuat.services.progress_template import team_slug_for_process_label

        slug = team_slug_for_process_label(name)
        if slug:
            return _norm_slug(slug)
    label = (_step_attr(step, 'team_label') or '').strip()
    if not label and wc is not None:
        label = (getattr(wc, 'team_label', None) or getattr(wc, 'name', None) or '').strip()
    if label:
        from san_xuat.services.capacity_from_hrm import _fold, _team_slug_from_folded

        return _norm_slug(_team_slug_from_folded(_fold(label)))
    return None


def _step_team_key(step) -> tuple[int | None, str]:
    """(work_center_id, nhãn tổ). Không có tổ → id None, không gộp với bước khác."""
    wc = _step_attr(step, 'work_center')
    wc_id = _step_attr(step, 'work_center_id')
    if wc is not None and getattr(wc, 'pk', None):
        wc_id = int(wc.pk)
    elif wc_id not in (None, '', 0, '0'):
        wc_id = int(wc_id)
    else:
        wc_id = None
    label = (_step_attr(step, 'team_label') or '').strip()
    if not label and wc is not None:
        label = (getattr(wc, 'team_label', None) or getattr(wc, 'name', None) or '').strip()
    return wc_id, label


def is_inter_team_hop(step, nxt) -> bool:
    """True khi bước sau thuộc tổ khác (cùng quy tắc cụm trên bảng kế hoạch)."""
    next_id, _ = _step_team_key(nxt)
    if next_id is None:
        return True
    cur_id, _ = _step_team_key(step)
    return cur_id != next_id


@dataclass
class PlanFlowGroup:
    """Cụm công đoạn liền kề cùng tổ; hop là khoảng sang tổ kế."""

    team_label: str
    work_center_id: int | None
    process_names: list[str] = field(default_factory=list)
    hop_step_id: int = 0
    count_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    transfer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    from_slug: str = ''
    to_slug: str = ''
    default_count_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    default_transfer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))

    @property
    def buffer_minutes(self) -> Decimal:
        return _q(self.count_minutes + self.transfer_minutes)

    @property
    def hop_is_set(self) -> bool:
        return self.buffer_minutes > 0

    @property
    def form_count_minutes(self) -> Decimal:
        if self.hop_is_set:
            return self.count_minutes
        return self.default_count_minutes

    @property
    def form_transfer_minutes(self) -> Decimal:
        if self.hop_is_set:
            return self.transfer_minutes
        return self.default_transfer_minutes


def attach_flow_group_hops(groups: list[PlanFlowGroup], plan_steps) -> list[PlanFlowGroup]:
    """Gắn hop_step_id + phút đã lưu từ snapshot đơn vào flow (theo tên công đoạn).

    Dùng khi flow build từ routing từng mã SP — vẫn sửa kiểm/VC qua SxSalesOrderPlanStep.
    """
    rows = list(plan_steps or [])
    if not groups:
        return groups
    by_name: dict[str, object] = {}
    for step in rows:
        name = (_step_attr(step, 'process_name') or '').strip()
        if name:
            by_name[name.casefold()] = step

    pairs = hop_pair_map()
    for i, g in enumerate(groups):
        if i >= len(groups) - 1:
            continue
        candidates = []
        for name in g.process_names:
            step = by_name.get((name or '').casefold())
            if step is not None:
                candidates.append(step)
        if not candidates:
            # Fallback: bước cùng slug tổ trong snapshot
            slug = (g.from_slug or '').strip().lower()
            if not slug and g.work_center_id:
                for step in rows:
                    if int(_step_attr(step, 'work_center_id', 0) or 0) == int(g.work_center_id):
                        candidates.append(step)
            elif slug:
                for step in rows:
                    if (_step_team_slug(step) or '') == slug:
                        candidates.append(step)
        if not candidates:
            g.hop_step_id = 0
            continue

        with_mins = [
            s for s in candidates
            if _q(_step_attr(s, 'count_minutes', 0)) > 0
            or _q(_step_attr(s, 'transfer_minutes', 0)) > 0
        ]
        pick = max(
            with_mins or candidates,
            key=lambda s: (int(_step_attr(s, 'sequence', 0) or 0), int(_step_attr(s, 'pk', 0) or 0)),
        )
        g.hop_step_id = int(_step_attr(pick, 'pk', 0) or 0)
        nxt = groups[i + 1]
        # from/to slug theo nhóm (đã chuẩn hóa), không phụ thuộc bước lẻ
        g.from_slug = g.from_slug or (_step_team_slug(pick) or '')
        # lấy slug nhóm sau từ bước đầu nhóm sau nếu có
        nxt_step = None
        for name in nxt.process_names:
            nxt_step = by_name.get((name or '').casefold())
            if nxt_step is not None:
                break
        g.to_slug = g.to_slug or (_step_team_slug(nxt_step) if nxt_step else '') or nxt.from_slug
        hop_c, hop_t = resolve_hop_minutes(
            _step_attr(pick, 'count_minutes'),
            _step_attr(pick, 'transfer_minutes'),
            fill_default=False,
        )
        if hop_c > 0 or hop_t > 0:
            g.count_minutes = hop_c
            g.transfer_minutes = hop_t
        def_c, def_t = default_hop_minutes(g.from_slug, g.to_slug, pairs=pairs)
        g.default_count_minutes = def_c
        g.default_transfer_minutes = def_t
    return groups


def sort_steps_by_factory_flow(steps) -> list:
    """Sắp công đoạn theo luồng xưởng (Cắt → In-Ép → Thêu → May → HT → GH).

    OB nhảy tổ (MAY→IN→MAY…) được xếp lại để bảng kế hoạch không lặp pill tổ.
    Trong cùng tổ giữ thứ tự sequence gốc.
    """
    from san_xuat.services.progress_template import TEAM_SLUGS

    slug_rank = {slug: i for i, (slug, *_rest) in enumerate(TEAM_SLUGS)}
    indexed: list[tuple[int, int, int, object]] = []
    for i, step in enumerate(steps or []):
        slug = _step_team_slug(step) or ''
        seq = int(_step_attr(step, 'sequence', 0) or 0)
        if slug in slug_rank:
            rank = slug_rank[slug]
        elif slug:
            rank = 800
        else:
            rank = 900
        indexed.append((rank, seq, i, step))
    indexed.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[3] for row in indexed]


def flow_groups_from_steps(steps, *, sort_factory: bool = False) -> list[PlanFlowGroup]:
    """Gộp công đoạn liền kề cùng tổ. Bước chưa gán tổ đứng riêng.

    ``sort_factory=True``: xếp lại theo luồng xưởng trước khi gộp (hết nhảy tổ).
    """
    rows = list(steps or [])
    if not rows:
        return []
    if sort_factory:
        rows = sort_steps_by_factory_flow(rows)

    clusters: list[tuple[int | None, str, str, list]] = []
    for step in rows:
        wc_id, label = _step_team_key(step)
        slug = _step_team_slug(step) or ''
        # Gộp theo slug chuẩn khi có — tránh trùng pill vì WC khác tên cùng tổ
        cluster_key = slug or (f'wc:{wc_id}' if wc_id is not None else None)
        if cluster_key is None:
            clusters.append((None, label, '', [step]))
            continue
        if clusters and clusters[-1][2] == cluster_key and cluster_key:
            clusters[-1][3].append(step)
            # Giữ nhãn/wc đầu tiên; bổ sung label nếu cụm trước trống
            if not clusters[-1][1] and label:
                clusters[-1] = (wc_id or clusters[-1][0], label, cluster_key, clusters[-1][3])
            elif clusters[-1][0] is None and wc_id is not None:
                clusters[-1] = (wc_id, label or clusters[-1][1], cluster_key, clusters[-1][3])
        else:
            clusters.append((wc_id, label, cluster_key, [step]))

    groups: list[PlanFlowGroup] = []
    pairs = hop_pair_map()
    from san_xuat.services.progress_template import team_by_slug

    for i, (wc_id, label, ckey, cluster) in enumerate(clusters):
        # Nhãn chuẩn theo slug xưởng khi gộp (ỦI + GẤP XẾP → «Ủi - Gấp xếp»)
        if ckey and not ckey.startswith('wc:'):
            meta = team_by_slug(ckey)
            if meta:
                label = meta.get('group_label') or meta.get('label') or label
        names: list[str] = []
        seen: set[str] = set()
        for step in cluster:
            name = (_step_attr(step, 'process_name') or '').strip()
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
        hop_c = hop_t = Decimal('0')
        hop_step_id = 0
        from_slug = to_slug = ''
        def_c, def_t = _global_hop_minutes()
        if i < len(clusters) - 1:
            last = cluster[-1]
            nxt_first = clusters[i + 1][3][0]
            hop_step_id = int(_step_attr(last, 'pk', 0) or 0)
            from_slug = _step_team_slug(last) or ''
            to_slug = _step_team_slug(nxt_first) or ''
            hop_c, hop_t = resolve_adjacent_hop(last, nxt_first, fill_default=False, pairs=pairs)
            def_c, def_t = default_hop_minutes(from_slug, to_slug, pairs=pairs)
        groups.append(PlanFlowGroup(
            team_label=label,
            work_center_id=wc_id,
            process_names=names,
            hop_step_id=hop_step_id,
            count_minutes=hop_c,
            transfer_minutes=hop_t,
            from_slug=from_slug,
            to_slug=to_slug,
            default_count_minutes=def_c,
            default_transfer_minutes=def_t,
        ))
    return groups


def hop_pair_form_context() -> dict:
    """Dữ liệu form: luồng xưởng + các khoảng khác theo cặp bộ phận."""
    from san_xuat.services.team_division_map import team_slug_choices

    teams = team_slug_choices()
    slugs = [s for s, _ in teams]
    sequential = set(zip(slugs, slugs[1:]))
    saved = hop_pair_map()
    sequential_hops: list[dict] = []
    other_groups: list[dict] = []
    current = None
    for from_slug, from_label in teams:
        for to_slug, to_label in teams:
            if from_slug == to_slug:
                continue
            pair = saved.get((from_slug, to_slug))
            row = {
                'from_slug': from_slug,
                'from_label': from_label,
                'to_slug': to_slug,
                'to_label': to_label,
                'count_minutes': pair[0] if pair is not None else None,
                'transfer_minutes': pair[1] if pair is not None else None,
                'is_sequential': (from_slug, to_slug) in sequential,
            }
            if row['is_sequential']:
                sequential_hops.append(row)
                continue
            if current is None or current['from_slug'] != from_slug:
                current = {
                    'from_slug': from_slug,
                    'from_label': from_label,
                    'hops': [],
                }
                other_groups.append(current)
            current['hops'].append(row)
    sequential_hops.sort(key=lambda r: slugs.index(r['from_slug']))
    return {
        'team_flow_labels': [label for _, label in teams],
        'sequential_hops': sequential_hops,
        'other_hop_groups': other_groups,
    }


def save_hop_pair_minutes(entries: list[tuple[str, str, Decimal | None, Decimal | None]], *, user=None) -> int:
    """Lưu cặp bộ phận. Cả hai None = xóa (dùng mặc định chung). Trả số dòng upsert/xóa."""
    from san_xuat.hub_models import SxInterStepHop
    from san_xuat.services.team_division_map import VALID_TEAM_SLUGS

    changed = 0
    for from_slug, to_slug, count, transfer in entries:
        src = _norm_slug(from_slug)
        dst = _norm_slug(to_slug)
        if not src or not dst or src == dst:
            continue
        if src not in VALID_TEAM_SLUGS or dst not in VALID_TEAM_SLUGS:
            continue
        if count is None and transfer is None:
            deleted, _ = SxInterStepHop.objects.filter(from_slug=src, to_slug=dst).delete()
            changed += deleted
            continue
        c = max(_q(count), Decimal('0'))
        t = max(_q(transfer), Decimal('0'))
        SxInterStepHop.objects.update_or_create(
            from_slug=src,
            to_slug=dst,
            defaults={
                'count_minutes': c,
                'transfer_minutes': t,
                'updated_by': user if getattr(user, 'is_authenticated', False) else None,
            },
        )
        changed += 1
    return changed
