import json
from django.shortcuts import render
from django.db.models import Count, Avg, F, ExpressionWrapper, fields
from django.utils import timezone
from datetime import timedelta

import json
from django.shortcuts import render
from django.db.models import Count
from django.utils import timezone

from recruitment.models import Candidate, JobPosting

def main_dashboard(request):
    # ==========================================
    # 1. DATA CHO TAB: TUYỂN DỤNG (RECRUITMENT)
    # ==========================================
    status_order = ['new', 'reviewing', 'interviewing', 'offered', 'hired']
    funnel_labels = ['CV Mới', 'Xem xét', 'Phỏng vấn', 'Gửi Offer', 'Nhận việc'] # <-- Tui đã sửa tên biến ở đây!
    
    cand_counts = Candidate.objects.values('status').annotate(total=Count('id'))
    counts_dict = {item['status']: item['total'] for item in cand_counts}
    funnel_values = [counts_dict.get(s, 0) for s in status_order]

    # Tính Time-to-Fill (TB số ngày tuyển dụng)
    hired_candidates = Candidate.objects.filter(status='hired')
    avg_days = 0
    if hired_candidates.exists():
        total_days = sum([(timezone.now() - c.applied_at).days for c in hired_candidates])
        avg_days = round(total_days / hired_candidates.count(), 1)

    # Hiệu quả nguồn (Giả lập nếu chưa có field 'source')
    source_labels = ['Website', 'Facebook', 'Nội bộ', 'TopCV']
    source_values = [40, 25, 15, 20] 

    # Tỷ lệ đáp ứng
    jobs = JobPosting.objects.filter(is_active=True)
    fulfillment_labels = [j.title[:15] + '...' for j in jobs]
    full_target = [getattr(j, 'vacancies', 5) for j in jobs] # Giả định mục tiêu là 5
    full_actual = [Candidate.objects.filter(job_posting=j, status='hired').count() for j in jobs]

    # Tỷ lệ rớt Offer
    rejected_after_offer = Candidate.objects.filter(status='rejected', hr_note__icontains='offer').count()
    drop_labels = ['Chấp nhận Offer', 'Từ chối Offer']
    drop_values = [hired_candidates.count(), rejected_after_offer or 2] # Dummy 2 nếu ko có data

    # Gói gọn Data Tuyển dụng
    rec_data = {
        'funnel_labels': funnel_labels, 
        'funnel_values': funnel_values,
        'avg_fill_time': avg_days,
        'source_labels': source_labels, 
        'source_values': source_values,
        'full_labels': fulfillment_labels, 
        'full_target': full_target, 
        'full_actual': full_actual,
        'drop_labels': drop_labels, 
        'drop_values': drop_values,
    }

    # ==========================================
    # 2. TRUYỀN RA TEMPLATE
    # ==========================================
    context = {
        'rec_data': json.dumps(rec_data),
    }
    return render(request, 'reports/dashboard.html', context)

def recruitment_report_view(request):
    # --- 1. PHỄU TUYỂN DỤNG (Conversion Funnel) ---
    status_order = ['new', 'reviewing', 'interviewing', 'offered', 'hired']
    status_labels = ['CV Mới', 'Xem xét', 'Phỏng vấn', 'Gửi Offer', 'Nhận việc']
    cand_counts = Candidate.objects.values('status').annotate(total=Count('id'))
    counts_dict = {item['status']: item['total'] for item in cand_counts}
    funnel_values = [counts_dict.get(s, 0) for s in status_order]

    # --- 2. THỜI GIAN TUYỂN DỤNG (Time-to-Fill) ---
    # Tính trung bình số ngày từ lúc ứng tuyển đến lúc nhận việc (status='hired')
    # Giả sử file models của ní có trường applied_at và ta dùng auto_now của status update
    # Ở đây tui demo tính trung bình dựa trên dữ liệu hired
    hired_candidates = Candidate.objects.filter(status='hired')
    # Logic: avg(ngày_hiện_tại - ngày_nộp) cho những người đã đậu
    # (Lưu ý: Nếu ní có trường hired_date thì sẽ chính xác hơn)
    avg_days = 0
    if hired_candidates.exists():
        total_days = sum([(timezone.now() - c.applied_at).days for c in hired_candidates])
        avg_days = round(total_days / hired_candidates.count(), 1)

    # --- 3. HIỆU QUẢ NGUỒN TUYỂN (Source of Hire) ---
    # Giả sử ní thêm trường 'source' vào model Candidate (Facebook, LinkedIn, Website...)
    # Nếu chưa có, ní có thể fake data hoặc dùng tạm trường job_posting để demo
    source_data = Candidate.objects.values('source').annotate(total=Count('id')) if hasattr(Candidate, 'source') else []
    source_labels = [s['source'] for s in source_data] or ['Website', 'Facebook', 'Nội bộ', 'TopCV']
    source_values = [s['total'] for s in source_data] or [40, 25, 15, 20] # Data demo nếu chưa có field

    # --- 4. TỶ LỆ ĐÁP ỨNG NHU CẦU (Fulfillment Rate) ---
    # So sánh Số lượng cần tuyển (vacancies) vs Số lượng đã tuyển (status='hired')
    jobs = JobPosting.objects.filter(is_active=True)
    fulfillment_labels = [j.title[:15] + '...' for j in jobs]
    target_values = [getattr(j, 'vacancies', 5) for j in jobs] # Giả sử có trường vacancies
    actual_values = []
    for j in jobs:
        actual = Candidate.objects.filter(job_posting=j, status='hired').count()
        actual_values.append(actual)

    # --- 5. TỶ LỆ RỚT OFFER (Drop-out Rate) ---
    # So sánh số người được 'offered' nhưng trạng thái cuối là 'rejected'
    offered_count = Candidate.objects.filter(status='offered').count() + Candidate.objects.filter(status='hired').count()
    rejected_after_offer = Candidate.objects.filter(status='rejected', hr_note__icontains='offer').count()
    
    drop_out_labels = ['Chấp nhận Offer', 'Từ chối Offer']
    drop_out_values = [hired_candidates.count(), rejected_after_offer or 5]

    rec_data = {
        'funnel_labels': status_labels,
        'funnel_values': funnel_values,
        'avg_fill_time': avg_days,
        'source_labels': source_labels,
        'source_values': source_values,
        'full_labels': fulfillment_labels,
        'full_target': target_values,
        'full_actual': actual_values,
        'drop_labels': drop_out_labels,
        'drop_values': drop_out_values,
    }

    return render(request, 'reports/recruitment_dashboard.html', {'data_json': json.dumps(rec_data)})