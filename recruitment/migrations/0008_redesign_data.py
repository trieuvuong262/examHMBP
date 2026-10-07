"""Chuyển dữ liệu Tuyển dụng sang cấu trúc mới.

- JobPosting.is_active → status (open / closed); department text → target_department FK.
- Interview.passed → result.
- Candidate.hr_note → CandidateEvent (ghi chú) để không mất dữ liệu khi bỏ cột.
- Mỗi ứng viên có sự kiện «Tạo hồ sơ» làm mốc lịch sử.
"""

from django.db import migrations


def forward(apps, schema_editor):
    JobPosting = apps.get_model('recruitment', 'JobPosting')
    Candidate = apps.get_model('recruitment', 'Candidate')
    Interview = apps.get_model('recruitment', 'Interview')
    CandidateEvent = apps.get_model('recruitment', 'CandidateEvent')
    Department = apps.get_model('hrm', 'Department')

    for job in JobPosting.objects.all():
        job.status = 'open' if job.is_active else 'closed'
        name = (job.department or '').strip()
        if name and not job.target_department_id:
            job.target_department = Department.objects.filter(name__iexact=name).first()
        job.save(update_fields=['status', 'target_department'])

    for interview in Interview.objects.all():
        if interview.passed is True:
            interview.result = 'pass'
        elif interview.passed is False:
            interview.result = 'fail'
        else:
            interview.result = 'pending'
        interview.save(update_fields=['result'])

    events = []
    for cand in Candidate.objects.all():
        events.append(CandidateEvent(
            candidate=cand, kind='created', to_status=cand.status,
            message='Hồ sơ có trước khi nâng cấp module.', created_at=cand.applied_at,
        ))
        note = (cand.hr_note or '').strip()
        if note:
            events.append(CandidateEvent(
                candidate=cand, kind='note', message=note, created_at=cand.applied_at,
            ))
        legacy = [
            ('Số GPHN/CCHN', cand.license_number),
            ('Phạm vi hành nghề', cand.scope_of_practice),
            ('Vị trí chuyên môn', cand.professional_position),
            ('Ghi chú CCHN', cand.license_note),
        ]
        legacy_lines = [f'{label}: {value}' for label, value in legacy if (value or '').strip()]
        if legacy_lines:
            # Trường CCHN bị xóa — lưu lại một lần vào lịch sử để tra cứu.
            events.append(CandidateEvent(
                candidate=cand, kind='note',
                message='Dữ liệu CCHN cũ:\n' + '\n'.join(legacy_lines),
                created_at=cand.applied_at,
            ))
    CandidateEvent.objects.bulk_create(events)


def backward(apps, schema_editor):
    JobPosting = apps.get_model('recruitment', 'JobPosting')
    for job in JobPosting.objects.all():
        job.is_active = job.status == 'open'
        job.save(update_fields=['is_active'])


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0007_redesign_fields'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
