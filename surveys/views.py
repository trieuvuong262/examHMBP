from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from assessment.decorators import module_perm_required
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_SURVEYS
from hrm.permissions import get_profile
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import SurveyCreateForm, SurveyReferenceForm, SurveyResponseForm
from .models import Survey, SurveyResponse, SurveyView


def _profile_department_label(profile):
    if profile is None:
        return '—'
    if profile.division_id and profile.division:
        return profile.division.name
    if profile.department_id and profile.department:
        return profile.department.name
    return '—'


def _snapshot_profile(user):
    profile = get_profile(user)
    return {
        'employee_code': (profile.employee_code if profile else '') or '—',
        'full_name': (profile.full_name if profile else user.get_full_name()) or user.username,
        'department_name': _profile_department_label(profile),
    }


def _build_share_url(request, survey):
    path = survey.get_absolute_share_path()
    return request.build_absolute_uri(path)


@module_perm_required(MODULE_SURVEYS, 'view')
def survey_hub(request):
    if user_can_access_menu(request.user, MODULE_SURVEYS, 'create'):
        return redirect('surveys:create')
    if user_can_access_menu(request.user, MODULE_SURVEYS, 'share'):
        return redirect('surveys:manage_list')
    if user_can_access_menu(request.user, MODULE_SURVEYS, 'results'):
        return redirect('surveys:results')
    return redirect('home_portal')


@module_perm_required(MODULE_SURVEYS, 'create')
def survey_create(request):
    if request.method == 'POST':
        form = SurveyCreateForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.created_by = request.user
            survey.save()
            messages.success(request, 'Đã tạo khảo sát. Sao chép link gửi nhân viên tại mục Tạo link gửi NV.')
            return redirect('surveys:share_detail', pk=survey.pk)
    else:
        form = SurveyCreateForm()
    return render(request, 'surveys/create.html', {'form': form})


@module_perm_required(MODULE_SURVEYS, 'view')
def survey_manage_list(request):
    search_query = get_search_query(request)
    qs = Survey.objects.select_related('created_by')
    qs = apply_term_search(qs, search_query, ('title', 'question'))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'surveys/manage_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'total_count': Survey.objects.count(),
    })


@module_perm_required(MODULE_SURVEYS, 'update')
def survey_reference_edit(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if request.method == 'POST':
        form = SurveyReferenceForm(request.POST, instance=survey)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật link tham khảo.')
            return redirect('surveys:manage_list')
    else:
        form = SurveyReferenceForm(instance=survey)
    return render(request, 'surveys/reference_edit.html', {
        'form': form,
        'survey': survey,
    })


@module_perm_required(MODULE_SURVEYS, 'view')
def survey_share_detail(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    share_url = _build_share_url(request, survey)
    return render(request, 'surveys/share_detail.html', {
        'survey': survey,
        'share_url': share_url,
    })


@module_perm_required(MODULE_SURVEYS, 'view')
def survey_results(request):
    search_query = get_search_query(request)
    qs = Survey.objects.select_related('created_by').prefetch_related('responses', 'views')
    qs = apply_term_search(qs, search_query, ('title',))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'surveys/results_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_SURVEYS, 'view')
def survey_result_detail(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    search_query = get_search_query(request)
    response_by_user = {
        row.user_id: row
        for row in survey.responses.select_related('user')
    }
    rows = []
    viewed_user_ids = set()
    for viewed in survey.views.select_related('user'):
        viewed_user_ids.add(viewed.user_id)
        submitted = response_by_user.get(viewed.user_id)
        rows.append({
            'employee_code': viewed.employee_code,
            'full_name': viewed.full_name,
            'department_name': viewed.department_name,
            'answer': submitted.answer if submitted else '',
            'event_at': submitted.submitted_at if submitted else viewed.last_viewed_at,
            'is_submitted': bool(submitted),
        })

    # Dữ liệu cũ có thể đã gửi trước khi bật tracking "đã xem".
    for user_id, submitted in response_by_user.items():
        if user_id in viewed_user_ids:
            continue
        rows.append({
            'employee_code': submitted.employee_code,
            'full_name': submitted.full_name,
            'department_name': submitted.department_name,
            'answer': submitted.answer or '',
            'event_at': submitted.submitted_at,
            'is_submitted': True,
        })

    if search_query:
        needle = search_query.lower()
        rows = [
            row for row in rows
            if needle in (row['employee_code'] or '').lower()
            or needle in (row['full_name'] or '').lower()
            or needle in (row['department_name'] or '').lower()
            or needle in (row['answer'] or '').lower()
        ]

    rows.sort(key=lambda item: item['event_at'], reverse=True)
    paginator = Paginator(rows, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    query_string = params.urlencode()
    return render(request, 'surveys/result_detail.html', {
        'survey': survey,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@login_required
def survey_fill(request, token):
    survey = get_object_or_404(Survey, token=token)
    if not survey.is_open:
        return render(request, 'surveys/fill_closed.html', {'survey': survey})

    profile_snapshot = _snapshot_profile(request.user)
    SurveyView.objects.update_or_create(
        survey=survey,
        user=request.user,
        defaults={
            'employee_code': profile_snapshot['employee_code'],
            'full_name': profile_snapshot['full_name'],
            'department_name': profile_snapshot['department_name'],
            'last_viewed_at': timezone.now(),
        },
    )

    existing = SurveyResponse.objects.filter(survey=survey, user=request.user).first()
    if existing:
        return render(request, 'surveys/fill_done.html', {
            'survey': survey,
            'response': existing,
            'already_submitted': True,
        })

    if request.method == 'POST':
        form = SurveyResponseForm(request.POST)
        if form.is_valid():
            response = form.save(commit=False)
            response.survey = survey
            response.user = request.user
            response.employee_code = profile_snapshot['employee_code']
            response.full_name = profile_snapshot['full_name']
            response.department_name = profile_snapshot['department_name']
            response.save()
            messages.success(request, 'Đã gửi phản hồi. Cảm ơn bạn!')
            return render(request, 'surveys/fill_done.html', {
                'survey': survey,
                'response': response,
                'already_submitted': False,
            })
    else:
        form = SurveyResponseForm()

    learning_url = None
    if survey.required_course_id:
        learning_url = f"{reverse('course_start', args=[survey.required_course_id])}?{urlencode({'next': request.get_full_path(), 'ref': 'survey'})}"

    return render(request, 'surveys/fill.html', {
        'survey': survey,
        'form': form,
        'profile': profile_snapshot,
        'learning_url': learning_url,
    })
