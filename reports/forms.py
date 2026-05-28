from django import forms
from django.forms import inlineformset_factory

from .models import DailyWorkReport, DailyWorkReportLine


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


DailyWorkReportLineFormSet = inlineformset_factory(
    DailyWorkReport,
    DailyWorkReportLine,
    form=DailyWorkReportLineForm,
    formset=BaseDailyWorkReportLineFormSet,
    extra=4,
    can_delete=True,
)
