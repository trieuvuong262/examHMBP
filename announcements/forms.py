from django import forms
from django.utils.html import strip_tags

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            'title',
            'summary',
            'content_type',
            'body',
            'pdf_file',
            'video_file',
            'is_active',
            'is_pinned',
            'require_acknowledgment',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập tiêu đề thông báo...'}),
            'summary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mô tả ngắn hiển thị ở danh sách...'}),
            'content_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_content_type'}),
            'pdf_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,application/pdf'}),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_pinned': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_acknowledgment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        content_type = cleaned.get('content_type')
        body = cleaned.get('body')
        pdf_file = cleaned.get('pdf_file')
        video_file = cleaned.get('video_file')

        if content_type == Announcement.TYPE_TEXT and not strip_tags(body or '').strip():
            self.add_error('body', 'Vui lòng nhập nội dung văn bản.')
        elif content_type == Announcement.TYPE_PDF and not pdf_file and not (self.instance.pk and self.instance.pdf_file):
            self.add_error('pdf_file', 'Vui lòng tải lên file PDF.')
        elif content_type == Announcement.TYPE_VIDEO and not video_file and not (self.instance.pk and self.instance.video_file):
            self.add_error('video_file', 'Vui lòng tải lên file video.')

        return cleaned
