from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Profile, Department, Division, DepartmentMenuPermission, PermissionGroup
from hrm.choices import GENDER_FORM_CHOICES
from hrm.permissions import ROLE_EMPLOYEE
from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_CHOICES, MODULE_LABELS
from hrm.role_permissions import normalize_module_permissions
from hrm.group_permissions import PERM_ACTIONS, PERM_ACTION_LABELS, normalize_group_permissions
from hrm.user_search import user_display_label

INPUT = {'class': 'form-control'}
SELECT = {'class': 'form-select'}
DATE = {'class': 'form-control', 'type': 'date'}


class CustomUserForm(forms.Form):
    # Tài khoản
    username = forms.CharField(
        label='Account',
        widget=forms.TextInput(attrs={**INPUT, 'placeholder': 'Annt'}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={**INPUT, 'placeholder': '••••••••'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={**INPUT, 'placeholder': 'annt@justplay.vn'}),
    )

    # Thông tin nhân sự
    employee_code = forms.CharField(
        label='Mã NS',
        required=False,
        widget=forms.TextInput(attrs={**INPUT, 'placeholder': 'NV001'}),
    )
    full_name = forms.CharField(
        label='Họ và tên',
        widget=forms.TextInput(attrs={**INPUT, 'placeholder': 'Nguyễn Văn An'}),
    )
    department = forms.ModelChoiceField(
        label='Phòng ban',
        queryset=Department.objects.filter(is_active=True),
        required=False,
        empty_label='-- Chọn phòng ban --',
        widget=forms.Select(attrs=SELECT),
    )
    division = forms.ModelChoiceField(
        label='Bộ phận',
        queryset=Division.objects.filter(is_active=True),
        required=False,
        empty_label='-- Chọn bộ phận --',
        widget=forms.Select(attrs=SELECT),
    )
    job_position = forms.CharField(
        label='Vị trí',
        required=False,
        widget=forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: Công nhân may'}),
    )
    job_title = forms.CharField(
        label='Chức vụ',
        required=False,
        widget=forms.TextInput(attrs={**INPUT, 'placeholder': 'Nhân viên'}),
    )
    join_date = forms.DateField(
        label='Ngày vào',
        required=False,
        widget=forms.DateInput(attrs=DATE, format='%Y-%m-%d'),
    )
    date_of_birth = forms.DateField(
        label='Ngày sinh',
        required=False,
        widget=forms.DateInput(attrs=DATE, format='%Y-%m-%d'),
    )
    gender = forms.ChoiceField(
        label='Giới tính',
        choices=GENDER_FORM_CHOICES,
        required=False,
        widget=forms.Select(attrs=SELECT),
    )

    role = forms.ChoiceField(
        choices=Profile.ROLE_CHOICES,
        widget=forms.Select(attrs=SELECT),
        initial=ROLE_EMPLOYEE,
        label='Vai trò hệ thống',
    )
    permission_group = forms.ModelChoiceField(
        queryset=PermissionGroup.objects.all().order_by('name'),
        required=False,
        empty_label='— Mặc định theo vai trò —',
        widget=forms.Select(attrs=SELECT),
        label='Nhóm quyền',
    )
    subordinates = forms.ModelMultipleChoiceField(
        queryset=User.objects.select_related('profile').order_by('profile__full_name', 'username'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multiple'}),
        label='Nhân viên cấp dưới trực tiếp',
        help_text='Người được chọn sẽ nộp báo cáo cho quản lý này; quản lý xem và duyệt báo cáo của họ.',
    )

    def __init__(self, *args, **kwargs):
        self.user_id = kwargs.pop('user_id', None)
        super().__init__(*args, **kwargs)
        self.fields['join_date'].input_formats = ['%Y-%m-%d']
        self.fields['date_of_birth'].input_formats = ['%Y-%m-%d']

        if self.user_id:
            self.fields['subordinates'].queryset = (
                User.objects.select_related('profile')
                .exclude(id=self.user_id)
                .order_by('profile__full_name', 'username')
            )

        dept_qs = Department.objects.filter(is_active=True)
        if self.initial.get('department'):
            current = self.initial['department']
            current_pk = current.pk if isinstance(current, Department) else current
            dept_qs = Department.objects.filter(Q(is_active=True) | Q(pk=current_pk))
        self.fields['department'].queryset = dept_qs.order_by('sort_order', 'name')

        div_qs = Division.objects.filter(is_active=True)
        if self.initial.get('division'):
            current = self.initial['division']
            current_pk = current.pk if isinstance(current, Division) else current
            div_qs = Division.objects.filter(Q(is_active=True) | Q(pk=current_pk))
        self.fields['division'].queryset = div_qs.order_by('sort_order', 'name')

        self.fields['subordinates'].label_from_instance = user_display_label

    def clean_username(self):
        username = self.cleaned_data.get('username')
        qs = User.objects.filter(username=username)
        if self.user_id:
            qs = qs.exclude(id=self.user_id)
        if qs.exists():
            raise forms.ValidationError('Tên đăng nhập này đã tồn tại!')
        return username

    def clean_employee_code(self):
        code = (self.cleaned_data.get('employee_code') or '').strip()
        if not code:
            return ''
        qs = Profile.objects.filter(employee_code=code)
        if self.user_id:
            qs = qs.exclude(user_id=self.user_id)
        if qs.exists():
            raise forms.ValidationError('Mã NS này đã được sử dụng!')
        return code


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'sort_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: SẢN XUẤT'}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Tên phòng ban',
            'sort_order': 'Thứ tự hiển thị',
            'is_active': 'Đang sử dụng',
        }

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Tên phòng ban không được để trống.')
        qs = Department.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Phòng ban này đã tồn tại.')
        return name


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ['name', 'sort_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: QC'}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Tên bộ phận',
            'sort_order': 'Thứ tự hiển thị',
            'is_active': 'Đang sử dụng',
        }

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Tên bộ phận không được để trống.')
        qs = Division.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Bộ phận này đã tồn tại.')
        return name


