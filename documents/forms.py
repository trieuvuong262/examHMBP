from django import forms
from django.utils.html import strip_tags

from .models import Document, DocumentCategory


class DocumentCategoryForm(forms.ModelForm):
    class Meta:
        model = DocumentCategory
        fields = ['name', 'slug', 'description', 'icon', 'sort_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: Nhân sự'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tự tạo nếu để trống'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mô tả ngắn (tuỳ chọn)'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'bi-people-fill'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            'category',
            'title',
            'slug',
            'summary',
            'content_type',
            'body',
            'pdf_file',
            'sort_order',
            'is_active',
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tiêu đề tài liệu...'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tự tạo nếu để trống'}),
            'summary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mô tả ngắn hiển thị trên cây thư mục...'}),
            'content_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_content_type'}),
            'pdf_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,application/pdf'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        content_type = cleaned.get('content_type')
        body = cleaned.get('body')
        pdf_file = cleaned.get('pdf_file')

        if content_type == Document.TYPE_TEXT and not strip_tags(body or '').strip():
            self.add_error('body', 'Vui lòng nhập nội dung văn bản.')
        elif content_type == Document.TYPE_PDF and not pdf_file and not (self.instance.pk and self.instance.pdf_file):
            self.add_error('pdf_file', 'Vui lòng tải lên file PDF.')

        return cleaned
