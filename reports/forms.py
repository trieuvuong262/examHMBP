import json

from django import forms
from django.forms import inlineformset_factory

from reports.link_utils import normalize_links_text
from reports.office_content import (
    DEFAULT_SPREADSHEET,
    normalize_spreadsheet_json,
    office_report_has_content,
    sanitize_document_html_for_storage,
)
from reports.week_utils import monday_of

from .models import DailyWorkReport, DailyWorkReportLine, WeeklyWorkReport
from .widgets import OfficeWordEditorWidget


class DailyWorkReportForm(forms.ModelForm):
    class Meta:
        model = DailyWorkReport
        fields = ['report_date']
        widgets = {
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.shift = ''
        if commit:
            instance.save()
        return instance


class DailyWorkReportLineForm(forms.ModelForm):
    class Meta:
        model = DailyWorkReportLine
        fields = ['area', 'order_code', 'product_name', 'quantity', 'unit', 'note']
        widgets = {
            'area': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'order_code': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'PO/Style',
            }),
            'product_name': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Tên SP',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm text-end',
                'min': 0,
                'placeholder': '0',
            }),
            'unit': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'note': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Ghi chú',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['area'].required = False


class BaseDailyWorkReportLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        valid = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('area'):
                valid += 1
        if valid == 0:
            raise forms.ValidationError('Thêm ít nhất một công đoạn.')

    def save(self, commit=True):
        self.changed_objects = []
        self.deleted_objects = []
        self.new_objects = []
        if not commit:
            raise NotImplementedError('commit=False is not supported for this formset.')
        for form in self.forms:
            if not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE') and form.instance.pk:
                form.instance.delete()
                self.deleted_objects.append(form.instance)
                continue
            if not form.cleaned_data.get('area'):
                if form.instance.pk:
                    form.instance.delete()
                continue
            form.save()
        return self.instance.lines.all()


class OfficeDailyWorkReportForm(forms.ModelForm):
    spreadsheet_data = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = DailyWorkReport
        fields = ['report_date', 'document_html', 'links']
        widgets = {
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document_html': OfficeWordEditorWidget(),
            'links': forms.Textarea(attrs={
                'class': 'form-control jp-office-links-input',
                'rows': 2,
                'placeholder': 'https://...',
                'aria-label': 'Link',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial_sheet = self.instance.spreadsheet_json if self.instance.pk else None
        self.fields['spreadsheet_data'].initial = json.dumps(
            normalize_spreadsheet_json(initial_sheet),
            ensure_ascii=False,
        )
        self.fields['document_html'].required = False
        self.fields['links'].required = False
        self.fields['links'].label = ''

    def clean_spreadsheet_data(self):
        raw = self.cleaned_data.get('spreadsheet_data') or ''
        try:
            parsed = json.loads(raw) if raw else DEFAULT_SPREADSHEET
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Dữ liệu bảng Excel không hợp lệ.') from exc
        return normalize_spreadsheet_json(parsed)

    def clean_document_html(self):
        return sanitize_document_html_for_storage(self.cleaned_data.get('document_html') or '')

    def clean_links(self):
        return normalize_links_text(self.cleaned_data.get('links') or '')

    def clean(self):
        cleaned = super().clean()
        sheet = cleaned.get('spreadsheet_data') or DEFAULT_SPREADSHEET
        doc = cleaned.get('document_html') or ''
        if self.data.get('action') == 'submit':
            delete_ids = {int(pk) for pk in self.data.getlist('delete_attachments') if pk.isdigit()}
            existing = 0
            if self.instance.pk:
                existing = self.instance.attachments.exclude(pk__in=delete_ids).count()
            new_uploads = 0
            for key in ('attachments', 'bang_images', 'bang_files', 'vanban_images', 'vanban_files', 'link_images', 'link_files'):
                new_uploads += len(self.files.getlist(key))
            if not office_report_has_content(
                sheet,
                doc,
                attachment_count=existing + new_uploads,
                links_text=cleaned.get('links') or '',
            ):
                raise forms.ValidationError(
                    'Khi nộp báo cáo, điền ít nhất một link, nội dung văn bản (≥ 50 ký tự hoặc có ảnh trong văn bản), một ô trong bảng, hoặc tải file/ảnh.',
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.spreadsheet_json = self.cleaned_data.get('spreadsheet_data')
        if commit:
            instance.save()
        return instance


class WeeklyWorkReportForm(forms.ModelForm):
    class Meta:
        model = WeeklyWorkReport
        fields = ['week_start', 'links']
        widgets = {
            'week_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'links': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['week_start'].label = 'Tuần (bắt đầu thứ 2)'
        self.fields['links'].label = 'Link'
        self.fields['links'].required = False
        if self.instance.week_start:
            self.initial.setdefault('week_start', self.instance.week_start)

    def clean_week_start(self):
        value = self.cleaned_data.get('week_start')
        return monday_of(value) if value else value

    def clean_links(self):
        return normalize_links_text(self.cleaned_data.get('links') or '')


DailyWorkReportLineFormSet = inlineformset_factory(
    DailyWorkReport,
    DailyWorkReportLine,
    form=DailyWorkReportLineForm,
    formset=BaseDailyWorkReportLineFormSet,
    extra=4,
    can_delete=True,
)
