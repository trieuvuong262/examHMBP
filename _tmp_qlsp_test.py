import traceback
from datetime import date, timedelta
from django.test.utils import setup_test_environment, override_settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db import transaction

setup_test_environment()
User = get_user_model()
admin = User.objects.filter(is_superuser=True, is_active=True).first()
print('admin', admin)

from kho_san_pham.models import Product
style = Product.objects.exclude(style_code='').values_list('style_code', flat=True).first()
print('style', style)

def run():
    c = Client()
    c.force_login(admin)
    urls = [
        '/', '/thiet-ke-san-pham/',
        '/ke-hoach-ra-mat/', '/ke-hoach-ra-mat/ke-hoach/', '/ke-hoach-ra-mat/ke-hoach/?f=risk',
        '/ke-hoach-ra-mat/ke-hoach/tao/', '/ke-hoach-ra-mat/lich/', '/ke-hoach-ra-mat/lich/?view=quarter',
        '/ke-hoach-ra-mat/viec-cua-toi/', '/ke-hoach-ra-mat/cho-duyet/', '/ke-hoach-ra-mat/thiet-lap/',
        '/kho-san-pham/thu-vien/', '/kho-san-pham/thu-vien/?status=inactive', '/kho-san-pham/thu-vien/?q=a&status=all',
        '/kho-san-pham/danh-muc/', '/kho-san-pham/thiet-lap-ma/',
        '/san-xuat/',
    ]
    if style:
        for t in ('data', 'sku', 'images', 'channels', 'history'):
            urls.append('/kho-san-pham/thu-vien/%s/?tab=%s' % (style, t))
    for u in urls:
        try:
            r = c.get(u)
            body = r.content.decode('utf-8', 'ignore')
            extra = ''
            if u == '/':
                extra = ' qlsp=%s launcher=%s' % ('jp-qlsp-group' in body, 'jp-qlsp-' in body)
            print(r.status_code, u, extra, r.get('Location', ''))
        except Exception:
            print('EXC', u); traceback.print_exc()

    # workflow
    from ra_mat_sp.models import LaunchPlan
    from thiet_ke_sp.models import ProductDevelopment
    d = ProductDevelopment.objects.first()
    sid = transaction.savepoint()
    try:
        data = {
            'name': 'TEST RM', 'launch_date': (date.today() + timedelta(days=40)).isoformat(),
            'coordinator': admin.pk, 'approver': admin.pk, 'scope': 'new', 'channels': 'store',
            'objective': 'x', 'target_qty': '100', 'target_revenue': '1000000', 'marketing_budget': '0',
        }
        if d:
            data['dossiers'] = [d.pk]
        r = c.post('/ke-hoach-ra-mat/ke-hoach/tao/', data)
        print('create', r.status_code, r.get('Location', ''))
        if r.status_code != 302:
            body = r.content.decode('utf-8', 'ignore')
            import re
            print(re.findall(r'invalid-feedback[^>]*>([^<]+)', body)[:10])
            print(re.findall(r'name="(\w+)"', body)[:40])
        p = LaunchPlan.objects.filter(name='TEST RM').first()
        if p:
            print('tasks', p.tasks.count(), 'status', p.status)
            base = '/ke-hoach-ra-mat/ke-hoach/%s/' % p.pk
            for t in ('overview', 'products', 'timeline', 'work', 'risks', 'go', 'post', 'history'):
                r = c.get(base + '?tab=' + t)
                print(r.status_code, 'tab', t)
            r = c.get(base + 'sua/'); print(r.status_code, 'edit')
            act = base + 'thao-tac/%s/'
            r = c.post(act % 'submit_plan', {}); print('submit_plan', r.status_code, p.__class__.objects.get(pk=p.pk).status)
            r = c.post(act % 'decide_plan', {'decision': 'approved', 'note': 'ok'}); print('decide_plan', r.status_code, LaunchPlan.objects.get(pk=p.pk).status)
            task = p.tasks.first()
            r = c.post(act % 'task_update', {'task': task.pk, 'status': 'done', 'evidence': 'link', 'delay_reason': 'x', 'owner': admin.pk, 'due_date': task.due_date.isoformat() if task.due_date else ''})
            print('task_update', r.status_code, p.tasks.get(pk=task.pk).status)
            r = c.post(act % 'task_add', {'group': 'marketing', 'title': 'Việc thêm', 'offset_days': '-5', 'importance': 'normal', 'owner': admin.pk})
            print('task_add', r.status_code, p.tasks.count())
            r = c.post(act % 'risk_add', {'title': 'Rủi ro', 'severity': 'high', 'mitigation': 'x', 'owner': admin.pk})
            print('risk_add', r.status_code, p.risks.count(), LaunchPlan.objects.get(pk=p.pk).status)
            rk = p.risks.first()
            if rk:
                r = c.post(act % 'risk_resolve', {'risk': rk.pk}); print('risk_resolve', r.status_code)
            r = c.post(act % 'submit_go', {}); print('submit_go', r.status_code, LaunchPlan.objects.get(pk=p.pk).status)
            r = c.post(act % 'decide_go', {'decision': 'postpone', 'new_launch_date': (date.today() + timedelta(days=60)).isoformat(), 'note': 'lùi'})
            print('decide_go postpone', r.status_code, LaunchPlan.objects.get(pk=p.pk).status, LaunchPlan.objects.get(pk=p.pk).launch_date)
            r = c.post(act % 'pause', {'note': 'tạm'}); print('pause', r.status_code, LaunchPlan.objects.get(pk=p.pk).status)
            r = c.post(act % 'resume', {'note': 'tiếp'}); print('resume', r.status_code, LaunchPlan.objects.get(pk=p.pk).status)
            for t in ('overview', 'go', 'history', 'work'):
                r = c.get(base + '?tab=' + t); print(r.status_code, 'tab after', t)
            for u in ('/ke-hoach-ra-mat/', '/ke-hoach-ra-mat/ke-hoach/', '/ke-hoach-ra-mat/lich/', '/ke-hoach-ra-mat/viec-cua-toi/', '/ke-hoach-ra-mat/cho-duyet/', '/'):
                r = c.get(u); print(r.status_code, 'with data', u)
            # messages from last redirect
            from django.contrib.messages import get_messages
    except Exception:
        traceback.print_exc()
    finally:
        transaction.savepoint_rollback(sid)

with override_settings(ALLOWED_HOSTS=['*']):
    with transaction.atomic():
        run()
        transaction.set_rollback(True)
print('done')
