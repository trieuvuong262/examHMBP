from django import forms

from hrm.models import Department, Profile

from .models import Device


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'name',
            'managed_by',
            'category',
            'usage_department',
            'usage_department_text',
            'usage_room',
            'assigned_user',
            'assigned_user_text',
            'handover_date',
            'model_number',
            'serial_number',
            'configuration',
            'description',
            'contact_email',
            'status',
            'quantity',
            'unit_price',
            'hostname',
            'ip_address',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'managed_by': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'usage_department': forms.Select(attrs={'class': 'form-select'}),
            'usage_department_text': forms.TextInput(attrs={'class': 'form-control'}),
            'usage_room': forms.TextInput(attrs={'class': 'form-control'}),
            'assigned_user': forms.Select(attrs={'class': 'form-select'}),
            'assigned_user_text': forms.TextInput(attrs={'class': 'form-control'}),
            'handover_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'model_number': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'configuration': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'hostname': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usage_department'].queryset = Department.objects.order_by('name')
        self.fields['usage_department'].required = False
        self.fields['assigned_user'].queryset = Profile.objects.filter(
            is_employed=True,
        ).select_related('user').order_by('full_name')
        self.fields['assigned_user'].required = False


class ReportIssueForm(forms.Form):
    issue_description = forms.CharField(
        label='Mô tả sự cố',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )
    incident_category = forms.ChoiceField(
        label='Loại sự cố',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    priority = forms.ChoiceField(
        label='Mức độ ưu tiên',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    blocks_work = forms.BooleanField(
        label='Đang chặn công việc / sản xuất',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        from service_requests.models import ServiceRequest
        super().__init__(*args, **kwargs)
        self.fields['incident_category'].choices = ServiceRequest.INCIDENT_CATEGORY_CHOICES
        self.fields['priority'].choices = ServiceRequest.PRIORITY_CHOICES
