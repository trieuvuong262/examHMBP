"""One-shot: set usage department to Sản Xuất for all production-scope devices."""
from equipment.models import Device
from equipment.scope import SCOPE_PRODUCTION, filter_devices_for_scope
from hrm.models import Department

LABEL = 'Sản Xuất'

qs = filter_devices_for_scope(Device.objects.all(), SCOPE_PRODUCTION)
count = qs.count()
dept = Department.objects.filter(name__iexact='Sản Xuất').first()
if not dept:
    dept = Department.objects.filter(name__icontains='Sản xuất').first()

updated = qs.update(
    usage_department_text=LABEL,
    usage_department=dept,
)
print(f'production_devices={count} updated={updated} dept_fk={dept.pk if dept else None}')
