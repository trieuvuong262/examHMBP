from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.models import User
from .models import KpiPeriod, YearlyKpi, YearlyKpiItem
import openpyxl
from django.http import HttpResponse
import datetime
# ========================================================
# 1. TRANG DANH SÁCH KPI (DASHBOARD CHÍNH)
# ========================================================
@login_required
def kpi_list_view(request):
    # 1. Lấy danh sách KPI của cá nhân và đội nhóm
    my_kpis = YearlyKpi.objects.filter(employee=request.user)
    team_kpis = YearlyKpi.objects.filter(direct_manager=request.user)
    
    # Lấy Role của User hiện tại (tránh lỗi nếu user chưa có profile)
    user_role = request.user.profile.role if hasattr(request.user, 'profile') else ''

    # Nếu là GM hoặc Admin thì thấy toàn bộ
    if user_role == 'GM' or request.user.is_superuser:
        team_kpis = YearlyKpi.objects.exclude(employee=request.user)

    # =================================================================
    # 🔥 FIX LỖI Ở ĐÂY: Xác định ai là Manager/GM để hiện nút thêm KPI
    # =================================================================
    is_admin = request.user.is_superuser
    is_manager_or_gm = is_admin or user_role in ['HOD', 'GM']

    # 2. XỬ LÝ QUYỀN ADMIN: Đóng/Mở kỳ đánh giá
    current_year = datetime.datetime.now().year
    admin_periods = []

    if is_admin:
        if request.method == 'POST' and 'toggle_period' in request.POST:
            p_type = request.POST.get('period_type')
            is_active = request.POST.get('is_active') == 'on' 
            
            period, created = KpiPeriod.objects.get_or_create(year=current_year, period_type=p_type)
            period.is_active = is_active
            period.save()
            messages.success(request, f"Đã {'MỞ' if is_active else 'ĐÓNG'} kỳ đánh giá {p_type}!")
            return redirect('kpi_list')
        
        standard_types = ['Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2', 'Y']
        for pt in standard_types:
            p, _ = KpiPeriod.objects.get_or_create(year=current_year, period_type=pt)
            admin_periods.append(p)

    # TRUYỀN BIẾN is_manager_or_gm RA HTML
    return render(request, 'kpi/kpi_list.html', {
        'my_kpis': my_kpis,
        'team_kpis': team_kpis,
        'is_admin': is_admin,
        'is_manager_or_gm': is_manager_or_gm,  # <--- Bắt buộc phải có dòng này nha ní!
        'admin_periods': admin_periods,
    })