class DepartmentMenuPermissionForm(forms.Form):
    modules = forms.MultipleChoiceField(
        choices=MODULE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Chức năng được phép truy cập',
    )


class RolePermissionForm(forms.Form):
    """Ma trận quyền Xem / Cập nhật theo module cho một vai trò."""

    def __init__(self, *args, **kwargs):
        initial_perms = kwargs.pop('initial_permissions', None)
        super().__init__(*args, **kwargs)
        normalized = normalize_module_permissions(initial_perms)
        for module_key, label in MODULE_CHOICES:
            view_field = f'view_{module_key}'
            edit_field = f'edit_{module_key}'
            mod = normalized.get(module_key, {'view': False, 'edit': False})
            self.fields[view_field] = forms.BooleanField(
                required=False,
                initial=mod['view'],
                label=f'Xem — {label}',
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            )
            self.fields[edit_field] = forms.BooleanField(
                required=False,
                initial=mod['edit'],
                label=f'Cập nhật — {label}',
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            )

    def module_rows(self):
        rows = []
        for module_key, label in MODULE_CHOICES:
            rows.append({
                'key': module_key,
                'label': label,
                'view_field': self[f'view_{module_key}'],
                'edit_field': self[f'edit_{module_key}'],
            })
        return rows

    def cleaned_permissions(self) -> dict:
        result = {}
        for module_key, _label in MODULE_CHOICES:
            view = self.cleaned_data.get(f'view_{module_key}', False)
            edit = self.cleaned_data.get(f'edit_{module_key}', False)
            if edit:
                view = True
            result[module_key] = {'view': view, 'edit': edit}
        return normalize_module_permissions(result)


class PermissionGroupMetaForm(forms.ModelForm):
    class Meta:
        model = PermissionGroup
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: Nhân viên HCNS'}),
            'description': forms.Textarea(attrs={'class': 'form-control jp-perm-group-desc-input', 'rows': 1}),
        }
        labels = {
            'name': 'Tên nhóm quyền',
            'description': 'Mô tả',
        }


PERM_GROUP_MODULE_ICONS = {
    'announcements': 'bi-megaphone',
    'recruitment': 'bi-person-plus',
    'training': 'bi-mortarboard',
    'assessment': 'bi-patch-check',
    'hrm': 'bi-people',
    'kpi': 'bi-graph-up-arrow',
    'reports': 'bi-journal-text',
    'guide': 'bi-book',
    'documents': 'bi-folder2',
    'permissions': 'bi-shield-lock',
    'audit': 'bi-clock-history',
    'tasks': 'bi-kanban',
    'service_requests': 'bi-headset',
    'nas_storage': 'bi-hdd-network',
}


class PermissionGroupPermissionForm(forms.Form):
    """Ma trận 5 quyền / module cho một nhóm."""

    def __init__(self, *args, **kwargs):
        initial_perms = kwargs.pop('initial_permissions', None)
        super().__init__(*args, **kwargs)
        normalized = normalize_group_permissions(initial_perms)
        for module_key, label in MODULE_CHOICES:
            mod = normalized.get(module_key, {})
            for action in PERM_ACTIONS:
                field_name = f'{action}_{module_key}'
                self.fields[field_name] = forms.BooleanField(
                    required=False,
                    initial=mod.get(action, False),
                    label=f'{PERM_ACTION_LABELS[action]} — {label}',
                    widget=forms.CheckboxInput(attrs={'class': 'jp-perm-switch-input'}),
                )

    def module_rows(self):
        rows = []
        for module_key, label in MODULE_CHOICES:
            rows.append({
                'key': module_key,
                'label': label,
                'icon': PERM_GROUP_MODULE_ICONS.get(module_key, 'bi-grid'),
                'fields': {
                    action: self[f'{action}_{module_key}']
                    for action in PERM_ACTIONS
                },
            })
        return rows

    def cleaned_permissions(self) -> dict:
        result = {}
        for module_key, _label in MODULE_CHOICES:
            entry = {
                action: self.cleaned_data.get(f'{action}_{module_key}', False)
                for action in PERM_ACTIONS
            }
            if any(entry[a] for a in ('create', 'update', 'delete', 'export')):
                entry['view'] = True
            result[module_key] = entry
        return normalize_group_permissions(result)

