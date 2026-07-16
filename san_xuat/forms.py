from django import forms
from django.forms import inlineformset_factory

from kho_npl.models import Material
from san_xuat.models import BomLine, BomVersion, ProcessStep


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


class BomVersionMetaForm(forms.ModelForm):
    class Meta:
        model = BomVersion
        fields = ('version_label', 'overhead_pct', 'notes')
        widgets = {
            'version_label': forms.TextInput(attrs={'class': 'form-control'}),
            'overhead_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class BomLineForm(forms.ModelForm):
    class Meta:
        model = BomLine
        fields = ('material', 'qty', 'scrap_pct', 'size_code', 'notes', 'sort_order')
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'min': '0'}),
            'scrap_pct': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0'}),
            'size_code': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'S/M/L'}),
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
