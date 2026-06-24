import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .catalog import PORTAL_TOOLS
from .models import UserNote
from .services import (
    BackgroundRemovalNotReady,
    apply_image_watermark,
    compress_image,
    convert_image_format,
    convert_office_to_pdf,
    convert_pdf_to_docx,
    generate_qr_image,
    is_background_removal_ready,
    remove_image_background,
)


def _tool_context(tool_slug: str, **extra):
    tool = next((item for item in PORTAL_TOOLS if item['slug'] == tool_slug), None)
    return {
        'portal_tools': PORTAL_TOOLS,
        'current_tool': tool,
        **extra,
    }


@login_required
def pdf_to_word(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('pdf_file')
        if not uploaded:
            return render(request, 'tools/pdf_to_word.html', _tool_context(
                'pdf-word',
                error='Vui lòng chọn file PDF.',
            ))
        try:
            docx_bytes, filename = convert_pdf_to_docx(uploaded)
        except ValidationError as exc:
            return render(request, 'tools/pdf_to_word.html', _tool_context('pdf-word', error=str(exc)))
        except Exception:
            return render(request, 'tools/pdf_to_word.html', _tool_context(
                'pdf-word',
                error='Không chuyển đổi được file. PDF có thể bị khóa hoặc quét ảnh — thử OCR trước.',
            ))

        response = HttpResponse(
            docx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'tools/pdf_to_word.html', _tool_context('pdf-word'))


@login_required
def office_to_pdf(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('office_file')
        if not uploaded:
            return render(request, 'tools/office_to_pdf.html', _tool_context(
                'office-pdf',
                error='Vui lòng chọn file Word hoặc Excel.',
            ))
        try:
            pdf_bytes, filename = convert_office_to_pdf(uploaded)
        except ValidationError as exc:
            return render(request, 'tools/office_to_pdf.html', _tool_context('office-pdf', error=str(exc)))
        except Exception:
            return render(request, 'tools/office_to_pdf.html', _tool_context(
                'office-pdf',
                error='Không chuyển được sang PDF. Thử lưu file bản mới (.docx / .xlsx) rồi upload lại.',
            ))

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'tools/office_to_pdf.html', _tool_context('office-pdf'))


@login_required
def compress_image_view(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('image_file')
        if not uploaded:
            return render(request, 'tools/compress_image.html', _tool_context(
                'compress',
                error='Vui lòng chọn ảnh.',
            ))
        try:
            quality = int(request.POST.get('quality', 80))
            max_width_raw = request.POST.get('max_width', '').strip()
            max_width = int(max_width_raw) if max_width_raw else None
            image_bytes, filename, content_type = compress_image(
                uploaded,
                quality=quality,
                max_width=max_width,
            )
        except (ValidationError, ValueError) as exc:
            return render(request, 'tools/compress_image.html', _tool_context('compress', error=str(exc)))
        except Exception:
            return render(request, 'tools/compress_image.html', _tool_context(
                'compress',
                error='Không xử lý được ảnh. Vui lòng thử file khác.',
            ))

        response = HttpResponse(image_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'tools/compress_image.html', _tool_context('compress'))


@login_required
def convert_image_format_view(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('image_file')
        if not uploaded:
            return render(request, 'tools/convert_format.html', _tool_context(
                'convert-format',
                error='Vui lòng chọn ảnh.',
            ))
        try:
            target_format = request.POST.get('target_format', 'png')
            quality = int(request.POST.get('quality', 85))
            image_bytes, filename, content_type = convert_image_format(
                uploaded,
                target_format,
                quality=quality,
            )
        except (ValidationError, ValueError) as exc:
            return render(request, 'tools/convert_format.html', _tool_context('convert-format', error=str(exc)))
        except Exception:
            return render(request, 'tools/convert_format.html', _tool_context(
                'convert-format',
                error='Không đổi được định dạng. Vui lòng thử file khác.',
            ))

        response = HttpResponse(image_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'tools/convert_format.html', _tool_context('convert-format'))


@login_required
def watermark_image_view(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('image_file')
        if not uploaded:
            return render(request, 'tools/watermark_image.html', _tool_context(
                'watermark',
                error='Vui lòng chọn ảnh.',
            ))
        try:
            image_bytes, filename, content_type = apply_image_watermark(
                uploaded,
                text=request.POST.get('watermark_text', 'JustPlay'),
                position=request.POST.get('position', 'bottom-right'),
                opacity=int(request.POST.get('opacity', 35)),
                watermark_file=request.FILES.get('watermark_file'),
            )
        except (ValidationError, ValueError) as exc:
            return render(request, 'tools/watermark_image.html', _tool_context('watermark', error=str(exc)))
        except Exception:
            return render(request, 'tools/watermark_image.html', _tool_context(
                'watermark',
                error='Không đóng watermark được. Vui lòng thử file khác.',
            ))

        response = HttpResponse(image_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'tools/watermark_image.html', _tool_context('watermark'))


@login_required
def qr_generator(request):
    preview_data = ''
    preview_png = None
    error = None

    if request.method == 'POST':
        action = request.POST.get('action', 'preview')
        preview_data = (request.POST.get('qr_data') or '').strip()
        box_size = request.POST.get('box_size', 10)
        border = request.POST.get('border', 2)
        try:
            png_bytes = generate_qr_image(preview_data, box_size=box_size, border=border)
        except ValidationError as exc:
            error = str(exc)
        else:
            if action == 'download':
                response = HttpResponse(png_bytes, content_type='image/png')
                response['Content-Disposition'] = 'attachment; filename="ma-qr.png"'
                return response
            import base64
            preview_png = base64.b64encode(png_bytes).decode('ascii')

    return render(request, 'tools/qr_generator.html', _tool_context(
        'qr',
        qr_data=preview_data,
        preview_png=preview_png,
        error=error,
    ))


@login_required
@require_GET
def ocr_tool(request):
    return render(request, 'tools/ocr.html', _tool_context('ocr'))


@login_required
@require_GET
def remove_background_tool(request):
    return render(request, 'tools/remove_background.html', _tool_context('remove-bg'))


@login_required
@require_POST
def remove_background_api(request):
    uploaded = request.FILES.get('image_file')
    if not uploaded:
        return JsonResponse({'error': 'Vui lòng chọn ảnh.'}, status=400)
    try:
        png_bytes, filename = remove_image_background(uploaded)
    except BackgroundRemovalNotReady:
        return JsonResponse({
            'error': 'Server đang tải mô hình AI lần đầu. Vui lòng đợi 30–60 giây rồi bấm Xóa nền lại.',
            'retry': True,
            'warming': True,
        }, status=503)
    except ValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception:
        warming = not is_background_removal_ready()
        return JsonResponse({
            'error': (
                'Server đang tải mô hình AI lần đầu. Vui lòng đợi 30–60 giây rồi thử lại.'
                if warming else
                'Không xóa được nền. Ảnh có thể quá lớn — thử file khác hoặc thử lại.'
            ),
            'retry': warming,
            'warming': warming,
        }, status=503 if warming else 500)

    response = HttpResponse(png_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def notes_page(request):
    notes = UserNote.objects.filter(user=request.user)
    return render(request, 'tools/notes.html', _tool_context('notes', notes=notes))


def _note_payload(note: UserNote) -> dict:
    return {
        'id': note.pk,
        'title': note.title,
        'content': note.content,
        'color': note.color,
        'updated_at': note.updated_at.isoformat(),
    }


@login_required
@require_http_methods(['GET', 'POST'])
def notes_api(request):
    if request.method == 'GET':
        notes = UserNote.objects.filter(user=request.user)
        return JsonResponse({'notes': [_note_payload(note) for note in notes]})

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dữ liệu không hợp lệ.'}, status=400)

    title = (payload.get('title') or '').strip()[:120]
    content = (payload.get('content') or '').strip()[:5000]
    color = (payload.get('color') or 'yellow').strip()
    if color not in dict(UserNote.COLOR_CHOICES):
        color = 'yellow'

    note = UserNote.objects.create(
        user=request.user,
        title=title,
        content=content,
        color=color,
    )
    return JsonResponse({'note': _note_payload(note)}, status=201)


@login_required
@require_http_methods(['PATCH', 'DELETE'])
def note_detail_api(request, pk):
    note = get_object_or_404(UserNote, pk=pk, user=request.user)

    if request.method == 'DELETE':
        note.delete()
        return JsonResponse({'ok': True})

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dữ liệu không hợp lệ.'}, status=400)

    if 'title' in payload:
        note.title = (payload.get('title') or '').strip()[:120]
    if 'content' in payload:
        note.content = (payload.get('content') or '').strip()[:5000]
    if 'color' in payload:
        color = (payload.get('color') or note.color).strip()
        if color in dict(UserNote.COLOR_CHOICES):
            note.color = color
    note.save()
    return JsonResponse({'note': _note_payload(note)})


@login_required
@require_POST
def note_quick_add(request):
    """Thêm ghi chú nhanh từ form HTML (không JS)."""
    title = (request.POST.get('title') or '').strip()[:120]
    content = (request.POST.get('content') or '').strip()[:5000]
    color = (request.POST.get('color') or 'yellow').strip()
    if color not in dict(UserNote.COLOR_CHOICES):
        color = 'yellow'
    UserNote.objects.create(user=request.user, title=title, content=content, color=color)
    return redirect('tools:notes')


@login_required
def schedule_reminder_page(request):
    from utilities.forms import ScheduleReminderForm
    from utilities.models import MealPushSubscription, ScheduleReminder
    from utilities.portal_push_eligibility import user_portal_push_eligible
    from utilities.push_service import webpush_configured
    from utilities.schedule_reminder_logic import reminder_schedule_summary

    form = ScheduleReminderForm()
    if request.method == 'POST':
        form = ScheduleReminderForm(request.POST)
        if form.is_valid():
            reminder = form.save(commit=False)
            reminder.user = request.user
            reminder.save()
            messages.success(
                request,
                f'Đã tạo nhắc «{reminder.title}» — {reminder_schedule_summary(reminder)}.',
            )
            return redirect('tools:schedule_reminder')

    push_ready = webpush_configured() and user_portal_push_eligible(request.user)
    push_subscribed = (
        push_ready
        and MealPushSubscription.objects.filter(user=request.user).exists()
    )
    reminders = list(
        ScheduleReminder.objects.filter(user=request.user, is_active=True)
        .order_by('remind_time', '-created_at')[:30],
    )

    return render(request, 'tools/schedule_reminder.html', _tool_context(
        'schedule-reminder',
        form=form,
        reminders=reminders,
        push_ready=push_ready,
        push_subscribed=push_subscribed,
        push_test_schedule_url=reverse('utilities:push_test_schedule') if push_ready else '',
    ))


@login_required
@require_POST
def schedule_reminder_delete(request, pk):
    from utilities.models import ScheduleReminder

    reminder = get_object_or_404(ScheduleReminder, pk=pk, user=request.user)
    reminder.is_active = False
    reminder.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, 'Đã xóa nhắc lịch.')
    return redirect('tools:schedule_reminder')
