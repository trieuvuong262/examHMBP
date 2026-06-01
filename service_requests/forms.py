from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.forms import formset_factory

from .models import RecurringItemCatalog, ServiceRequest


class ServiceRequestCreateForm(forms.ModelForm):
    recurring_item = forms.ModelChoiceField(
        queryset=RecurringItemCatalog.objects.filter(is_active=True),
        required=False,
        label='Hàng mua định kỳ (tuỳ chọn)',
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='— Không chọn —',
    )

    class Meta:
        model = ServiceRequest
        fields = ['title', 'description', 'recurring_item', 'needs_advance', 'advance_amount']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Đề xuất mua vật tư sản xuất tháng 5',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Mô tả chi tiết nhu cầu, lý do...',
            }),
            'needs_advance': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'advance_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: 5000000',
                'min': 0,
            }),
        }
        labels = {
            'title': 'Tiêu đề',
            'description': 'Nội dung yêu cầu',
            'needs_advance': 'Cần tạm ứng trước khi mua',
            'advance_amount': 'Số tiền tạm ứng (VNĐ)',
        }

    def __init__(self, *args, request_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_type = request_type
        self.fields['advance_amount'].required = False

    def clean(self):
        cleaned = super().clean()
        if not self.request_type or not self.request_type.is_active:
            raise forms.ValidationError('Loại yêu cầu không khả dụng.')
        if cleaned.get('needs_advance') and not cleaned.get('advance_amount'):
            self.add_error('advance_amount', 'Vui lòng nhập số tiền tạm ứng.')
        return cleaned


class LineItemForm(forms.Form):
    description = forms.CharField(
        label='Mô tả hàng',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên / mô tả hàng hóa'}),
    )
    quantity = forms.DecimalField(
        label='Số lượng',
        min_value=Decimal('0.01'),
        initial=Decimal('1'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
    )
    unit = forms.CharField(
        label='Đơn vị',
        required=False,
        initial='cái',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'cái'}),
    )

    def clean_unit(self):
        return (self.cleaned_data.get('unit') or 'cái').strip() or 'cái'


LineItemFormSet = formset_factory(LineItemForm, extra=2, max_num=20, validate_max=True)


class StepActionForm(forms.Form):
    note = forms.CharField(
        required=False,
        label='Ghi chú / kết quả',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class RejectStepForm(forms.Form):
    reason = forms.CharField(
        required=True,
        label='Lý do từ chối',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class PurchaseCompleteForm(forms.Form):
    goods_receiver = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Người nhận hàng',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    note = forms.CharField(
        required=True,
        label='Ghi chú đặt hàng',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def __init__(self, *args, receiver_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if receiver_queryset is not None:
            self.fields['goods_receiver'].queryset = receiver_queryset


class RecurringItemCatalogForm(forms.ModelForm):
    class Meta:
        model = RecurringItemCatalog
        fields = ['name', 'description', 'unit', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Tên hàng',
            'description': 'Mô tả',
            'unit': 'Đơn vị',
            'is_active': 'Đang dùng',
        }
