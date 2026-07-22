from django import forms
from django.forms import inlineformset_factory

from kho_npl.models import Material
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc, TechDocDesignFile


class ProductTechDocCreateForm(forms.Form):
    product_code = forms.CharField(
        max_length=60,
        label='Mã sản phẩm (KiotViet)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'VD: SP008073',
            'autocomplete': 'off',
            'list': 'sx-product-code-list',
        }),
    )
    notes = forms.CharField(
        required=False,
        label='Ghi chú',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )


class ProductTechDocDescriptionForm(forms.ModelForm):
    class Meta:
        model = ProductTechDoc
        fields = ('description', 'notes', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Mô tả kỹ thuật, yêu cầu sản xuất, lưu ý…',
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'description': 'Mô tả chi tiết',
            'notes': 'Ghi chú ngắn',
            'is_active': 'Đang dùng',
        }


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        default_attrs = {'class': 'form-control', 'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def value_from_datadict(self, data, files, name):
        return files.getlist(name) if files else []


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data if item]
        return single_clean(data, initial)


class TechDocDesignUploadForm(forms.Form):
    files = MultipleFileField(
        label='Tệp tài liệu',
        required=True,
        widget=MultipleFileInput(attrs={
            'class': 'form-control form-control-sm design-upload-control',
        }),
    )
    title = forms.CharField(
        required=False,
        max_length=200,
        label='Tiêu đề chung',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm design-upload-control',
            'placeholder': 'Để trống = dùng tên file',
        }),
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        label='Ghi chú',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm design-upload-control',
        }),
    )

    def save(self, tech_doc, *, user=None):
        title = (self.cleaned_data.get('title') or '').strip()
        notes = (self.cleaned_data.get('notes') or '').strip()
        files = self.cleaned_data.get('files') or []
        if not isinstance(files, (list, tuple)):
            files = [files] if files else []
        created = []
        for f in files:
            created.append(
                TechDocDesignFile.objects.create(
                    tech_doc=tech_doc,
                    file=f,
                    title=title if len(files) == 1 else '',
                    notes=notes,
                    uploaded_by=user if getattr(user, 'is_authenticated', False) else None,
                ),
            )
        return created


class BomVersionMetaForm(forms.ModelForm):
    class Meta:
        model = BomVersion
        fields = ('version_label', 'overhead_pct', 'notes')
        widgets = {
            'version_label': forms.TextInput(attrs={'class': 'form-control'}),
            'overhead_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BomLineForm(forms.ModelForm):
    class Meta:
        model = BomLine
        fields = ('material', 'qty', 'notes', 'sort_order')
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select form-select-sm jp-npl-material-select', 'data-placeholder': '— Gõ mã hoặc tên NPL —'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True).select_related(
            'unit', 'category',
        ).order_by('code')
        self.fields['material'].empty_label = '— Chọn NPL —'


class ProcessStepForm(forms.ModelForm):
    class Meta:
        model = ProcessStep
        fields = ('sequence', 'process_name', 'norm_per_hour', 'cost_per_hour', 'notes')
        widgets = {
            'sequence': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1'}),
            'process_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'norm_per_hour': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0.01'}),
            'cost_per_hour': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


BomLineFormSet = inlineformset_factory(
    BomVersion,
    BomLine,
    form=BomLineForm,
    extra=1,
    can_delete=True,
)

ProcessStepFormSet = inlineformset_factory(
    BomVersion,
    ProcessStep,
    form=ProcessStepForm,
    extra=1,
    can_delete=True,
)
