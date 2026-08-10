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
    ProgressGroup('CAT', 'Cắt', WC_CAT),
    ProgressGroup('IN_EP', 'In - Ép', WC_IN_EP),
    ProgressGroup('THEU', 'Thêu', WC_THEU),
    ProgressGroup('MAY', 'May', WC_MAY),
    ProgressGroup('HOAN_THANH', 'Ủi - Gấp xếp', WC_HT),
    ProgressGroup('GIAO_HANG', 'Giao hàng thành phẩm', WC_GH),
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


# CD chuẩn JustPlay — thứ tự theo luồng xưởng (Cắt → In-Ép → Thêu → May → HT → GH)
_STEPS_RAW: tuple[tuple[str, str, str, str], ...] = (
    # —— Cắt ——
    ('cat_ao', 'Áo TT + TS + Tay', 'CAT', WC_CAT),
    ('cat_quan', 'Quần', 'CAT', WC_CAT),
    ('cat_phoi', 'Phối quần', 'CAT', WC_CAT),
    # —— In - Ép ——
    ('inep_la_co', 'Lá cổ', 'IN_EP', WC_IN_EP),
    ('inep_tru', 'Trụ', 'IN_EP', WC_IN_EP),
    ('inep_in_giay', 'In giấy', 'IN_EP', WC_IN_EP),
    ('inep_than_truoc', 'Thân trước', 'IN_EP', WC_IN_EP),
    ('inep_than_sau', 'Thân sau', 'IN_EP', WC_IN_EP),
    ('inep_tay', 'Tay', 'IN_EP', WC_IN_EP),
    # —— Thêu ——
    ('theu_ao', 'TT áo', 'THEU', WC_THEU),
    ('theu_quan', 'TT quần', 'THEU', WC_THEU),
    # —— May (áo) ——
    ('may_2_lop_la_co', 'May 2 lớp lá cổ x1', 'MAY', WC_MAY),
    ('may_mi_la_co', 'Mí lá cổ x1', 'MAY', WC_MAY),
    ('may_lon_2_canh_la_co', 'May lộn 2 cạnh lá cổ x1', 'MAY', WC_MAY),
    ('may_vs_tru', 'VS trụ x1', 'MAY', WC_MAY),
    ('may_quay_tru', 'Quay trụ x1', 'MAY', WC_MAY),
    ('may_mo_tru', 'Mổ trụ x1', 'MAY', WC_MAY),
    ('may_khoa_tru', 'Khoá trụ x1', 'MAY', WC_MAY),
    ('may_rap_vai', 'Ráp vai x2', 'MAY', WC_MAY),
    ('may_tra_tay', 'Tra tay (thường) x2', 'MAY', WC_MAY),
    ('may_tra_la_co', 'Tra lá cổ x1', 'MAY', WC_MAY),
    ('may_day_tape_nhan', 'May dây tape + nhãn size x1', 'MAY', WC_MAY),
    ('may_dieu_day_tape', 'Diễu dây tape x1', 'MAY', WC_MAY),
    ('may_dieu_co_truoc', 'Diễu cổ trước x1', 'MAY', WC_MAY),
    ('may_rap_suon_ao', 'Ráp sườn x2', 'MAY', WC_MAY),
    ('may_kansai_lai_tay', 'Kansai lai tay x2', 'MAY', WC_MAY),
    ('may_kansai_lai_ao', 'Kansai lai áo x1', 'MAY', WC_MAY),
    ('may_kep_nhan_lai_tay', 'Kẹp nhãn lai tay x2', 'MAY', WC_MAY),
    ('may_ld_thua_khuy', 'Ld + thùa khuy x1', 'MAY', WC_MAY),
    ('may_ld_dinh_nut', 'Ld + đính nút x1', 'MAY', WC_MAY),
    ('may_cat_chi_ao', 'Cắt chỉ áo', 'MAY', WC_MAY),
    ('may_kiem_loi_ao', 'Kiểm lỗi áo', 'MAY', WC_MAY),
    # —— May (quần) ——
    ('may_rap_day_truoc', 'Ráp đáy trước x1', 'MAY', WC_MAY),
    ('may_dieu_day_truoc', 'Diễu đáy trước x1', 'MAY', WC_MAY),
    ('may_rap_day_sau', 'Ráp đáy sau x1', 'MAY', WC_MAY),
    ('may_dieu_day_sau', 'Diễu đáy sau x1', 'MAY', WC_MAY),
    ('may_rap_suon_trong', 'Ráp sườn trong x1', 'MAY', WC_MAY),
    ('may_rap_suon_quan', 'Ráp sườn x2', 'MAY', WC_MAY),
    ('may_cat_thun', 'Cắt thun+ Nối thun x1', 'MAY', WC_MAY),
    ('may_vat_thun_lung', 'Vắt thun vào lưng x1', 'MAY', WC_MAY),
    ('may_dieu_lung', 'Diễu lưng x1', 'MAY', WC_MAY),
    ('may_kansai_lai_quan', 'Kansai lai quần x2', 'MAY', WC_MAY),
    ('may_bam_khuy_day', 'Bấm khuy + Xỏ dây luồn x3', 'MAY', WC_MAY),
    ('may_kiem_quan', 'Kiểm quần', 'MAY', WC_MAY),
    ('may_cat_chi_quan', 'Cắt chỉ quần', 'MAY', WC_MAY),
    ('may_giao', 'Giao hàng may', 'MAY', WC_MAY),
    # —— Ủi - Gấp xếp ——
    ('ht_kiem', 'Kiểm hàng', 'HOAN_THANH', WC_HT),
    ('ht_ui', 'Ủi', 'HOAN_THANH', WC_HT),
    ('ht_gap', 'Gấp xếp', 'HOAN_THANH', WC_HT),
    # —— Giao hàng ——
    ('gh_tp', 'Giao hàng thành phẩm', 'GIAO_HANG', WC_GH),
)

