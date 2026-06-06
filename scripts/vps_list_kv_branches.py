from kiotviet.models import KvBranch

for b in KvBranch.objects.order_by('branch_name'):
    print(b.kiotviet_id, '|', b.branch_name, '|', b.branch_code)
