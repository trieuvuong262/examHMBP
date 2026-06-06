from django.db.models import Count

from kiotviet.models import KvProductInventory

for row in (
    KvProductInventory.objects.values('branch_name')
    .annotate(c=Count('id'))
    .order_by('branch_name')
):
    print(row['branch_name'], '|', row['c'])
