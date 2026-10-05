from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.forms import formset_factory

from .models import RecurringItemCatalog, ServiceRequest


class SubtypeSelectForm(forms.Form):
    """Chọn loại đề xuất ở đầu màn hình tạo."""

    request_subtype = forms.ChoiceField(
        choices=ServiceRequest.SUBTYPE_CHOICES,
        label='Loại đề xuất',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_request_subtype'}),
    )


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


class GeneralProposalForm(forms.Form):
    """Form cho các loại đề xuất phi mua-hàng (thanh toán, nhân sự, sửa chữa, cấp phát).

    Tất cả field riêng theo loại đều optional ở mức field; việc bắt buộc theo loại
    được xử lý trong clean() dựa trên subtype.
    """

    PAYMENT_KIND_CHOICES = [
        ('payment', 'Thanh toán'),
        ('advance', 'Tạm ứng'),
        ('reimbursement', 'Hoàn ứng'),
    ]
    HR_KIND_CHOICES = [
        ('recruit', 'Tuyển dụng'),
        ('transfer', 'Điều chuyển'),
    ]
    ACCOUNT_KIND_CHOICES = [
        ('account', 'Tài khoản hệ thống'),
        ('computer', 'Máy tính'),
        ('email', 'Email'),
        ('other', 'Khác'),
    ]
    REPAIR_INCIDENT_CHOICES = [
        ('hw', 'Phần cứng'),
        ('sw', 'Phần mềm'),
        ('network', 'Mạng / Internet'),
        ('account', 'Tài khoản / quyền truy cập'),
        ('machine', 'Máy móc / thiết bị sản xuất'),
        ('facility', 'Cơ sở vật chất'),
        ('other', 'Khác'),
    ]
    PRIORITY_CHOICES = ServiceRequest.PRIORITY_CHOICES

    title = forms.CharField(
        label='Tiêu đề',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tóm tắt ngắn gọn nội dung đề xuất'}),
    )
    description = forms.CharField(
        label='Nội dung chi tiết',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Mô tả chi tiết nhu cầu, lý do...'}),
    )

    # --- Thanh toán / tạm ứng / hoàn ứng ---
    payment_kind = forms.ChoiceField(
        choices=PAYMENT_KIND_CHOICES, required=False, label='Hình thức',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    payment_amount = forms.DecimalField(
        required=False, min_value=Decimal('0'), label='Số tiền (VNĐ)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': 'VD: 5000000'}),
    )
    payee = forms.CharField(
        required=False, label='Người/đơn vị thụ hưởng',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên người/đơn vị nhận tiền'}),
    )
    due_date = forms.DateField(
        required=False, label='Ngày cần chi',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    # --- Tuyển dụng / điều chuyển ---
    hr_kind = forms.ChoiceField(
        choices=HR_KIND_CHOICES, required=False, label='Loại yêu cầu',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    position = forms.CharField(
        required=False, label='Vị trí / chức danh',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Công nhân may, Nhân viên kho'}),
    )
    target_department = forms.CharField(
        required=False, label='Phòng ban',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phòng ban cần nhân sự'}),
    )
    headcount = forms.IntegerField(
        required=False, min_value=1, label='Số lượng',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'placeholder': 'VD: 2'}),
    )
    desired_date = forms.DateField(
        required=False, label='Ngày mong muốn',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    # --- Sửa chữa máy móc / IT / CSVC ---
    incident_category = forms.ChoiceField(
        choices=REPAIR_INCIDENT_CHOICES, required=False, label='Loại sự cố',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES, required=False, label='Mức độ ưu tiên',
        initial=ServiceRequest.PRIORITY_NORMAL,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    location_text = forms.CharField(
        required=False, label='Vị trí',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Xưởng may — Line 2'}),
    )
    equipment_label = forms.CharField(
        required=False, label='Thiết bị',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên hoặc mã thiết bị (tuỳ chọn)'}),
    )
    equipment_serial = forms.CharField(
        required=False, label='Serial',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial (tuỳ chọn)'}),
    )

    # --- Cấp phát tài khoản / máy tính / email ---
    account_kind = forms.ChoiceField(
        choices=ACCOUNT_KIND_CHOICES, required=False, label='Loại cấp phát',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    target_user = forms.CharField(
        required=False, label='Cấp cho',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên nhân viên được cấp'}),
    )

    # Khai báo field bắt buộc theo từng loại.
    REQUIRED_BY_SUBTYPE = {
        ServiceRequest.SUBTYPE_PAYMENT: ['payment_kind', 'payment_amount'],
        ServiceRequest.SUBTYPE_HR: ['hr_kind', 'position'],
        ServiceRequest.SUBTYPE_REPAIR: ['incident_category', 'priority', 'location_text'],
        ServiceRequest.SUBTYPE_ACCOUNT: ['account_kind', 'target_user'],
    }
    # Field thuộc extra_data theo từng loại.
    EXTRA_BY_SUBTYPE = {
        ServiceRequest.SUBTYPE_PAYMENT: ['payment_kind', 'payee', 'due_date'],
        ServiceRequest.SUBTYPE_HR: ['hr_kind', 'position', 'target_department', 'headcount', 'desired_date'],
        ServiceRequest.SUBTYPE_REPAIR: ['incident_category', 'priority', 'location_text', 'equipment_label', 'equipment_serial'],
        ServiceRequest.SUBTYPE_ACCOUNT: ['account_kind', 'target_user'],
    }

    def __init__(self, *args, subtype=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.subtype = subtype

    def clean(self):
        cleaned = super().clean()
        if self.subtype not in self.REQUIRED_BY_SUBTYPE:
            raise forms.ValidationError('Loại đề xuất không hợp lệ.')
        for name in self.REQUIRED_BY_SUBTYPE[self.subtype]:
            if cleaned.get(name) in (None, ''):
                self.add_error(name, 'Trường này là bắt buộc.')
        return cleaned

    def extra_data(self):
        """Gom các field riêng theo loại thành dict để lưu vào extra_data (JSON-safe)."""
        data = {}
        for name in self.EXTRA_BY_SUBTYPE.get(self.subtype, []):
            value = self.cleaned_data.get(name)
            if value in (None, ''):
                continue
            # Chuyển choice sang nhãn hiển thị để trang chi tiết đọc được ngay.
            field = self.fields[name]
            if isinstance(field, forms.ChoiceField):
                value = dict(field.choices).get(value, value)
            elif hasattr(value, 'isoformat'):
                value = value.isoformat()
            data[name] = value
        return data


class StepActionForm(forms.Form):
    note = forms.CharField(
        required=False,
        label='Ghi chú / kết quả',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class DivisionHeadApproveForm(forms.Form):
    procurement_assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Nhân viên Thu mua xử lý',
        widget=forms.Select(attrs={'class': 'form-select d-none jp-user-picker-native'}),
    )
    note = forms.CharField(
        required=False,
        label='Ghi chú duyệt',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def __init__(self, *args, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if staff_queryset is not None:
            self.fields['procurement_assignee'].queryset = staff_queryset


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


class ItRepairCreateForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = [
            'title',
            'description',
            'incident_category',
            'priority',
            'location_text',
            'equipment_label',
            'equipment_serial',
            'blocks_work',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Máy tính không vào mạng',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Mô tả triệu chứng, thời điểm phát sinh, đã thử gì...',
            }),
            'incident_category': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'location_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Xưởng may — Line 2',
            }),
            'equipment_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tên hoặc mã thiết bị (tuỳ chọn)',
            }),
            'equipment_serial': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Serial (tuỳ chọn)',
            }),
            'blocks_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'description': 'Mô tả sự cố',
            'incident_category': 'Loại sự cố',
            'priority': 'Mức độ ưu tiên',
            'location_text': 'Vị trí',
            'equipment_label': 'Thiết bị',
            'equipment_serial': 'Serial',
            'blocks_work': 'Đang chặn công việc',
        }

    def __init__(self, *args, request_type=None, repair_equipment_scope=None, **kwargs):
        from equipment.scope import SCOPE_PRODUCTION, normalize_repair_equipment_scope
        from service_requests.models import (
            incident_category_choices_for_repair_scope,
            valid_incident_category_codes_for_repair_scope,
        )

        super().__init__(*args, **kwargs)
        self.request_type = request_type
        self.repair_equipment_scope = normalize_repair_equipment_scope(repair_equipment_scope)
        is_production = self.repair_equipment_scope == SCOPE_PRODUCTION

        self.fields['incident_category'].choices = incident_category_choices_for_repair_scope(
            self.repair_equipment_scope,
        )
        self.fields['blocks_work'].label = (
            'Đang chặn sản xuất / chuyền' if is_production else 'Đang chặn công việc'
        )
        if is_production:
            self.fields['title'].widget.attrs['placeholder'] = 'VD: Máy may dừng giữa ca'
            self.fields['description'].widget.attrs['placeholder'] = (
                'Mô tả triệu chứng, thời điểm, ảnh hưởng chuyền...'
            )
            self.fields['equipment_label'].widget.attrs['placeholder'] = 'Mã hoặc tên máy (tuỳ chọn)'
            self.fields['priority'].choices = [
                (c, 'Khẩn — chặn sản xuất' if c == 'urgent' else label)
                for c, label in self.fields['priority'].choices
            ]
        else:
            self.fields['priority'].choices = [
                (c, 'Khẩn — chặn công việc' if c == 'urgent' else label)
                for c, label in self.fields['priority'].choices
            ]

        self._valid_incident_codes = valid_incident_category_codes_for_repair_scope(
            self.repair_equipment_scope,
        )
        self.fields['incident_category'].required = True
        self.fields['priority'].required = True
        self.fields['location_text'].required = True
        self.fields['equipment_label'].required = False
        self.fields['equipment_serial'].required = False

    def clean_incident_category(self):
        value = self.cleaned_data.get('incident_category')
        if value and value not in self._valid_incident_codes:
            raise forms.ValidationError('Loại sự cố không hợp lệ cho phạm vi thiết bị đã chọn.')
        return value

    def clean(self):
        cleaned = super().clean()
        if not self.request_type or not self.request_type.is_active:
            raise forms.ValidationError('Loại yêu cầu không khả dụng.')
        return cleaned


class ItRepairCompleteForm(forms.Form):
    note = forms.CharField(
        required=True,
        label='Kết quả / cách xử lý',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )
    repair_cost = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        label='Chi phí sửa (VNĐ)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
    )
    expected_return_date = forms.DateField(
        required=False,
        label='Ngày hoàn thành thực tế',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )


class RequesterConfirmForm(forms.Form):
    note = forms.CharField(
        required=False,
        label='Ghi chú xác nhận',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )


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
