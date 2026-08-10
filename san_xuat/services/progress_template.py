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

# CD con — May rút gọn (đủ dùng v1; mở rộng trong list này không đổi schema)
_STEPS_RAW: tuple[tuple[str, str, str, str], ...] = (
    # key, label, group, wc
    ('cat_ao', 'Áo TT + TS + Tay', 'CAT', WC_CAT),
    ('cat_quan', 'Quần', 'CAT', WC_CAT),
    ('cat_phoi', 'Phối quần', 'CAT', WC_CAT),
    # IN-ÉP = ép keo + in CN
    ('inep_la_co', 'Lá cổ', 'IN_EP', WC_IN_EP),
    ('inep_tru', 'Trụ', 'IN_EP', WC_IN_EP),
    ('inep_in_giay', 'In giấy', 'IN_EP', WC_IN_EP),
    ('inep_than_truoc', 'Thân trước', 'IN_EP', WC_IN_EP),
    ('inep_than_sau', 'Thân sau', 'IN_EP', WC_IN_EP),
    ('inep_tay', 'Tay', 'IN_EP', WC_IN_EP),
    ('theu_ao', 'TT áo', 'THEU', WC_THEU),
    ('theu_quan', 'TT quần', 'THEU', WC_THEU),
    # May (rút gọn)
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
    ('gh_tp', 'Giao hàng TP', 'GIAO_HANG', WC_GH),
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


def label_to_key_map() -> dict[str, str]:
    return {s.label.casefold(): s.key for s in progress_steps()}


# Mô tả WC để seed
WC_SEED: tuple[tuple[str, str, str], ...] = (
    (WC_CAT, 'Cắt', 'Cắt'),
    (WC_IN_EP, 'In - Ép', 'In - Ép'),
    (WC_THEU, 'Thêu', 'Thêu'),
    (WC_MAY, 'May', 'May'),
    (WC_HT, 'Hoàn thành', 'Hoàn thành'),
    (WC_GH, 'Giao hàng TP', 'Giao hàng TP'),
)
