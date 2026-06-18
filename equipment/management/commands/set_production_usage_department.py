from django.core.management.base import BaseCommand

from equipment.models import Device
from equipment.scope import SCOPE_PRODUCTION, filter_devices_for_scope
from hrm.models import Department

LABEL = 'Sản Xuất'


class Command(BaseCommand):
    help = 'Gan phong ban su dung "San Xuat" cho tat ca thiet bi san xuat.'

    def handle(self, *args, **options):
        qs = filter_devices_for_scope(Device.objects.all(), SCOPE_PRODUCTION)
        total = qs.count()
        dept = Department.objects.filter(name__iexact=LABEL).first()
        if not dept:
            dept = Department.objects.filter(name__icontains='Sản xuất').first()
        updated = qs.update(usage_department_text=LABEL, usage_department=dept)
        self.stdout.write(
            self.style.SUCCESS(
                f'Da cap nhat {updated}/{total} thiet bi san xuat -> "{LABEL}"'
                + (f' (FK phong ban id={dept.pk})' if dept else ' (chi text)')
            )
        )
