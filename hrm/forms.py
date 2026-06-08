from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from .models import (
    Profile,
    Department,
    DepartmentPosition,
    Division,
    DivisionPosition,
    DepartmentMenuPermission,
    PermissionGroup,
)
from hrm.org_structure import ORG_DEPARTMENT_HEAD_LABEL
from .sort_order import next_sort_order, resolve_sort_order_on_create


def _coerce_pk(value):
    if value is None or value == '':
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    return int(s) if s.isdigit() else None
from hrm.org_structure import divisions_for_department
from hrm.choices import GENDER_FORM_CHOICES
from hrm.permissions import ROLE_EMPLOYEE
from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_CHOICES, MODULE_LABELS
from hrm.role_permissions import normalize_module_permissions
from hrm.group_permissions import PERM_ACTIONS, PERM_ACTION_LABELS, normalize_group_permissions
from hrm.user_search import (
    subordinate_candidate_queryset,
    subordinate_scope_hint,
    user_display_label,
)

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
        required=False,
        widget=forms.EmailInput(attrs={**INPUT, 'placeholder': 'annt@justplay.vn (tuỳ chọn)'}),
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
        widget=forms.TextInput(attrs={
            **INPUT,
            'placeholder': 'VD: Công nhân may, Nhân viên QC…',
        }),
        help_text='Nhập tự do — cấp thấp nhất trong sơ đồ tổ chức.',
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

    IS_EMPLOYED_CHOICES = (
        ('1', 'Đang làm'),
        ('0', 'Nghỉ làm'),
    )
    is_employed = forms.ChoiceField(
        choices=IS_EMPLOYED_CHOICES,
        initial='1',
        label='Trạng thái làm việc',
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
        widget=forms.CheckboxSelectMultiple(),
        label='Nhân viên cấp dưới trực tiếp',
        help_text='Người được chọn sẽ nộp báo cáo cho quản lý này; quản lý xem và duyệt báo cáo của họ.',
    )

    def __init__(self, *args, **kwargs):
        self.user_id = kwargs.pop('user_id', None)
        super().__init__(*args, **kwargs)
        self.fields['join_date'].input_formats = ['%Y-%m-%d']
        self.fields['date_of_birth'].input_formats = ['%Y-%m-%d']

        manager_role = (self.data.get('role') or self.initial.get('role') or '').strip()
        manager_dept = self.data.get('department') or self.initial.get('department')
        manager_div = self.data.get('division') or self.initial.get('division')
        if isinstance(manager_dept, Department):
            manager_dept = manager_dept.pk
        if isinstance(manager_div, Division):
            manager_div = manager_div.pk

        extra_sub_ids: list[int] = []
        if self.data:
            extra_sub_ids = [int(x) for x in self.data.getlist('subordinates') if str(x).isdigit()]
        elif self.initial.get('subordinates'):
            raw_subs = self.initial['subordinates']
            if hasattr(raw_subs, 'values_list'):
                extra_sub_ids = list(raw_subs.values_list('pk', flat=True))
            else:
                extra_sub_ids = [u.pk for u in raw_subs]

        sub_qs = subordinate_candidate_queryset(
            exclude_user_id=self.user_id,
            manager_role=manager_role,
            department_id=manager_dept,
            division_id=manager_div,
            extra_user_ids=extra_sub_ids,
        )
        self.fields['subordinates'].queryset = sub_qs
        self.subordinate_scope_hint = subordinate_scope_hint(
            manager_role=manager_role,
            department_id=manager_dept,
            division_id=manager_div,
        )
        self.subordinate_candidate_count = sub_qs.count()

        dept_qs = Department.objects.filter(is_active=True)
        if self.initial.get('department'):
            current = self.initial['department']
            current_pk = current.pk if isinstance(current, Department) else current
            dept_qs = Department.objects.filter(Q(is_active=True) | Q(pk=current_pk))
        self.fields['department'].queryset = dept_qs.order_by('sort_order', 'name')

        div_qs = divisions_for_department(None)
        div_current = self.initial.get('division') or self.data.get('division')
        if div_current:
            current_pk = div_current.pk if isinstance(div_current, Division) else div_current
            try:
                current_pk = int(current_pk)
            except (TypeError, ValueError):
                current_pk = None
            if current_pk:
                div_qs = Division.objects.filter(
                    Q(pk__in=div_qs.values('pk')) | Q(pk=current_pk),
                ).distinct()
        self.fields['division'].queryset = div_qs.select_related('department').order_by(
            'department__sort_order', 'department__name', 'sort_order', 'name',
        )

        def _division_label(obj):
            label = obj.name
            if not obj.is_active:
                label = f'{label} (ngưng)'
            if obj.department_id:
                return label
            return f'{label} (chưa gán phòng ban)'

        self.fields['division'].label_from_instance = _division_label
        self.fields['subordinates'].label_from_instance = user_display_label

        if not self.user_id:
            self.fields['full_name'].widget.attrs.update({
                'autocomplete': 'off',
                'data-lpignore': 'true',
                'data-1p-ignore': 'true',
            })
            self.fields['username'].widget.attrs.update({
                'autocomplete': 'off',
                'autocapitalize': 'off',
                'autocorrect': 'off',
                'spellcheck': 'false',
                'data-lpignore': 'true',
                'data-1p-ignore': 'true',
                'data-form-type': 'other',
            })
            self.fields['password'].widget.attrs['autocomplete'] = 'new-password'
            self.fields['email'].widget.attrs.update({
                'autocomplete': 'off',
                'data-lpignore': 'true',
            })

    def clean_username(self):
        username = self.cleaned_data.get('username')
        qs = User.objects.filter(username=username)
        if self.user_id:
            qs = qs.exclude(id=self.user_id)
        if qs.exists():
            raise forms.ValidationError('Tên đăng nhập này đã tồn tại!')
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        return email

    def clean_full_name(self):
        name = (self.cleaned_data.get('full_name') or '').strip()
        if not name:
            raise forms.ValidationError('Họ và tên không được để trống.')
        return name

    def clean_password(self):
        password = self.cleaned_data.get('password') or ''
        if not self.user_id and not str(password).strip():
            raise forms.ValidationError('Mật khẩu bắt buộc khi thêm nhân viên mới.')
        return password

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

    def clean_is_employed(self):
        return (self.cleaned_data.get('is_employed') or '1') == '1'

    def clean(self):
        cleaned = super().clean()
        dept = cleaned.get('department')
        div = cleaned.get('division')
        if div and dept:
            allowed = divisions_for_department(dept.pk if dept else None).filter(pk=div.pk).exists()
            if not allowed:
                self.add_error(
                    'division',
                    'Bộ phận này không thuộc phòng ban đã chọn — chọn lại hoặc cập nhật tại Cơ cấu tổ chức.',
                )
        return cleaned


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'sort_order', 'report_profile', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: SẢN XUẤT'}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'report_profile': forms.Select(attrs={**INPUT}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Tên phòng ban',
            'sort_order': 'Thứ tự hiển thị',
            'report_profile': 'Mẫu báo cáo',
            'is_active': 'Đang sử dụng',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['sort_order'].initial = next_sort_order(Department.objects.all())
            self.fields['sort_order'].help_text = 'Tự động đánh số tiếp theo khi thêm mới (có thể sửa).'

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.pk:
            obj.sort_order = resolve_sort_order_on_create(
                posted=self.cleaned_data['sort_order'],
                field_initial=self.fields['sort_order'].initial,
                scope_changed=False,
                queryset=Department.objects.all(),
            )
        if commit:
            obj.save()
        return obj

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
        fields = ['department', 'name', 'sort_order', 'is_active']
        widgets = {
            'department': forms.Select(attrs=SELECT),
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'VD: QC'}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'department': 'Phòng ban',
            'name': 'Tên bộ phận',
            'sort_order': 'Thứ tự hiển thị',
            'is_active': 'Đang sử dụng',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True).order_by(
            'sort_order', 'name',
        )
        self.fields['department'].empty_label = '-- Chọn phòng ban --'
        self.fields['department'].required = True
        if not self.instance.pk:
            dept_id = self._initial_department_id()
            if dept_id:
                qs = Division.objects.filter(department_id=dept_id)
                self.fields['sort_order'].initial = next_sort_order(qs)
            self.fields['sort_order'].help_text = 'Tự động đánh số trong phòng ban đã chọn (có thể sửa).'

    def _initial_department_id(self):
        return _coerce_pk(self.initial.get('department') if self.initial else None) or _coerce_pk(
            self.data.get('department') if self.data else None,
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.pk and obj.department_id:
            init_dept = _coerce_pk(self.initial.get('department') if self.initial else None)
            scope_changed = init_dept is not None and obj.department_id != init_dept
            obj.sort_order = resolve_sort_order_on_create(
                posted=self.cleaned_data['sort_order'],
                field_initial=self.fields['sort_order'].initial,
                scope_changed=scope_changed,
                queryset=Division.objects.filter(department_id=obj.department_id),
            )
        if commit:
            obj.save()
        return obj

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Tên bộ phận không được để trống.')
        dept = self.cleaned_data.get('department')
        qs = Division.objects.filter(name__iexact=name, department=dept)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Bộ phận này đã tồn tại trong phòng ban đã chọn.')
        return name

    def clean_department(self):
        dept = self.cleaned_data.get('department')
        if not dept:
            raise forms.ValidationError('Phòng ban không được để trống.')
        return dept


class DepartmentPositionForm(forms.ModelForm):
    class Meta:
        model = DepartmentPosition
        fields = ['department', 'name', 'sort_order', 'is_active']
        widgets = {
            'department': forms.Select(attrs=SELECT),
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': ORG_DEPARTMENT_HEAD_LABEL}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'department': 'Phòng ban',
            'name': 'Tên vị trí',
            'sort_order': 'Thứ tự hiển thị',
            'is_active': 'Đang sử dụng',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True).order_by(
            'sort_order', 'name',
        )
        self.fields['department'].empty_label = '-- Chọn phòng ban --'
        self.fields['department'].required = True
        if not self.instance.pk:
            dept_id = self._initial_department_id()
            if dept_id:
                pos_qs = DepartmentPosition.objects.filter(department_id=dept_id)
                self.fields['sort_order'].initial = next_sort_order(pos_qs)
            self.fields['name'].initial = ORG_DEPARTMENT_HEAD_LABEL
            self.fields['sort_order'].help_text = 'Tự động đánh số trong phòng ban (có thể sửa).'

    def _initial_department_id(self):
        return _coerce_pk(self.initial.get('department') if self.initial else None) or _coerce_pk(
            self.data.get('department') if self.data else None,
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.pk and obj.department_id:
            init_dept = _coerce_pk(self.initial.get('department') if self.initial else None)
            scope_changed = init_dept is not None and obj.department_id != init_dept
            obj.sort_order = resolve_sort_order_on_create(
                posted=self.cleaned_data['sort_order'],
                field_initial=self.fields['sort_order'].initial,
                scope_changed=scope_changed,
                queryset=DepartmentPosition.objects.filter(department_id=obj.department_id),
            )
        if commit:
            obj.save()
        return obj

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Tên vị trí không được để trống.')
        dept = self.cleaned_data.get('department')
        if not dept:
            return name
        dup = DepartmentPosition.objects.filter(department=dept, name__iexact=name)
        if self.instance.pk:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError('Vị trí này đã tồn tại trong phòng ban đã chọn.')
        return name

    def clean_department(self):
        dept = self.cleaned_data.get('department')
        if not dept:
            raise forms.ValidationError('Phòng ban không được để trống.')
        return dept


def sync_profiles_for_position_change(*, old_division_id, old_name, position):
    """Khi sửa vị trí: chuyển NV (division + job_position) theo bộ phận / tên mới."""
    if not old_division_id or not old_name:
        return 0
    new_name = (position.name or '').strip()
    old_name_s = (old_name or '').strip()
    if not new_name or not old_name_s:
        return 0
    division_changed = old_division_id != position.division_id
    name_changed = old_name_s.lower() != new_name.lower()
    if not division_changed and not name_changed:
        return 0
    qs = Profile.objects.filter(
        division_id=old_division_id,
        job_position__iexact=old_name_s,
    )
    count = qs.count()
    if not count:
        return 0
    updates = {}
    if division_changed:
        updates['division_id'] = position.division_id
        division = position.division
        if division is None and position.division_id:
            division = Division.objects.only('department_id').get(pk=position.division_id)
        updates['department_id'] = division.department_id if division else None
    if name_changed:
        updates['job_position'] = new_name
    qs.update(**updates)
    return count


class DivisionPositionForm(forms.ModelForm):
    class Meta:
        model = DivisionPosition
        fields = ['division', 'name', 'sort_order', 'is_active']
        widgets = {
            'division': forms.Select(attrs=SELECT),
            'name': forms.TextInput(attrs={
                **INPUT,
                'placeholder': 'VD: Công nhân may, Trưởng ca…',
            }),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'division': 'Bộ phận',
            'name': 'Tên vị trí',
            'sort_order': 'Thứ tự hiển thị',
            'is_active': 'Đang sử dụng',
        }

    def __init__(self, *args, **kwargs):
        division_qs = kwargs.pop('division_queryset', None)
        super().__init__(*args, **kwargs)
        qs = division_qs or Division.objects.filter(is_active=True).select_related('department')
        self.fields['division'].queryset = qs.order_by('department__sort_order', 'department__name', 'sort_order', 'name')
        if not self.instance.pk:
            div_id = self._initial_division_id()
            if div_id:
                pos_qs = DivisionPosition.objects.filter(division_id=div_id)
                self.fields['sort_order'].initial = next_sort_order(pos_qs)
            self.fields['sort_order'].help_text = 'Tự động đánh số trong bộ phận đã chọn (có thể sửa).'

    def _initial_division_id(self):
        return _coerce_pk(self.initial.get('division') if self.initial else None) or _coerce_pk(
            self.data.get('division') if self.data else None,
        )

    def save(self, commit=True):
        old_division_id = None
        old_name = None
        if self.instance.pk:
            prev = (
                DivisionPosition.objects
                .only('division_id', 'name')
                .filter(pk=self.instance.pk)
                .first()
            )
            if prev:
                old_division_id = prev.division_id
                old_name = prev.name

        obj = super().save(commit=False)
        if not obj.pk and obj.division_id:
            init_div = _coerce_pk(self.initial.get('division') if self.initial else None)
            scope_changed = init_div is not None and obj.division_id != init_div
            obj.sort_order = resolve_sort_order_on_create(
                posted=self.cleaned_data['sort_order'],
                field_initial=self.fields['sort_order'].initial,
                scope_changed=scope_changed,
                queryset=DivisionPosition.objects.filter(division_id=obj.division_id),
            )
        self.profiles_synced_count = 0
        if commit:
            obj.save()
            if self.instance.pk:
                self.profiles_synced_count = sync_profiles_for_position_change(
                    old_division_id=old_division_id,
                    old_name=old_name,
                    position=obj,
                )
        return obj

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Tên vị trí không được để trống.')
        division = self.cleaned_data.get('division')
        if not division:
            return name
        dup = DivisionPosition.objects.filter(division=division, name__iexact=name)
        if self.instance.pk:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError('Vị trí này đã tồn tại trong bộ phận đã chọn.')
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
    'de_xuat': 'bi-lightbulb',
    'ho_tro': 'bi-tools',
    'nas_storage': 'bi-hdd-network',
    'equipment': 'bi-pc-display',
    'feedback': 'bi-chat-square-text',
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

