from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from hrm.module_permissions import MODULE_FEEDBACK, user_can_access_module, user_can_edit_module
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import FeedbackCreateForm, FeedbackReplyForm, FeedbackStatusForm
from .models import Feedback


STATUS_TABS = [
    ('', 'Tất cả'),
    (Feedback.STATUS_NEW, 'Mới'),
    (Feedback.STATUS_IN_REVIEW, 'Đang xử lý'),
    (Feedback.STATUS_RESOLVED, 'Đã phản hồi'),
    (Feedback.STATUS_CLOSED, 'Đã đóng'),
]


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_FEEDBACK):
            messages.error(request, 'Bạn không có quyền truy cập module Góp ý.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper


def _edit_required(view_func):
    @_access_required
    def wrapper(request, *args, **kwargs):
        if not user_can_edit_module(request.user, MODULE_FEEDBACK):
            messages.error(request, 'Bạn không có quyền xử lý góp ý.')
            return redirect('feedback:my_list')
        return view_func(request, *args, **kwargs)

    return wrapper


def _can_view_feedback(user, feedback):
    if user_can_edit_module(user, MODULE_FEEDBACK):
        return True
    return feedback.submitter_id == user.id


def _pending_review_count():
    return Feedback.objects.filter(status__in=Feedback.OPEN_STATUSES).count()


def _subnav_context(request):
    ctx = {'pending_count': 0}
    if user_can_edit_module(request.user, MODULE_FEEDBACK):
        ctx['pending_count'] = _pending_review_count()
    return ctx


def _filter_status(qs, status_key):
    if status_key:
        return qs.filter(status=status_key)
    return qs


def _list_context(request, *, queryset, current_status=''):
    search_query = get_search_query(request)
    qs = apply_term_search(queryset, search_query, ('title', 'body'))
    qs = _filter_status(qs, current_status)
    page_obj, query_string = paginate_queryset(request, qs)
    return {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'status_tabs': STATUS_TABS,
        'current_status': current_status,
        **_subnav_context(request),
    }


@_access_required
def feedback_hub(request):
    return redirect('feedback:my_list')


@_access_required
def my_list(request):
    qs = Feedback.objects.filter(submitter=request.user).select_related('submitter', 'assigned_to')
    ctx = _list_context(request, queryset=qs, current_status=request.GET.get('status', ''))
    return render(request, 'feedback/my_list.html', ctx)


@_access_required
def create(request):
    if request.method == 'POST':
        form = FeedbackCreateForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.submitter = request.user
            feedback.save()
            messages.success(request, 'Đã gửi góp ý. Ban quản lý sẽ phản hồi sớm nhất có thể.')
            return redirect('feedback:detail', pk=feedback.pk)
    else:
        form = FeedbackCreateForm()
    return render(request, 'feedback/form.html', {
        'form': form,
        **_subnav_context(request),
    })


@_edit_required
def review_list(request):
    qs = Feedback.objects.select_related('submitter', 'assigned_to')
    ctx = _list_context(request, queryset=qs, current_status=request.GET.get('status', ''))
    ctx['is_review_queue'] = True
    return render(request, 'feedback/review_list.html', ctx)


@_access_required
def detail(request, pk):
    feedback = get_object_or_404(
        Feedback.objects.select_related('submitter', 'assigned_to').prefetch_related('replies__author'),
        pk=pk,
    )
    if not _can_view_feedback(request.user, feedback):
        messages.error(request, 'Bạn không có quyền xem góp ý này.')
        return redirect('feedback:my_list')

    can_manage = user_can_edit_module(request.user, MODULE_FEEDBACK)
    reply_form = FeedbackReplyForm()
    status_form = FeedbackStatusForm(initial={'status': feedback.status})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'follow_up':
            if feedback.submitter_id != request.user.id:
                messages.error(request, 'Chỉ người gửi mới có thể bổ sung góp ý.')
                return redirect('feedback:detail', pk=pk)
            if not feedback.is_open:
                messages.error(request, 'Góp ý đã đóng, không thể bổ sung thêm.')
                return redirect('feedback:detail', pk=pk)
            reply_form = FeedbackReplyForm(request.POST)
            if reply_form.is_valid():
                feedback.replies.create(
                    author=request.user,
                    body=reply_form.cleaned_data['body'],
                    is_staff_reply=False,
                )
                if feedback.status != Feedback.STATUS_IN_REVIEW:
                    feedback.status = Feedback.STATUS_IN_REVIEW
                    feedback.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'Đã gửi bổ sung.')
                return redirect('feedback:detail', pk=pk)
        elif action == 'respond' and can_manage:
            status_form = FeedbackStatusForm(request.POST)
            if status_form.is_valid():
                feedback.status = status_form.cleaned_data['status']
                feedback.assigned_to = request.user
                feedback.save(update_fields=['status', 'assigned_to', 'updated_at'])
                body = status_form.cleaned_data['body'].strip()
                if body:
                    feedback.replies.create(
                        author=request.user,
                        body=body,
                        is_staff_reply=True,
                    )
                messages.success(request, 'Đã cập nhật trạng thái góp ý.')
                return redirect('feedback:detail', pk=pk)
        else:
            messages.error(request, 'Không thể thực hiện thao tác này.')

    return render(request, 'feedback/detail.html', {
        'feedback': feedback,
        'reply_form': reply_form,
        'status_form': status_form,
        'can_manage': can_manage,
        'is_owner': feedback.submitter_id == request.user.id,
        **_subnav_context(request),
    })
