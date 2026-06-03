"""Sơ đồ cơ cấu tổ chức — treemap: GDĐH → Phòng ban → Bộ phận."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count, Prefetch, Q

_HEAD_POSITION_NAMES = ('Trưởng phòng', 'Trưởng Phòng', 'TRUONG PHONG')
_DIVISION_HEAD_POSITION_NAMES = ('Trưởng bộ phận', 'Trưởng Bộ Phận', 'TRUONG BO PHAN')

from hrm.models import Department, Division, DivisionPosition, Profile
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD
from hrm.user_search import exclude_hidden_hrm_profiles, hidden_hrm_username_q

ORG_EXECUTIVE_LABEL = 'Giám đốc điều hành'
ORG_COMPANY_ROOT = 'Công ty TNHH Just Play'
ORG_DEPARTMENT_HEAD_LABEL = 'Trưởng phòng'
ORG_DEPARTMENT_HEAD_PREFIX = 'Trưởng Phòng:'
ORG_DIVISION_HEAD_LABEL = 'Trưởng bộ phận'
ORG_DIVISION_HEAD_PREFIX = 'Trưởng Bộ Phận:'
ORG_DIRECTOR_PREFIX = 'Giám đốc:'
MAX_POSITIONS_PER_DIVISION = 12
MAX_EMPLOYEES_PER_POSITION = 80


def position_node_key(division_id: int, position_name: str, position_id: int | None = None) -> str:
    if position_id:
        return f'id:{position_id}'
    return f'div:{division_id}:pos:{position_name}'


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


def _org_profile_count_filter(related_prefix: str) -> Q:
    visible = Q(**{f'{related_prefix}is_employed': True})
    return visible & ~hidden_hrm_username_q(user_prefix=f'{related_prefix}user__')


def _division_queryset():
    return (
        Division.objects.annotate(
            staff_count=Count(
                'division_profiles',
                filter=_org_profile_count_filter('division_profiles__'),
                distinct=True,
            ),
        )
        .order_by('sort_order', 'name')
    )


def build_org_treemap() -> OrgTreemapContext:
    divisions_qs = _division_queryset()
    departments = (
        Department.objects.annotate(
            staff_count=Count(
                'profiles',
                filter=_org_profile_count_filter('profiles__'),
                distinct=True,
            ),
        )
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

    total_staff = exclude_hidden_hrm_profiles(
        Profile.objects.filter(is_employed=True),
    ).count()
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
    )


def _department_head_profiles(department_id: int):
    """NV trưởng phòng: thuộc PB, không gán bộ phận, vị trí Trưởng phòng."""
    return exclude_hidden_hrm_profiles(
        Profile.objects.filter(
            is_employed=True,
            department_id=department_id,
            division__isnull=True,
            job_position__in=_HEAD_POSITION_NAMES,
        ),
    ).select_related('user').order_by('employee_code', 'full_name')


def _division_head_profiles(department_id: int | None, division_id: int):
    """NV trưởng bộ phận — gắn bộ phận, vai trò Trưởng bộ phận hoặc vị trí tương ứng."""
    qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(
            is_employed=True,
            division_id=division_id,
        ).filter(
            Q(role=ROLE_DIVISION_HEAD) | Q(job_position__in=_DIVISION_HEAD_POSITION_NAMES),
        ),
    )
    if department_id:
        qs = qs.filter(department_id=department_id)
    return qs.select_related('user').order_by('employee_code', 'full_name')


def _division_head_line(
    department_id: int | None,
    division_id: int,
) -> tuple[str, int | None, bool]:
    profiles = list(_division_head_profiles(department_id, division_id)[:3])
    names = [
        (p.full_name or p.user.first_name or p.user.username or '').strip()
        for p in profiles
    ]
    names = [n for n in names if n]
    if not names:
        return '', None, False
    subtitle = f'{ORG_DIVISION_HEAD_PREFIX} {", ".join(names)}'
    head_user_id = profiles[0].user_id if len(profiles) == 1 else None
    return subtitle, head_user_id, True


def _executive_director_profiles():
    return exclude_hidden_hrm_profiles(
        Profile.objects.filter(is_employed=True, role=ROLE_DIRECTOR),
    ).select_related('user').order_by('employee_code', 'full_name')


def _executive_director_line() -> tuple[str, int | None, bool]:
    profiles = list(_executive_director_profiles()[:5])
    names = [
        (p.full_name or p.user.first_name or p.user.username or '').strip()
        for p in profiles
    ]
    names = [n for n in names if n]
    if not names:
        return '', None, False
    subtitle = f'{ORG_DIRECTOR_PREFIX} {", ".join(names)}'
    head_user_id = profiles[0].user_id if len(profiles) == 1 else None
    return subtitle, head_user_id, True


def _division_tree_node(
    *,
    name: str,
    staff_count: int,
    division_id: int,
    department_id: int | None,
    is_active: bool,
    children: list[dict],
) -> dict:
    head_subtitle, head_user_id, has_head = _division_head_line(department_id, division_id)
    node: dict = {
        'name': name,
        'count': staff_count,
        'level': 'division',
        'id': division_id,
        'dept_id': department_id,
        'is_active': is_active,
        'has_head': has_head,
        'head_user_id': head_user_id,
        'head_position': ORG_DIVISION_HEAD_LABEL,
        'children': children,
    }
    if head_subtitle:
        node['subtitle'] = head_subtitle
    return node


def _department_head_line(department_id: int) -> tuple[str, int | None, bool]:
    """Dòng phụ dưới tên phòng ban — vd. «Trưởng Phòng: Nguyễn Thành An»."""
    profiles = list(_department_head_profiles(department_id)[:3])
    names = [
        (p.full_name or p.user.first_name or p.user.username or '').strip()
        for p in profiles
    ]
    names = [n for n in names if n]
    if not names:
        return '', None, False
    subtitle = f'{ORG_DEPARTMENT_HEAD_PREFIX} {", ".join(names)}'
    head_user_id = profiles[0].user_id if len(profiles) == 1 else None
    return subtitle, head_user_id, True


def _staff_counts_by_position(department_id: int | None, division_id: int) -> dict[str, int]:
    qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(is_employed=True, division_id=division_id).exclude(job_position=''),
    )
    if department_id:
        qs = qs.filter(department_id=department_id)
    rows = qs.values('job_position').annotate(count=Count('id'))
    return {row['job_position']: row['count'] for row in rows}


def _employee_nodes(
    department_id: int | None,
    division_id: int,
    position_name: str,
) -> list[dict]:
    qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(
            is_employed=True,
            division_id=division_id,
            job_position__iexact=position_name,
        ),
    ).select_related('user').order_by('employee_code', 'full_name')
    if department_id:
        qs = qs.filter(department_id=department_id)
    return [
        {
            'name': (p.full_name or p.user.first_name or p.user.username or '').strip(),
            'subtitle': (p.employee_code or '').strip(),
            'count': 0,
            'level': 'employee',
            'id': p.user_id,
            'user_id': p.user_id,
            'employee_code': p.employee_code or '',
            'dept_id': department_id,
            'division_id': division_id,
            'position_name': position_name,
            'children': [],
        }
        for p in qs[:MAX_EMPLOYEES_PER_POSITION]
    ]


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
            'position_key': position_node_key(division_id, pos.name, pos.pk),
            'children': _employee_nodes(department_id, division_id, pos.name),
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
            'position_key': position_node_key(division_id, name, None),
            'children': _employee_nodes(department_id, division_id, name),
        })
    return out[:MAX_POSITIONS_PER_DIVISION]


def build_org_tree(treemap: OrgTreemapContext) -> dict:
    """Cây JSON cho sơ đồ ngang (D3) — Công ty → Phòng ban → Bộ phận → Vị trí."""
    children: list[dict] = []

    for dept in treemap.departments:
        div_children: list[dict] = []
        for div in dept.divisions:
            div_children.append(
                _division_tree_node(
                    name=div.name,
                    staff_count=div.staff_count,
                    division_id=div.pk,
                    department_id=dept.pk,
                    is_active=div.is_active,
                    children=_position_children(dept.pk, div.pk),
                ),
            )
        head_subtitle, head_user_id, has_head = _department_head_line(dept.pk)
        dept_node: dict = {
            'name': dept.name,
            'count': dept.staff_count,
            'level': 'department',
            'id': dept.pk,
            'is_active': dept.is_active,
            'has_head': has_head,
            'head_user_id': head_user_id,
            'head_position': ORG_DEPARTMENT_HEAD_LABEL,
            'children': div_children,
        }
        if head_subtitle:
            dept_node['subtitle'] = head_subtitle
        children.append(dept_node)

    if treemap.unassigned_divisions:
        children.append({
            'name': 'Chưa gán phòng ban',
            'count': sum(d.staff_count for d in treemap.unassigned_divisions),
            'level': 'unassigned',
            'children': [
                _division_tree_node(
                    name=div.name,
                    staff_count=div.staff_count,
                    division_id=div.pk,
                    department_id=None,
                    is_active=div.is_active,
                    children=_position_children(None, div.pk),
                )
                for div in treemap.unassigned_divisions
            ],
        })

    dir_subtitle, dir_user_id, has_director = _executive_director_line()
    root: dict = {
        'name': ORG_COMPANY_ROOT,
        'count': treemap.total_staff,
        'level': 'root',
        'has_head': has_director,
        'head_user_id': dir_user_id,
        'children': children,
    }
    if dir_subtitle:
        root['subtitle'] = dir_subtitle
    else:
        root['subtitle'] = f'{treemap.executive_label} · {treemap.director_count} GĐ'
    return root


def filter_org_tree(node: dict, query: str) -> dict | None:
    """Lọc cây theo từ khóa — giữ nhánh khớp tên."""
    if not query:
        return node
    q = query.lower().strip()
    if not q:
        return node

    name = (node.get('name') or '').lower()
    subtitle = (node.get('subtitle') or '').lower()
    matched = q in name or (subtitle and q in subtitle)
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
