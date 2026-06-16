from django.contrib import messages
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from assessment.decorators import module_perm_required
from hrm.forms_guide import UserGuideForm
from hrm.guide_sections import (
    get_guide_admin_section_ids,
    get_guide_preview_items,
    get_visible_guide_sections,
)
from hrm.models import UserGuide
from hrm.module_permissions import MODULE_GUIDE
from hrm.permissions import can_edit_user_guide


DEFAULT_TITLE = 'Hướng dẫn sử dụng JustPlay Portal'
DEFAULT_SUBTITLE = ''


def _guide_context(request, guide: UserGuide, *, can_edit: bool) -> dict:
    visible_sections = get_visible_guide_sections(request.user)
    return {
        'guide': guide,
        'can_edit': can_edit,
        'visible_sections': visible_sections,
        'visible_section_ids': {s['id'] for s in visible_sections},
        'guide_admin_section_ids': get_guide_admin_section_ids(request.user),
        'guide_preview_items': get_guide_preview_items(request.user),
        'guide_title': guide.title or DEFAULT_TITLE,
        'guide_subtitle': '',
    }


def _default_body_html(request):
    guide = UserGuide.load()
    ctx = _guide_context(request, guide, can_edit=False)
    return render_to_string('guide/_default_body.html', ctx, request=request)


@module_perm_required(MODULE_GUIDE, 'view')
def user_guide(request):
    guide = UserGuide.load()
    can_edit = can_edit_user_guide(request.user)
    return render(request, 'guide/user_guide.html', _guide_context(request, guide, can_edit=can_edit))


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
