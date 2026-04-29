import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from kpi.models import YearlyKpi, YearlyKpiItem 

@login_required
def dashboard_view(request):
    user = request.user
    is_staff = user.is_staff or user.is_superuser

    # 1. PHÂN QUYỀN TRUY VẤN
    if is_staff:
        base_query = YearlyKpi.objects.all()
        item_query = YearlyKpiItem.objects.all()
    else:
        base_query = YearlyKpi.objects.filter(Q(employee=user) | Q(direct_manager=user))
        item_query = YearlyKpiItem.objects.filter(yearly_kpi__in=base_query)

    # 2. THỐNG KÊ SỐ LIỆU (Sửa lỗi 'status' thành 'y_status')
    total_kpis = base_query.count()
    # Ở đây tui dùng y_status (trạng thái năm) làm chuẩn để đếm hoàn thành
    completed_kpis = base_query.filter(y_status='completed').count()
    pending_kpis = total_kpis - completed_kpis
    
    # Tính điểm trung bình (Sửa field thành y_gm - Điểm GM chốt cuối năm)
    avg_score_data = item_query.aggregate(Avg('y_gm'))['y_gm__avg']
    avg_score = round(avg_score_data, 1) if avg_score_data else 0

    # 3. DỮ LIỆU CHO BIỂU ĐỒ TRÒN (Trạng thái năm)
    status_counts = base_query.values('y_status').annotate(count=Count('id'))
    # Tạo từ điển dịch trạng thái thủ công nếu ní chưa có STATUS_CHOICES trong model
    status_map = {
        'draft': 'Bản nháp',
        'self_evaluating': 'NV Đang làm',
        'manager_evaluating': 'Sếp đang chấm',
        'completed': 'Hoàn tất'
    }
    
    status_labels = []
    status_data = []
    for item in status_counts:
        label = status_map.get(item['y_status'], item['y_status'])
        status_labels.append(label)
        status_data.append(item['count'])

    # 4. DỮ LIỆU CHO BIỂU ĐỒ CỘT (Điểm theo chức danh)
    # Lưu ý: tui dùng 'yearly_kpi__employee__profile__position' dựa trên quan hệ Model của ní
    position_scores = item_query.values('yearly_kpi__employee__profile__position').annotate(
        avg=Avg('y_gm')
    ).exclude(yearly_kpi__employee__profile__position='')

    pos_labels = []
    pos_data = []
    for item in position_scores:
        pos_labels.append(item['yearly_kpi__employee__profile__position'])
        pos_data.append(round(item['avg'] or 0, 1))

    # 5. CẤU HÌNH NHÚNG METABASE
    # Thay UUID thật của ní vào đây
    UUID_BAO_CAO_CHOT = "808f9c1e-b83c-4d57-8975-d227f6e80689"

    if is_staff:
        metabase_url = "http://127.0.0.1:3000/collection/root"
    else:
        metabase_url = f"http://127.0.0.1:3000/public/dashboard/{UUID_BAO_CAO_CHOT}"

    context = {
        'total_kpis': total_kpis,
        'completed_kpis': completed_kpis,
        'pending_kpis': pending_kpis,
        'avg_score': avg_score,
        'status_labels': json.dumps(status_labels),
        'status_data': json.dumps(status_data),
        'pos_labels': json.dumps(pos_labels),
        'pos_data': json.dumps(pos_data),
        'metabase_url': metabase_url,
        'is_admin': is_staff,
    }
    
    return render(request, 'reports/dashboard.html', context)