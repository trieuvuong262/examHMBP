from django.contrib import messages
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from assessment.decorators import module_perm_required
from hrm.forms_guide import UserGuideForm
from hrm.models import UserGuide
from hrm.module_permissions import MODULE_GUIDE
from hrm.permissions import can_edit_user_guide


DEFAULT_TITLE = 'Hướng dẫn sử dụng JustPlay Portal'
DEFAULT_SUBTITLE = (
    'Hướng dẫn từng bước — dành cho người chưa từng dùng hệ thống. '
    'Đọc theo thứ tự từ mục 1, hoặc nhảy thẳng tới chức năng bạn cần ở mục lục bên trái.'
)


def _default_body_html(request):
    return render_to_string('guide/_default_body.html', request=request)


@module_perm_required(MODULE_GUIDE, 'view')
def user_guide(request):
    guide = UserGuide.load()
    can_edit = can_edit_user_guide(request.user)

    if guide.has_content:
        return render(request, 'guide/view.html', {
            'guide': guide,
            'can_edit': can_edit,
        })

    return render(request, 'guide/user_guide.html', {
        'can_edit': can_edit,
    })


@module_perm_required(MODULE_GUIDE, 'update')
def user_guide_edit(request):
    guide = UserGuide.load()

    if request.method == 'POST':
        form = UserGuideForm(request.POST, instance=guide)
        if form.is_valid():
            guide = form.save(commit=False)
            guide.updated_by = request.user
            guide.save()
            messages.success(request, 'Đã lưu hướng dẫn sử dụng.')
            return redirect('user_guide')
    else:
        initial = {}
        if not guide.has_content:
            initial = {
                'title': DEFAULT_TITLE,
                'subtitle': DEFAULT_SUBTITLE,
                'body': _default_body_html(request),
            }
        form = UserGuideForm(instance=guide, initial=initial)

    return render(request, 'guide/edit.html', {
        'form': form,
        'guide': guide,
        'is_new': not guide.has_content,
    })
