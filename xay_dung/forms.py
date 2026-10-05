import os

from django import forms
from django.conf import settings

from nas_storage.upload_guard import scan_for_malware

from .models import Model3D

ALLOWED_EXTS = ('.html', '.htm')


def _max_bytes() -> int:
    return int(getattr(settings, 'UPLOAD_MAX_BYTES_DESIGN', 100 * 1024 * 1024))


class Model3DForm(forms.ModelForm):
    class Meta:
        model = Model3D
        fields = ('title', 'description', 'html_file')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Nhà xưởng D5'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Ghi chú (không bắt buộc)'}),
            'html_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.html,.htm,text/html'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'description': 'Mô tả',
            'html_file': 'File HTML mô hình 3D',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sửa: không bắt buộc chọn lại file.
        if self.instance and self.instance.pk:
            self.fields['html_file'].required = False
            self.fields['html_file'].widget = forms.FileInput(
                attrs={'class': 'form-control', 'accept': '.html,.htm,text/html'},
            )

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if not title:
            raise forms.ValidationError('Vui lòng nhập tiêu đề.')
        return title

    def clean_html_file(self):
        f = self.cleaned_data.get('html_file')
        # Không upload file mới (đang sửa) → giữ file cũ.
        if not f or not hasattr(f, 'content_type'):
            return f

        name = os.path.basename(f.name or '')
        if os.path.splitext(name)[1].lower() not in ALLOWED_EXTS:
            raise forms.ValidationError('Chỉ nhận file .html hoặc .htm.')

        limit = _max_bytes()
        if f.size > limit:
            raise forms.ValidationError(f'File vượt giới hạn {limit // (1024 * 1024)} MB.')

        head = f.read(4096)
        f.seek(0)
        if b'\x00' in head:
            raise forms.ValidationError('File không phải HTML dạng văn bản.')
        if b'<' not in head:
            raise forms.ValidationError('Nội dung file không giống HTML.')

        scan_for_malware(f, name)
        return f

    def save(self, commit=True):
        obj = super().save(commit=False)
        f = self.cleaned_data.get('html_file')
        if f and hasattr(f, 'content_type'):
            obj.original_name = os.path.basename(f.name or '')[:255]
            obj.file_size = f.size or 0
        if commit:
            obj.save()
        return obj
