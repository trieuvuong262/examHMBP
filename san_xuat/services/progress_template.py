"""Mẫu cố định phiếu theo dõi tiến độ ra hàng (size × công đoạn).

Nhóm IN_EP gộp Ép keo + In chuyển nhiệt thành một bộ phận IN-ÉP.
"""

from __future__ import annotations

from dataclasses import dataclass

# Mã tổ mặc định cho nhóm in–ép (khớp SxWorkCenter.code)
WC_IN_EP = 'IN-EP'
WC_CAT = 'CAT'
WC_THEU = 'THEU'
WC_MAY = 'MAY'
WC_HT = 'HT'
WC_GH = 'GH'


@dataclass(frozen=True)
class ProgressGroup:
    key: str
    label: str
    work_center_code: str


@dataclass(frozen=True)
class ProgressStepDef:
    key: str
    label: str
    group: str
    work_center_code: str
    sequence: int


GROUPS: tuple[ProgressGroup, ...] = (
    ProgressGroup('CAT', 'CẮT', WC_CAT),
    ProgressGroup('IN_EP', 'IN - ÉP', WC_IN_EP),
    ProgressGroup('THEU', 'THÊU', WC_THEU),
    ProgressGroup('MAY', 'CÔNG ĐOẠN MAY', WC_MAY),
    ProgressGroup('HOAN_THANH', 'HOÀN THÀNH', WC_HT),
    ProgressGroup('GIAO_HANG', 'GIAO HÀNG THÀNH PHẨM', WC_GH),
)

# slug URL ↔ group key ↔ menu key
TEAM_SLUGS: tuple[tuple[str, str, str, str], ...] = (
    # slug, group_key, menu_key, short_label
    ('cat', 'CAT', 'team_work_cat', 'Cắt'),
    ('inep', 'IN_EP', 'team_work_inep', 'In - Ép'),
    ('theu', 'THEU', 'team_work_theu', 'Thêu'),
    ('may', 'MAY', 'team_work_may', 'May'),
    ('ht', 'HOAN_THANH', 'team_work_ht', 'Ủi - Gấp xếp'),
    ('gh', 'GIAO_HANG', 'team_work_gh', 'Giao hàng thành phẩm'),
)


def team_by_slug(slug: str) -> dict | None:
    s = (slug or '').strip().lower()
    for item_slug, group_key, menu_key, label in TEAM_SLUGS:
        if item_slug == s:
            grp = next((g for g in GROUPS if g.key == group_key), None)
            return {
                'slug': item_slug,
                'group_key': group_key,
                'menu_key': menu_key,
                'label': label,
                'group_label': grp.label if grp else label,
                'work_center_code': grp.work_center_code if grp else '',
            }
    return None


# CD con — May rút gọn (đủ dùng v1; mở rộng trong list này không đổi schema)
_STEPS_RAW: tuple[tuple[str, str, str, str], ...] = (
    ('cat_ao', 'Áo TT + TS + Tay', 'CAT', WC_CAT),
    ('cat_quan', 'Quần', 'CAT', WC_CAT),
    ('cat_phoi', 'Phối quần', 'CAT', WC_CAT),
    ('inep_la_co', 'Lá cổ', 'IN_EP', WC_IN_EP),
    ('inep_tru', 'Trụ', 'IN_EP', WC_IN_EP),
    ('inep_in_giay', 'In giấy', 'IN_EP', WC_IN_EP),
    ('inep_than_truoc', 'Thân trước', 'IN_EP', WC_IN_EP),
    ('inep_than_sau', 'Thân sau', 'IN_EP', WC_IN_EP),
    ('inep_tay', 'Tay', 'IN_EP', WC_IN_EP),
    ('theu_ao', 'TT áo', 'THEU', WC_THEU),
    ('theu_quan', 'TT quần', 'THEU', WC_THEU),
    ('may_la_co', 'May 2 lớp lá cổ', 'MAY', WC_MAY),
    ('may_mi_la_co', 'Mí lá cổ', 'MAY', WC_MAY),
    ('may_rap_vai', 'Ráp vai', 'MAY', WC_MAY),
    ('may_tra_tay', 'Tra tay', 'MAY', WC_MAY),
    ('may_tra_co', 'Tra lá cổ', 'MAY', WC_MAY),
    ('may_rap_suon', 'Ráp sườn', 'MAY', WC_MAY),
    ('may_kansai', 'Kansai lai', 'MAY', WC_MAY),
    ('may_cat_chi', 'Cắt chỉ', 'MAY', WC_MAY),
    ('may_kiem_loi', 'Kiểm lỗi', 'MAY', WC_MAY),
    ('may_giao', 'Giao hàng may', 'MAY', WC_MAY),
    ('ht_kiem', 'Kiểm hàng', 'HOAN_THANH', WC_HT),
    ('ht_ui', 'Ủi', 'HOAN_THANH', WC_HT),
    ('ht_gap', 'Gấp xếp', 'HOAN_THANH', WC_HT),
    ('gh_tp', 'Giao hàng thành phẩm', 'GIAO_HANG', WC_GH),
)


def progress_steps() -> list[ProgressStepDef]:
    out: list[ProgressStepDef] = []
    for i, (key, label, group, wc) in enumerate(_STEPS_RAW):
        out.append(
            ProgressStepDef(
                key=key,
                label=label,
                group=group,
                work_center_code=wc,
                sequence=(i + 1) * 10,
            )
        )
    return out


def steps_for_group(group_key: str) -> list[ProgressStepDef]:
    return [s for s in progress_steps() if s.group == group_key]


def progress_groups_with_steps() -> list[tuple[ProgressGroup, list[ProgressStepDef]]]:
    by_group: dict[str, list[ProgressStepDef]] = {g.key: [] for g in GROUPS}
    for step in progress_steps():
        by_group.setdefault(step.group, []).append(step)
    return [(g, by_group.get(g.key, [])) for g in GROUPS]


def step_by_key(key: str) -> ProgressStepDef | None:
    k = (key or '').strip()
    for s in progress_steps():
        if s.key == k:
            return s
    return None


def step_by_label(label: str) -> ProgressStepDef | None:
    lab = (label or '').strip().casefold()
    if not lab:
        return None
    for s in progress_steps():
        if s.label.casefold() == lab:
            return s
    return None


def team_slug_for_process_label(label: str) -> str | None:
    """Slug URL Công việc tổ từ tên công đoạn (vd. Lá cổ → inep)."""
    sd = step_by_label(label)
    if not sd:
        return None
    for slug, group_key, _menu_key, _lab in TEAM_SLUGS:
        if group_key == sd.group:
            return slug
    return None


def label_to_key_map() -> dict[str, str]:
    return {s.label.casefold(): s.key for s in progress_steps()}


# Mô tả WC để seed
WC_SEED: tuple[tuple[str, str, str], ...] = (
    (WC_CAT, 'Cắt', 'Cắt'),
    (WC_IN_EP, 'In - Ép', 'In - Ép'),
    (WC_THEU, 'Thêu', 'Thêu'),
    (WC_MAY, 'May', 'May'),
    (WC_HT, 'Hoàn thành', 'Hoàn thành'),
    (WC_GH, 'Giao hàng thành phẩm', 'Giao hàng thành phẩm'),
)