# Tên cũ → tên mới (map khi đổi nhãn / thêm xN)
LABEL_ALIASES: dict[str, str] = {
    'áo tt + ts+ tay': 'Áo TT + TS + Tay',
    'may 2 lớp lá cổ': 'May 2 lớp lá cổ x1',
    'mí lá cổ': 'Mí lá cổ x1',
    'ráp vai': 'Ráp vai x2',
    'tra tay': 'Tra tay (thường) x2',
    'tra lá cổ': 'Tra lá cổ x1',
    'ráp sườn': 'Ráp sườn x2',
    'kansai lai': 'Kansai lai áo x1',
    'cắt chỉ': 'Cắt chỉ áo',
    'kiểm lỗi': 'Kiểm lỗi áo',
    'diễu đáy trước': 'Diễu đáy trước x1',
    'diễu đáy sau': 'Diễu đáy sau x1',
    'ráp đáy trước': 'Ráp đáy trước x1',
    'ráp đáy sau': 'Ráp đáy sau x1',
    'giao hàng tp': 'Giao hàng thành phẩm',
    'giao hàng may': 'Giao hàng may',
}


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
    alias = LABEL_ALIASES.get(lab)
    if alias:
        lab = alias.casefold()
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


def canonical_process_label(label: str) -> str:
    """Chuẩn hoá nhãn CD về tên trong mẫu (kể cả alias cũ)."""
    raw = (label or '').strip()
    if not raw:
        return ''
    alias = LABEL_ALIASES.get(raw.casefold())
    if alias:
        return alias
    sd = step_by_label(raw)
    return sd.label if sd else raw


# Mô tả WC để seed
WC_SEED: tuple[tuple[str, str, str], ...] = (
    (WC_CAT, 'Cắt', 'Cắt'),
    (WC_IN_EP, 'In - Ép', 'In - Ép'),
    (WC_THEU, 'Thêu', 'Thêu'),
    (WC_MAY, 'May', 'May'),
    (WC_HT, 'Ủi - Gấp xếp', 'Ủi - Gấp xếp'),
    (WC_GH, 'Giao hàng thành phẩm', 'Giao hàng thành phẩm'),
)
