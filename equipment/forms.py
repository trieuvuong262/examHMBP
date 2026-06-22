from django import forms

from hrm.models import Department

from .models import Device, DeviceCategory, DeviceStatus


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'device_code',
            'name',
            'managed_department',
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
            'photo',
            'quantity',
            'unit_price',
            'hostname',
            'ip_address',
            'ultraviewer_id',
            'ultraviewer_password',
        ]
        widgets = {
            'device_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'TB-000001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'managed_department': forms.Select(attrs={'class': 'form-select'}),
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
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/jpeg,image/png,image/gif,image/webp,image/bmp',
            }),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'hostname': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
            'ultraviewer_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: 12345678',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }),
            'ultraviewer_password': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Mật khẩu cố định UltraViewer',
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, equipment_scope=None, editor_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from equipment.services.assignee_users import equipment_assignee_queryset
        from equipment.services.device_categories import category_label
        from equipment.services.device_statuses import status_choices
        from equipment.services.managed_department import default_managed_department_for_scope
        from equipment.services.scope_ui import categories_by_group_for_scope, is_it_scope

        self._equipment_scope = equipment_scope
        self._editor_user = editor_user
        from equipment.services.device_categories import categories_by_group

        grouped = (
            categories_by_group_for_scope(equipment_scope)
            if equipment_scope
            else categories_by_group()
        )
        choices: list[tuple[str, str]] = []
        for _g, _label, items in grouped:
            choices.extend(items)

        current = ''
        extra_option = None
        if self.instance and self.instance.pk and self.instance.category:
            current = self.instance.category
            in_groups = any(
                current == code for _g, _gl, items in grouped for code, _name in items
            )
            if not in_groups:
                extra_option = (current, category_label(current))

        category_label_text = Device._meta.get_field('category').verbose_name
        category_field = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_category'}),
            required=True,
            label=category_label_text,
            initial=current or None,
        )
        category_field.grouped_choices = grouped
        category_field.extra_option = extra_option
        self.fields['category'] = category_field

        status_field = forms.ChoiceField(
            choices=status_choices(),
            widget=forms.Select(attrs={'class': 'form-select'}),
            required=True,
            label=Device._meta.get_field('status').verbose_name,
            initial=(self.instance.status if self.instance and self.instance.pk else Device.STATUS_NEW),
        )
        self.fields['status'] = status_field

        self.fields['usage_department'].queryset = Department.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['usage_department'].required = False

        self.fields['managed_department'].queryset = Department.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['managed_department'].required = False
        if not self.instance.pk and equipment_scope:
            default_dept = default_managed_department_for_scope(equipment_scope)
            if default_dept:
                self.fields['managed_department'].initial = default_dept.pk

        current_assignee_id = self.instance.assigned_user_id if self.instance and self.instance.pk else None
        self.fields['assigned_user'].queryset = equipment_assignee_queryset(
            editor_user,
            current_user_id=current_assignee_id,
        )
        self.fields['assigned_user'].label_from_instance = self._user_choice_label
        self.fields['assigned_user'].required = False
        self.fields['assigned_user'].widget = forms.Select(attrs={
            'class': 'form-select d-none jp-user-picker-native',
        })
        self.fields['photo'].required = False
        self.fields['device_code'].required = False

        scope_is_it = not (equipment_scope and not is_it_scope(equipment_scope))
        if scope_is_it:
            self.fields['photo'].help_text = ''
            self.fields['device_code'].help_text = 'Để trống để hệ thống tự sinh mã (TB-000001).'
        else:
            self.fields['photo'].help_text = ''
            self.fields['device_code'].help_text = ''
            self.fields['device_code'].widget.attrs['placeholder'] = ''

        if equipment_scope and not is_it_scope(equipment_scope):
            for name in ('ultraviewer_id', 'ultraviewer_password'):
                self.fields.pop(name, None)
        else:
            self.fields['ultraviewer_id'].required = False
            self.fields['ultraviewer_password'].required = False
            self.fields['ultraviewer_id'].label = 'UltraViewer ID'
            self.fields['ultraviewer_password'].label = 'UltraViewer mật khẩu'
            self.fields['ultraviewer_id'].help_text = 'Chỉ thiết bị IT. Agent tự điền khi cài (UltraViewer).'
            self.fields['ultraviewer_password'].help_text = (
                'Mật khẩu cố định chuẩn IT — agent tự đặt khi cài. Thiết bị sản xuất không dùng.'
            )

        self._apply_scope_labels(equipment_scope)

    def _apply_scope_labels(self, equipment_scope):
        from equipment.services.scope_ui import is_it_scope

        it = is_it_scope(equipment_scope) if equipment_scope else True
        if it:
            self.fields['name'].widget.attrs.setdefault('placeholder', 'VD: Laptop Dell Latitude 5540')
            self.fields['usage_room'].label = 'Phòng / vị trí đặt máy'
            self.fields['usage_room'].widget.attrs.setdefault('placeholder', 'VD: Tầng 2 · Phòng IT')
            self.fields['model_number'].label = 'Model / hãng'
            self.fields['configuration'].label = 'Cấu hình HW / SW'
            self.fields['description'].widget.attrs.setdefault(
                'placeholder', 'Ghi chú bảo hành, phần mềm cài sẵn…',
            )
            self.fields['hostname'].widget.attrs.setdefault('placeholder', 'VD: PC-HR-01')
            self.fields['ip_address'].widget.attrs.setdefault('placeholder', 'VD: 192.168.1.10')
            if equipment_scope:
                self.fields['managed_department'].help_text = 'Thường là IT / CNTT.'
        else:
            self.fields['name'].widget.attrs.setdefault('placeholder', 'VD: Máy may Juki DDL-8700')
            from equipment.production_locations import production_usage_room_choices

            self.fields['usage_room'] = forms.ChoiceField(
                choices=production_usage_room_choices(),
                required=False,
                widget=forms.Select(attrs={'class': 'form-select'}),
                label='Vị trí lắp máy',
                initial=(self.instance.usage_room if self.instance and self.instance.pk else ''),
            )
            self.fields['model_number'].label = 'Model máy'
            self.fields['configuration'].label = 'Thông số kỹ thuật'
            self.fields['description'].widget.attrs.setdefault(
                'placeholder', 'Công suất, phụ tùng chính, lịch bảo dưỡng…',
            )
            self.fields['quantity'].help_text = ''
            self.fields['unit_price'].help_text = ''
            self.fields['managed_department'].help_text = ''

    @staticmethod
    def _user_choice_label(user):
        profile = getattr(user, 'profile', None)
        if profile and profile.full_name:
            return profile.full_name
        return user.get_full_name() or user.username

    def clean_category(self):
        from equipment.services.device_categories import normalize_category_value, valid_codes

        value = (self.cleaned_data.get('category') or '').strip()
        if not value:
            raise forms.ValidationError('Vui lòng chọn loại thiết bị.')
        normalized = normalize_category_value(value) or value
        choice_codes = {code for code, _label in self.fields['category'].choices}
        if normalized in choice_codes or normalized in valid_codes():
            return normalized
        if self.instance.pk and self.instance.category == normalized:
            return normalized
        raise forms.ValidationError('Loại thiết bị không hợp lệ.')

    def clean_status(self):
        from equipment.services.device_statuses import normalize_status_value, valid_status_codes

        value = (self.cleaned_data.get('status') or '').strip()
        if not value:
            raise forms.ValidationError('Vui lòng chọn trạng thái.')
        normalized = normalize_status_value(value) or value
        if normalized in valid_status_codes():
            return normalized
        if self.instance.pk and self.instance.status == normalized:
            return normalized
        raise forms.ValidationError('Trạng thái không hợp lệ.')

    def clean_photo(self):
        from tasks.attachment_utils import validate_image_file

        photo = self.cleaned_data.get('photo')
        if photo is False:
            return photo
        if photo:
            validate_image_file(photo)
        return photo

    def clean_device_code(self):
        from equipment.services.device_code import normalize_device_code

        value = normalize_device_code(self.cleaned_data.get('device_code'))
        if not value:
            return ''
        qs = Device.objects.filter(device_code__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Mã thiết bị đã tồn tại.')
        return value


class DeviceCategoryForm(forms.ModelForm):
    class Meta:
        model = DeviceCategory
        fields = ['code', 'name', 'group', 'import_profile', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: SEW_OVERLOCK'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'import_profile': forms.Select(attrs={'class': 'form-select'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from equipment.categories import CATEGORY_GROUP_LABELS

        self.fields['group'].choices = [(k, v) for k, v in CATEGORY_GROUP_LABELS.items()]
        if self.instance and self.instance.pk:
            self.fields['code'].disabled = True
        self.fields['code'].help_text = 'Mã duy nhất, không dấu — không đổi sau khi tạo.'

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper().replace(' ', '_')
        if not code:
            raise forms.ValidationError('Vui lòng nhập mã loại.')
        if self.instance.pk:
            return self.instance.code
        if DeviceCategory.objects.filter(code=code).exists():
            raise forms.ValidationError('Mã loại đã tồn tại.')
        return code


class DeviceStatusForm(forms.ModelForm):
    class Meta:
        model = DeviceStatus
        fields = ['code', 'name', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: active'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['code'].disabled = True
        self.fields['code'].help_text = 'Mã duy nhất — không đổi sau khi tạo.'

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().lower().replace(' ', '_')
        if not code:
            raise forms.ValidationError('Vui lòng nhập mã trạng thái.')
        if self.instance.pk:
            return self.instance.code
        if DeviceStatus.objects.filter(code=code).exists():
            raise forms.ValidationError('Mã trạng thái đã tồn tại.')
        return code


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
        label='Đang chặn công việc',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, repair_equipment_scope=None, **kwargs):
        from equipment.scope import SCOPE_PRODUCTION, normalize_repair_equipment_scope
        from service_requests.models import (
            ServiceRequest,
            incident_category_choices_for_repair_scope,
            valid_incident_category_codes_for_repair_scope,
        )

        super().__init__(*args, **kwargs)
        scope = normalize_repair_equipment_scope(repair_equipment_scope)
        is_production = scope == SCOPE_PRODUCTION
        self.repair_equipment_scope = scope
        self.fields['incident_category'].choices = incident_category_choices_for_repair_scope(scope)
        self._valid_incident_codes = valid_incident_category_codes_for_repair_scope(scope)
        self.fields['priority'].choices = [
            (c, 'Khẩn — chặn sản xuất' if is_production and c == 'urgent' else (
                'Khẩn — chặn công việc' if not is_production and c == 'urgent' else label
            ))
            for c, label in ServiceRequest.PRIORITY_CHOICES
        ]
        self.fields['blocks_work'].label = (
            'Đang chặn sản xuất / chuyền' if is_production else 'Đang chặn công việc'
        )

    def clean_incident_category(self):
        value = self.cleaned_data.get('incident_category')
        if value and value not in self._valid_incident_codes:
            raise forms.ValidationError('Loại sự cố không hợp lệ cho thiết bị này.')
        return value
