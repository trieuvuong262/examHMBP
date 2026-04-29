from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import MetabaseReport 

@login_required
def dashboard(request):
    user = request.user
    is_staff = user.is_staff or user.is_superuser

    # ==========================================
    # XỬ LÝ FORM THÊM & XÓA BÁO CÁO (CHỈ ADMIN)
    # ==========================================
    if request.method == 'POST' and is_staff:
        action = request.POST.get('action')

        # XỬ LÝ XÓA
        if action == 'delete':
            report_id = request.POST.get('report_id')
            if report_id:
                MetabaseReport.objects.filter(id=report_id).delete()
                messages.success(request, "Đã xóa báo cáo thành công!")
            return redirect('reports:dashboard')

        # XỬ LÝ THÊM MỚI
        elif action == 'add':
            title = request.POST.get('title')
            raw_link = request.POST.get('link')
            report_type = request.POST.get('report_type')
            is_active = request.POST.get('is_active') == 'on'

            uuid = raw_link.strip()
            if '/public/dashboard/' in uuid:
                uuid = uuid.split('/public/dashboard/')[-1].split('?')[0]
            elif '/public/question/' in uuid:
                uuid = uuid.split('/public/question/')[-1].split('?')[0]

            if title and uuid:
                MetabaseReport.objects.create(
                    title=title, uuid=uuid, report_type=report_type, is_active=is_active
                )
                messages.success(request, f"Đã thêm báo cáo '{title}' thành công!")
            return redirect('reports:dashboard')

    # ==========================================
    # LẤY DANH SÁCH BÁO CÁO METABASE
    # ==========================================
    reports_list = MetabaseReport.objects.filter(is_active=True).order_by('-created_at')
    all_reports = MetabaseReport.objects.all().order_by('-created_at') if is_staff else []

    context = {
        'reports_list': reports_list,
        'all_reports': all_reports, 
        'design_url': "http://127.0.0.1:3000/question/new",
        'is_admin': is_staff,
    }
    
    return render(request, 'reports/dashboard.html', context)