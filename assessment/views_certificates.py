"""Quản lý và xem chứng chỉ hoàn thành kỳ thi."""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from PortalJustPlay.list_search import get_search_query, search_terms
from PortalJustPlay.pagination import paginate_queryset
from assessment.certificates import maybe_issue_certificate, recipient_display_name, revoke_certificate
from assessment.decorators import module_perm_required
from assessment.forms import CertificateTemplateForm
from assessment.models import Certificate, CertificateTemplate, Exam, ExamSubmission
from hrm.module_permissions import MODULE_ASSESSMENT, user_can_edit_module
from hrm.permissions import is_portal_admin


def _preview_cert(template, user=None):
    now = timezone.localtime(timezone.now())
    name = recipient_display_name(user) if user else 'Nguyễn Văn A'
    return {
        'code': 'JP-PREVIEW',
        'recipient_name': name,
        'exam_title': 'Kỳ thi mẫu',
        'score': 8.5,
        'body_text': (template.body_text or '').format(
            name=name,
            exam_title='Kỳ thi mẫu',
            score='8.5',
            date=now.strftime('%d/%m/%Y'),
            code='JP-PREVIEW',
        ),
        'issued_at': now,
        'template': template,
        'is_revoked': False,
    }


@module_perm_required(MODULE_ASSESSMENT, 'edit')
def admin_certificate_list(request):
    search_query = get_search_query(request)
    exam_id = request.GET.get('exam', '').strip()
    status = request.GET.get('status', '').strip()
    qs = Certificate.objects.select_related(
        'user', 'user__profile', 'exam', 'template',
    ).order_by('-issued_at')
    if exam_id:
        qs = qs.filter(exam_id=exam_id)
    if status == 'active':
        qs = qs.filter(is_revoked=False)
    elif status == 'revoked':
        qs = qs.filter(is_revoked=True)
    if search_query:
        for term in search_terms(search_query):
            qs = qs.filter(
                Q(code__icontains=term)
                | Q(recipient_name__icontains=term)
                | Q(exam_title__icontains=term)
                | Q(user__username__icontains=term)
                | Q(user__profile__full_name__icontains=term)
                | Q(user__profile__employee_code__icontains=term)
            )
        qs = qs.distinct()

    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'assessment/admin/certificate_list.html', {
        'certificates': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'exam_id': exam_id,
        'status': status,
        'exams': Exam.objects.order_by('title'),
        'total_count': page_obj.paginator.count,
        'active_count': Certificate.objects.filter(is_revoked=False).count(),
        'revoked_count': Certificate.objects.filter(is_revoked=True).count(),
        'template_count': CertificateTemplate.objects.count(),
    })


@module_perm_required(MODULE_ASSESSMENT, 'update')
def admin_certificate_revoke(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    if request.method == 'POST':
        revoke_certificate(cert, by=request.user)
        messages.success(request, f'Đã thu hồi chứng chỉ {cert.code}.')
        return redirect('admin_certificate_list')
    return render(request, 'assessment/admin/certificate_revoke.html', {'cert': cert})


@module_perm_required(MODULE_ASSESSMENT, 'update')
def admin_certificate_reissue(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    if request.method != 'POST':
        return redirect('admin_certificate_list')
    submission = cert.submission
    if submission is None:
        submission = (
            ExamSubmission.objects.filter(user=cert.user, exam=cert.exam, submitted_at__isnull=False)
            .order_by('-submitted_at')
            .first()
        )
    if submission is None:
        messages.error(request, 'Không tìm thấy bài nộp để cấp lại chứng chỉ.')
        return redirect('admin_certificate_list')
    cert.is_revoked = False
    cert.save(update_fields=['is_revoked'])
    issued = maybe_issue_certificate(submission)
    if issued:
        messages.success(request, f'Đã cấp lại chứng chỉ {issued.code}.')
    else:
        messages.warning(request, 'Không cấp lại được. Kiểm tra điểm đạt và trạng thái chấm bài.')
    return redirect('admin_certificate_list')


@module_perm_required(MODULE_ASSESSMENT, 'edit')
def admin_template_list(request):
    templates = CertificateTemplate.objects.order_by('-is_default', 'name')
    return render(request, 'assessment/admin/certificate_template_list.html', {
        'templates': templates,
    })


@module_perm_required(MODULE_ASSESSMENT, 'create')
def admin_template_create(request):
    return _template_form(request, instance=None, title='Thêm mẫu chứng chỉ')


@module_perm_required(MODULE_ASSESSMENT, 'update')
def admin_template_edit(request, pk):
    instance = get_object_or_404(CertificateTemplate, pk=pk)
    return _template_form(request, instance=instance, title='Sửa mẫu chứng chỉ')


def _template_form(request, instance, title):
    if request.method == 'POST':
        form = CertificateTemplateForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã lưu mẫu chứng chỉ.')
            return redirect('admin_certificate_templates')
    else:
        form = CertificateTemplateForm(instance=instance)
    preview = _preview_cert(form.instance, request.user)
    return render(request, 'assessment/admin/certificate_template_form.html', {
        'form': form,
        'title': title,
        'template': instance,
        'preview_cert': preview,
    })


@module_perm_required(MODULE_ASSESSMENT, 'delete')
def admin_template_delete(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    if request.method == 'POST':
        template.delete()
        messages.success(request, 'Đã xóa mẫu chứng chỉ.')
        return redirect('admin_certificate_templates')
    return render(request, 'assessment/admin/certificate_template_delete.html', {'template': template})


@module_perm_required(MODULE_ASSESSMENT, 'view')
def my_certificates(request):
    qs = Certificate.objects.filter(
        user=request.user, is_revoked=False,
    ).select_related('exam', 'template').order_by('-issued_at')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'assessment/my_certificates.html', {
        'certificates': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
    })


@module_perm_required(MODULE_ASSESSMENT, 'view')
def certificate_view(request, pk):
    cert = get_object_or_404(Certificate.objects.select_related('template', 'exam', 'user'), pk=pk)
    can_manage = is_portal_admin(request.user) or user_can_edit_module(request.user, MODULE_ASSESSMENT)
    if cert.user_id != request.user.id and not can_manage:
        messages.error(request, 'Bạn không có quyền xem chứng chỉ này.')
        return redirect('exam_list')
    if cert.is_revoked and cert.user_id == request.user.id and not can_manage:
        messages.error(request, 'Chứng chỉ này đã bị thu hồi.')
        return redirect('my_certificates')
    return render(request, 'assessment/certificate_view.html', {'cert': cert})
