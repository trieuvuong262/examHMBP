from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from assessment.decorators import module_perm_required
from hrm.forms_guide import UserGuideSectionForm, UserGuideTitleForm
from hrm.guide_editor import (
    all_guide_sections_for_admin,
    clear_section_override,
    get_section_edit_initial,
    normalize_section_overrides,
    save_section_override,
    section_display_title,
    section_has_override,
)
from hrm.guide_sections import (
    build_guide_toc_groups,
    get_guide_admin_section_ids,
    get_guide_preview_items,
    get_section_by_id,
    get_visible_guide_sections,
)
from hrm.models import UserGuide
from hrm.module_permissions import MODULE_GUIDE, MODULE_LABELS
from hrm.permissions import can_edit_user_guide


DEFAULT_TITLE = 'Hướng dẫn sử dụng JustPlay Portal'
DEFAULT_SUBTITLE = ''


def _guide_context(request, guide: UserGuide, *, can_edit: bool) -> dict:
    visible_sections, guide_toc_groups = build_guide_toc_groups(
        get_visible_guide_sections(request.user),
    )
    return {
        'guide': guide,
        'can_edit': can_edit,
        'visible_sections': visible_sections,
        'guide_toc_groups': guide_toc_groups,
        'visible_section_ids': {s['id'] for s in visible_sections},
        'guide_admin_section_ids': get_guide_admin_section_ids(request.user),
        'guide_preview_items': get_guide_preview_items(request.user),
        'guide_title': guide.title or DEFAULT_TITLE,
        'guide_subtitle': '',
        'section_overrides': normalize_section_overrides(guide.section_overrides),
    }


def _default_body_html(request):
    guide = UserGuide.load()
    ctx = _guide_context(request, guide, can_edit=False)
    return render_to_string('guide/_default_body.html', ctx, request=request)


def _section_module_labels(section: dict) -> list[str]:
    modules = section.get('modules')
    if not modules:
        return ['Nền tảng — mọi người']
    return [MODULE_LABELS.get(mod, mod) for mod in modules]


@module_perm_required(MODULE_GUIDE, 'view')
def user_guide(request):
    guide = UserGuide.load()
    can_edit = can_edit_user_guide(request.user)
    return render(request, 'guide/user_guide.html', _guide_context(request, guide, can_edit=can_edit))


@module_perm_required(MODULE_GUIDE, 'update')
def user_guide_edit(request):
    guide = UserGuide.load()
    overrides = normalize_section_overrides(guide.section_overrides)

    if request.method == 'POST' and request.POST.get('action') == 'save_title':
        title_form = UserGuideTitleForm(request.POST, instance=guide)
        if title_form.is_valid():
            guide = title_form.save(commit=False)
            guide.updated_by = request.user
            guide.save()
            messages.success(request, 'Đã lưu tiêu đề trang hướng dẫn.')
            return redirect('user_guide_edit')
    else:
        title_form = UserGuideTitleForm(instance=guide)

    sections = []
    for sec in all_guide_sections_for_admin():
        sections.append({
            **sec,
            'display_title': section_display_title(sec, overrides),
            'is_custom': section_has_override(sec['id'], overrides),
            'module_labels': _section_module_labels(sec),
            'icon': sec.get('icon', 'bi-journal-text'),
        })

    custom_count = sum(1 for s in sections if s['is_custom'])

    return render(request, 'guide/edit.html', {
        'guide': guide,
        'title_form': title_form,
        'sections': sections,
        'section_count': len(sections),
        'custom_count': custom_count,
    })


@module_perm_required(MODULE_GUIDE, 'update')
def user_guide_edit_section(request, section_id: str):
    section = get_section_by_id(section_id)
    if not section:
        raise Http404

    guide = UserGuide.load()
    ctx = _guide_context(request, guide, can_edit=True)
    overrides = ctx['section_overrides']

    if request.method == 'POST':
        if request.POST.get('action') == 'reset':
            clear_section_override(guide, section_id)
            guide.updated_by = request.user
            guide.save(update_fields=['updated_by', 'updated_at'])
            messages.success(request, f'Đã khôi phục mục «{section["toc"]}» về nội dung mặc định.')
            return redirect('user_guide_edit_section', section_id=section_id)

        form = UserGuideSectionForm(request.POST)
        if form.is_valid():
            save_section_override(
                guide,
                section_id,
                title=form.cleaned_data['title'],
                body=form.cleaned_data['body'],
            )
            guide.updated_by = request.user
            guide.save(update_fields=['updated_by', 'updated_at'])
            messages.success(request, f'Đã lưu mục «{form.cleaned_data["title"]}».')
            return redirect('user_guide_edit')
    else:
        initial = get_section_edit_initial(section_id, guide, request, context=ctx)
        form = UserGuideSectionForm(initial=initial)

    return render(request, 'guide/edit_section.html', {
        'form': form,
        'guide': guide,
        'section': section,
        'section_id': section_id,
        'is_custom': section_has_override(section_id, overrides),
        'icon': section.get('icon', 'bi-journal-text'),
        'module_labels': _section_module_labels(section),
    })
