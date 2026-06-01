from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from hrm.module_permissions import MODULE_FEEDBACK, user_can_access_module, user_can_edit_module
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import FeedbackCreateForm
from .models import Feedback


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_FEEDBACK):
            messages.error(request, 'Bạn không có quyền truy cập module Góp ý.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper


def _manage_required(view_func):
    @_access_required
    def wrapper(request, *args, **kwargs):
        if not user_can_edit_module(request.user, MODULE_FEEDBACK):
            messages.error(request, 'Bạn không có quyền xem danh sách góp ý.')
            return redirect('feedback:create')
        return view_func(request, *args, **kwargs)

    return wrapper


def unviewed_feedback_count_for_manager(user):
    if not user_can_edit_module(user, MODULE_FEEDBACK):
        return 0
    return Feedback.objects.filter(viewed_at__isnull=True).count()


def feedback_count_for_manager(user):
    return unviewed_feedback_count_for_manager(user)


@_access_required
def feedback_hub(request):
    if user_can_edit_module(request.user, MODULE_FEEDBACK):
        return redirect('feedback:list')
    return redirect('feedback:create')


@_access_required
def create(request):
    if request.method == 'POST':
        form = FeedbackCreateForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.submitter = request.user
            feedback.save()
            messages.success(request, 'Cảm ơn bạn đã gửi góp ý.')
            return redirect('feedback:create')
    else:
        form = FeedbackCreateForm()
    return render(request, 'feedback/form.html', {'form': form})


@_manage_required
def feedback_list(request):
    search_query = get_search_query(request)
    qs = Feedback.objects.select_related('submitter', 'viewed_by')
    qs = apply_term_search(qs, search_query, ('title', 'body'))
    page_obj, query_string = paginate_queryset(request, qs)
    unviewed_count = Feedback.objects.filter(viewed_at__isnull=True).count()
    return render(request, 'feedback/list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'total_count': Feedback.objects.count(),
        'unviewed_count': unviewed_count,
    })


@_manage_required
def detail(request, pk):
    feedback = get_object_or_404(
        Feedback.objects.select_related('submitter', 'viewed_by'),
        pk=pk,
    )
    feedback.mark_viewed_by(request.user)
    feedback.refresh_from_db()
    return render(request, 'feedback/detail.html', {'feedback': feedback})