@login_required
def kpi_detail_view(request, kpi_id):
    # 1. Lấy bảng KPI và các chỉ tiêu liên quan
    kpi_board = get_object_or_404(YearlyKpi, id=kpi_id)
    items = kpi_board.items.all().order_by('pillar')
    
    # 2. Lấy danh sách các kỳ ĐANG MỞ (Q1, Q2, Q3, Q4, H1, H2, Y)
    open_periods = KpiPeriod.objects.filter(year=kpi_board.year, is_active=True).values_list('period_type', flat=True)
    
    # 3. Phân quyền người dùng
    is_owner = (request.user == kpi_board.employee)
    is_manager = (request.user == kpi_board.direct_manager) or (kpi_board.employee in request.user.profile.subordinates.all())
    # GM hoặc Admin hoặc Superuser đều có quyền GM
    is_gm = (request.user == kpi_board.general_manager) or (request.user.profile.role == 'GM') or request.user.is_superuser
    
    # Nếu là Manager thì không cần làm Owner (để tránh xung đột logic nút bấm)
    if is_manager or is_gm:
        is_owner = (request.user == kpi_board.employee) # Giữ nguyên để biết lính tự xem bài mình

    if request.method == 'POST':
        target_period = request.POST.get('target_period') # Nhận Q1, Q2, H1, Y...
        action = request.POST.get('action', 'save') 

        if not target_period:
            messages.error(request, "Vui lòng chọn kỳ đánh giá cụ thể!")
            return redirect('kpi_detail', kpi_id=kpi_id)

        # Kiểm tra trạng thái đóng/mở kỳ từ Admin
        if target_period not in open_periods and action != 'save':
            messages.error(request, f"Kỳ đánh giá {target_period} hiện đang đóng, không thể nộp bài!")
            return redirect('kpi_detail', kpi_id=kpi_id)

        # Xác định tên trường trạng thái (VD: q1_status, y_status)
        status_attr = f"{target_period.lower()}_status"
        
        # Kiểm tra xem trường status có tồn tại trong Model không (đề phòng lỗi y_status chưa migrate)
        if not hasattr(kpi_board, status_attr):
            messages.error(request, f"Hệ thống chưa cấu hình trạng thái cho kỳ {target_period}!")
            return redirect('kpi_detail', kpi_id=kpi_id)
            
        current_status = getattr(kpi_board, status_attr)

        # 4. VÒNG LẶP LƯU ĐIỂM ĐỘNG
        for item in items:
            prefix = f"item_{item.id}_{target_period}_"
            
            try:
                # NHÂN VIÊN TỰ CHẤM
                if is_owner and current_status == 'self_evaluating':
                    val_self = request.POST.get(f"{prefix}self")
                    if val_self is not None:
                        setattr(item, f"{target_period.lower()}_self", float(val_self) if val_self.strip() != "" else None)
                
                # HOD CHẤM
                if is_manager and current_status == 'manager_evaluating':
                    val_mgr = request.POST.get(f"{prefix}mgr")
                    if val_mgr is not None:
                        setattr(item, f"{target_period.lower()}_mgr", float(val_mgr) if val_mgr.strip() != "" else None)
                    
                # GM CHỐT ĐIỂM
                if is_gm and current_status == 'general_evaluating':
                    val_gm = request.POST.get(f"{prefix}gm")
                    if val_gm is not None:
                        setattr(item, f"{target_period.lower()}_gm", float(val_gm) if val_gm.strip() != "" else None)
                
                item.save()
            except ValueError:
                messages.warning(request, f"Định dạng điểm không hợp lệ tại mục tiêu: {item.personal_objective}")
                continue

        # 5. CẬP NHẬT TRẠNG THÁI LUỒNG (Chỉ cập nhật khi bấm nút Nộp/Chốt)
        if action == 'submit_manager' and is_owner:
            setattr(kpi_board, status_attr, 'manager_evaluating')
            messages.success(request, f"Đã gửi đánh giá {target_period} cho Quản lý!")
            
        elif action == 'submit_gm' and is_manager:
            setattr(kpi_board, status_attr, 'general_evaluating')
            messages.success(request, f"Đã gửi kỳ {target_period} cho Quản lý cấp cao (GM)!")
            
        elif action == 'finish' and is_gm:
            setattr(kpi_board, status_attr, 'completed')
            messages.success(request, f"Chúc mừng! Đã chốt kết quả cuối cùng cho kỳ {target_period}!")
            
        else:
            messages.info(request, f"Đã lưu bản nháp dữ liệu kỳ {target_period}.")
            
        kpi_board.save()
        return redirect('kpi_detail', kpi_id=kpi_id)

    # 6. Render ra giao diện
    return render(request, 'kpi/kpi_form.html', {
        'kpi': kpi_board, 
        'items': items, 
        'open_periods': list(open_periods),
        'is_owner': is_owner, 
        'is_manager': is_manager, 
        'is_gm': is_gm
    })

