"""Sơ đồ cơ cấu tổ chức — treemap: GDĐH → Phòng ban → Bộ phận."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count, Prefetch, Q

from hrm.models import Department, Division, DivisionPosition, Profile
from hrm.permissions import ROLE_DIRECTOR

ORG_EXECUTIVE_LABEL = 'Giám đốc điều hành'
ORG_COMPANY_ROOT = 'Công ty TNHH Just Play'
MAX_POSITIONS_PER_DIVISION = 12


@dataclass
class OrgDivisionNode:
    pk: int
    name: str
    sort_order: int
    is_active: bool
    staff_count: int
    treemap_weight: int = 1


@dataclass
class OrgDepartmentNode:
    pk: int
    name: str
    sort_order: int
    is_active: bool
    staff_count: int
    divisions: list[OrgDivisionNode] = field(default_factory=list)
    treemap_weight: int = 1


@dataclass
class OrgTreemapContext:
    executive_label: str
    director_count: int
    total_staff: int
    departments: list[OrgDepartmentNode]
    unassigned_divisions: list[OrgDivisionNode]
    position_hint: str


def _division_queryset():
    return (
        Division.objects.annotate(staff_count=Count('division_profiles', distinct=True))
        .order_by('sort_order', 'name')
    )


def build_org_treemap() -> OrgTreemapContext:
    divisions_qs = _division_queryset()
    departments = (
        Department.objects.annotate(staff_count=Count('profiles', distinct=True))
        .prefetch_related(
            Prefetch('divisions', queryset=divisions_qs),
        )
        .order_by('sort_order', 'name')
    )

    dept_nodes: list[OrgDepartmentNode] = []
    for dept in departments:
        div_nodes = [
            OrgDivisionNode(
                pk=div.pk,
                name=div.name,
                sort_order=div.sort_order,
                is_active=div.is_active,
                staff_count=div.staff_count,
                treemap_weight=max(div.staff_count, 1),
            )
            for div in dept.divisions.all()
        ]
        div_staff = sum(d.staff_count for d in div_nodes)
        weight = max(dept.staff_count, div_staff, len(div_nodes), 1)
        div_nodes.sort(key=lambda d: (-d.treemap_weight, d.sort_order, d.name.lower()))
        dept_nodes.append(
            OrgDepartmentNode(
                pk=dept.pk,
                name=dept.name,
                sort_order=dept.sort_order,
                is_active=dept.is_active,
                staff_count=dept.staff_count,
                divisions=div_nodes,
                treemap_weight=weight,
            )
        )

    dept_nodes.sort(key=lambda d: (-d.treemap_weight, d.sort_order, d.name.lower()))

    unassigned = [
        OrgDivisionNode(
            pk=div.pk,
            name=div.name,
            sort_order=div.sort_order,
            is_active=div.is_active,
            staff_count=div.staff_count,
            treemap_weight=max(div.staff_count, 1),
        )
        for div in divisions_qs.filter(department__isnull=True)
    ]
    unassigned.sort(key=lambda d: (-d.treemap_weight, d.sort_order, d.name.lower()))

    total_staff = Profile.objects.filter(is_employed=True).count()
    director_count = Profile.objects.filter(
        is_employed=True,
        role=ROLE_DIRECTOR,
    ).count()

    return OrgTreemapContext(
        executive_label=ORG_EXECUTIVE_LABEL,
        director_count=director_count,
        total_staff=total_staff,
        departments=dept_nodes,
        unassigned_divisions=unassigned,
        position_hint=(
            'Vị trí: thêm từ nút + trên bộ phận trong sơ đồ hoặc gán khi thêm nhân viên. '
            'Tên vị trí trùng với hồ sơ NV sẽ gộp số lượng.'
        ),
    )


def _staff_counts_by_position(department_id: int | None, division_id: int) -> dict[str, int]:
    qs = Profile.objects.filter(is_employed=True, division_id=division_id).exclude(job_position='')
    if department_id:
        qs = qs.filter(department_id=department_id)
    rows = qs.values('job_position').annotate(count=Count('id'))
    return {row['job_position']: row['count'] for row in rows}


def _position_children(department_id: int | None, division_id: int) -> list[dict]:
    counts = _staff_counts_by_position(department_id, division_id)
    defined = DivisionPosition.objects.filter(
        division_id=division_id,
        is_active=True,
    ).order_by('sort_order', 'name')
    seen: set[str] = set()
    out: list[dict] = []

    for pos in defined:
        seen.add(pos.name)
        out.append({
            'name': pos.name,
            'count': counts.get(pos.name, 0),
            'level': 'position',
            'id': pos.pk,
            'division_id': division_id,
            'dept_id': department_id,
            'is_defined': True,
            'children': [],
        })

    extras = sorted(
        ((name, cnt) for name, cnt in counts.items() if name not in seen),
        key=lambda item: (-item[1], item[0].lower()),
    )
    for name, cnt in extras:
        if len(out) >= MAX_POSITIONS_PER_DIVISION:
            break
        out.append({
            'name': name,
            'count': cnt,
            'level': 'position',
            'id': None,
            'division_id': division_id,
            'dept_id': department_id,
            'is_defined': False,
            'children': [],
        })
    return out[:MAX_POSITIONS_PER_DIVISION]


def build_org_tree(treemap: OrgTreemapContext) -> dict:
    """Cây JSON cho sơ đồ ngang (D3) — Công ty → Phòng ban → Bộ phận → Vị trí."""
    children: list[dict] = []

    for dept in treemap.departments:
        div_children: list[dict] = []
        for div in dept.divisions:
            div_children.append({
                'name': div.name,
                'count': div.staff_count,
                'level': 'division',
                'id': div.pk,
                'dept_id': dept.pk,
                'is_active': div.is_active,
                'children': _position_children(dept.pk, div.pk),
            })
        children.append({
            'name': dept.name,
            'count': dept.staff_count,
            'level': 'department',
            'id': dept.pk,
            'is_active': dept.is_active,
            'children': div_children,
        })

    if treemap.unassigned_divisions:
        children.append({
            'name': 'Chưa gán phòng ban',
            'count': sum(d.staff_count for d in treemap.unassigned_divisions),
            'level': 'unassigned',
            'children': [
                {
                    'name': div.name,
                    'count': div.staff_count,
                    'level': 'division',
                    'id': div.pk,
                    'dept_id': None,
                    'is_active': div.is_active,
                    'children': _position_children(None, div.pk),
                }
                for div in treemap.unassigned_divisions
            ],
        })

    return {
        'name': ORG_COMPANY_ROOT,
        'count': treemap.total_staff,
        'level': 'root',
        'subtitle': f'{treemap.executive_label} · {treemap.director_count} GĐ',
        'children': children,
    }


def filter_org_tree(node: dict, query: str) -> dict | None:
    """Lọc cây theo từ khóa — giữ nhánh khớp tên."""
    if not query:
        return node
    q = query.lower().strip()
    if not q:
        return node

    name = (node.get('name') or '').lower()
    matched = q in name
    kids = []
    for child in node.get('children') or []:
        kept = filter_org_tree(child, q)
        if kept is not None:
            kids.append(kept)
            matched = True
    if not matched:
        return None
    out = dict(node)
    out['children'] = kids
    return out


def divisions_for_department(department_id: int | None):
    """Queryset bộ phận theo phòng ban (dropdown nhân sự)."""
    qs = Division.objects.filter(is_active=True).select_related('department')
    if not department_id:
        return qs.order_by('sort_order', 'name')
    return qs.filter(Q(department_id=department_id) | Q(department__isnull=True)).order_by(
        'sort_order', 'name',
    )
