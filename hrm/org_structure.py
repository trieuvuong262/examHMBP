"""Sơ đồ cơ cấu tổ chức — treemap: GDĐH → Phòng ban → Bộ phận."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count, Prefetch, Q

from hrm.models import Department, Division, Profile
from hrm.permissions import ROLE_DIRECTOR

ORG_EXECUTIVE_LABEL = 'Giám đốc điều hành'


@dataclass
class OrgDivisionNode:
    pk: int
    name: str
    sort_order: int
    is_active: bool
    staff_count: int


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
            )
            for div in dept.divisions.all()
        ]
        div_staff = sum(d.staff_count for d in div_nodes)
        weight = max(dept.staff_count, div_staff, len(div_nodes), 1)
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

    unassigned = [
        OrgDivisionNode(
            pk=div.pk,
            name=div.name,
            sort_order=div.sort_order,
            is_active=div.is_active,
            staff_count=div.staff_count,
        )
        for div in divisions_qs.filter(department__isnull=True)
    ]

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
            'Vị trí (cấp thấp nhất) nhập tự do tại hồ sơ nhân viên — '
            'không quản lý trong sơ đồ này.'
        ),
    )


def divisions_for_department(department_id: int | None):
    """Queryset bộ phận theo phòng ban (dropdown nhân sự)."""
    qs = Division.objects.filter(is_active=True).select_related('department')
    if not department_id:
        return qs.order_by('sort_order', 'name')
    return qs.filter(Q(department_id=department_id) | Q(department__isnull=True)).order_by(
        'sort_order', 'name',
    )