# ========================================================
# 3. GIAO MỤC TIÊU NĂM (YEARLY SETUP)
# ========================================================
@login_required
def yearly_kpi_create(request):
    profile = request.user.profile
    
    # 1. CHẶN ĐỨNG NHÂN VIÊN (Quy trình Top-Down)
    if profile.role == 'EMPLOYEE' and not request.user.is_superuser:
        messages.error(request, "Quyền truy cập bị từ chối! Chỉ Quản lý mới được thiết lập KPI năm.")
        return redirect('kpi_list')

    # 2. Lấy danh sách nhân viên để thả vào Dropdown cho Sếp chọn
    if profile.role == 'HOD':
        # Sếp HOD chỉ được giao cho lính trực tiếp của mình
        target_employees = profile.subordinates.all()
    else:
        # Sếp GM hoặc Admin thì được giao cho tất cả mọi người
        target_employees = User.objects.filter(is_active=True).exclude(id=request.user.id)
        
    hod_list = User.objects.filter(profile__role='HOD', is_active=True)
    gm_list = User.objects.filter(Q(profile__role='GM') | Q(is_superuser=True), is_active=True)
    
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        year = request.POST.get('year', timezone.now().year)
        eval_type = request.POST.get('eval_type', 'QUARTER') # Bắt giá trị từ Form HTML mới
        
        # Sếp HOD tạo thì tự động gán mình làm Quản lý trực tiếp luôn
        direct_manager_id = request.user.id if profile.role == 'HOD' else request.POST.get('direct_manager_id')
        general_manager_id = request.POST.get('general_manager_id')

        # Dùng update_or_create để nếu HOD lỡ tạo trùng năm thì ghi đè luôn, không bị sập web
        yearly_kpi, created = YearlyKpi.objects.update_or_create(
            employee_id=employee_id, 
            year=year,
            defaults={
                'direct_manager_id': direct_manager_id or None,
                'general_manager_id': general_manager_id or None,
                'eval_type': eval_type
            }
        )
        
        # Xóa các mục tiêu cũ của năm đó đi để add cái mới vào
        if not created:
            yearly_kpi.items.all().delete()

        # Bắt mảng dữ liệu từ Table trong HTML
        pillars = request.POST.getlist('pillar[]')
        objectives = request.POST.getlist('personal_objective[]')
        indicators = request.POST.getlist('kpi_indicator[]')
        weightages = request.POST.getlist('weightage[]')
        targets = request.POST.getlist('yearly_target[]')
        units = request.POST.getlist('unit[]')
        trends = request.POST.getlist('trend[]')

        for i in range(len(pillars)):
            if objectives[i].strip() != '':
                YearlyKpiItem.objects.create(
                    yearly_kpi=yearly_kpi, 
                    pillar=pillars[i], 
                    personal_objective=objectives[i],
                    kpi_indicator=indicators[i], 
                    weightage=float(weightages[i]) if weightages[i] else 0.0,
                    yearly_target=float(targets[i]) if targets[i] else 0.0, 
                    unit=units[i], 
                    trend=trends[i]
                )
                
        messages.success(request, f"Đã thiết lập Mục tiêu KPI Năm {year} thành công!")
        return redirect('kpi_list')

    return render(request, 'kpi/yearly_kpi_form.html', {
        'target_employees': target_employees,
        'hod_list': hod_list, 
        'gm_list': gm_list, 
        'is_hod': profile.role == 'HOD'
    })

@login_required
def kpi_import_excel(request):
    profile = request.user.profile
    if profile.role == 'EMPLOYEE' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền này!")
        return redirect('kpi_list')

    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if not excel_file or not excel_file.name.endswith('.xlsx'):
            messages.error(request, "File không hợp lệ!")
            return redirect('kpi_import_excel')

        try:
            wb = openpyxl.load_workbook(excel_file, data_only=True)
            sheet = wb.active
            processed_users_for_year = set() 

            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not any(row): continue 
                email, year, pillar, objective, indicator, weight, target, unit, trend = row[:9]
                
                employee = User.objects.filter(email=email).first()
                if not employee: continue
                    
                board, created = YearlyKpi.objects.get_or_create(employee=employee, year=year)
                if f"{employee.id}_{year}" not in processed_users_for_year:
                    board.items.all().delete()
                    processed_users_for_year.add(f"{employee.id}_{year}")

                YearlyKpiItem.objects.create(
                    yearly_kpi=board, pillar=pillar, personal_objective=objective,
                    kpi_indicator=indicator, weightage=float(weight or 0),
                    yearly_target=float(target or 0), unit=unit, trend=trend or 'HIGHER'
                )
            messages.success(request, "Import thành công!")
            return redirect('kpi_list')
        except Exception as e:
            messages.error(request, f"Lỗi: {str(e)}")
    return render(request, 'kpi/kpi_import.html')

@login_required
def download_kpi_sample_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Email NV", "Năm", "Lĩnh vực", "Mục tiêu", "Chỉ số đo", "Trọng số (%)", "Chỉ tiêu", "Đơn vị", "Xu hướng"])
    ws.append(["luu.dao@hoanmy.com", 2026, "FINANCE", "Mục tiêu mẫu", "Chỉ số mẫu", 20, 100, "%", "HIGHER"])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_KPI.xlsx'
    wb.save(response)
    return response