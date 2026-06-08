import json

from django import forms
from django.forms import inlineformset_factory

from reports.office_content import (
    DEFAULT_SPREADSHEET,
    normalize_spreadsheet_json,
    office_report_has_content,
)

from .models import DailyWorkReport, DailyWorkReportLine
from .widgets import CKEditor5Widget


class DailyWorkReportForm(forms.ModelForm):
    class Meta:
        model = DailyWorkReport
        fields = ['report_date', 'shift']
        widgets = {
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'shift': forms.Select(attrs={'class': 'form-select form-select-lg'}),
        }


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
        fields = ['report_date', 'document_html']
        widgets = {
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document_html': CKEditor5Widget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial_sheet = self.instance.spreadsheet_json if self.instance.pk else None
        self.fields['spreadsheet_data'].initial = json.dumps(
            normalize_spreadsheet_json(initial_sheet),
            ensure_ascii=False,
        )
        self.fields['document_html'].required = False

    def clean_spreadsheet_data(self):
        raw = self.cleaned_data.get('spreadsheet_data') or ''
        try:
            parsed = json.loads(raw) if raw else DEFAULT_SPREADSHEET
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Dữ liệu bảng Excel không hợp lệ.') from exc
        return normalize_spreadsheet_json(parsed)

    def clean(self):
        cleaned = super().clean()
        sheet = cleaned.get('spreadsheet_data') or DEFAULT_SPREADSHEET
        doc = cleaned.get('document_html') or ''
        if self.data.get('action') == 'submit':
            if not office_report_has_content(sheet, doc):
                raise forms.ValidationError(
                    'Khi nộp báo cáo, điền ít nhất một ô trong tab Bảng hoặc ≥ 50 ký tự trong tab Văn bản.',
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.spreadsheet_json = self.cleaned_data.get('spreadsheet_data')
        if commit:
            instance.save()
        return instance


DailyWorkReportLineFormSet = inlineformset_factory(
    DailyWorkReport,
    DailyWorkReportLine,
    form=DailyWorkReportLineForm,
    formset=BaseDailyWorkReportLineFormSet,
    extra=4,
    can_delete=True,
)
