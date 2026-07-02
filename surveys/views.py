from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_SURVEYS
from hrm.permissions import get_profile
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import SurveyCreateForm, SurveyReferenceForm, SurveyResponseForm
from .models import Survey, SurveyResponse


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
    if user_can_access_menu(request.user, MODULE_SURVEYS, 'manage'):
        return redirect('surveys:manage_list')
    if user_can_access_menu(request.user, MODULE_SURVEYS, 'create'):
        return redirect('surveys:create')
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
    qs = Survey.objects.select_related('created_by').prefetch_related('responses')
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
    qs = survey.responses.select_related('user')
    qs = apply_term_search(
        qs,
        search_query,
        ('full_name', 'employee_code', 'department_name', 'answer'),
    )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'surveys/result_detail.html', {
        'survey': survey,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'response_count': survey.response_count(),
    })


@login_required
def survey_fill(request, token):
    survey = get_object_or_404(Survey, token=token)
    if not survey.is_open:
        return render(request, 'surveys/fill_closed.html', {'survey': survey})

    existing = SurveyResponse.objects.filter(survey=survey, user=request.user).first()
    if existing:
        return render(request, 'surveys/fill_done.html', {
            'survey': survey,
            'response': existing,
            'already_submitted': True,
        })

    profile_snapshot = _snapshot_profile(request.user)
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

    return render(request, 'surveys/fill.html', {
        'survey': survey,
        'form': form,
        'profile': profile_snapshot,
    })
