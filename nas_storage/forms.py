from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet, modelformset_factory

from nas_storage.models import NasUserFolderAccess, NasUserFolderAcl
from nas_storage.nas_paths import NasPathError, normalize_rel_path, normalize_volume_path

INPUT = {'class': 'form-control form-control-sm'}
SELECT = {'class': 'form-select form-select-sm'}


class NasUserFolderAccessForm(forms.ModelForm):
    class Meta:
        model = NasUserFolderAccess
        fields = ['label', 'rel_path', 'description', 'sort_order', 'is_active']
        widgets = {
            'label': forms.TextInput(attrs={**INPUT, 'placeholder': 'Thư mục cá nhân'}),
            'rel_path': forms.TextInput(attrs={
                **INPUT,
                'placeholder': '05_MARKETING/lvanhthu hoặc KD-MKT/_CHUNG',
            }),
            'description': forms.TextInput(attrs={**INPUT, 'placeholder': 'Tuỳ chọn'}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_permitted = True
        for name in ('label', 'rel_path', 'description'):
            self.fields[name].required = False

    def clean_rel_path(self):
        raw = (self.cleaned_data.get('rel_path') or '').strip()
        if not raw:
            return ''
        try:
            return normalize_rel_path(raw)
        except NasPathError as exc:
            raise ValidationError(str(exc)) from exc

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        rel_path = (cleaned.get('rel_path') or '').strip()
        if not rel_path:
            if self.instance.pk:
                raise ValidationError('Đường dẫn NAS không được để trống.')
            return cleaned
        label = (cleaned.get('label') or '').strip()
        if not label:
            parts = rel_path.split('/')
            cleaned['label'] = parts[-1] if parts else rel_path
        cleaned['rel_path'] = rel_path
        return cleaned


class NasUserFolderAccessFormSet(BaseModelFormSet):
    def clean(self):
        super().clean()
        paths = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            rel = form.cleaned_data.get('rel_path')
            if not rel or not form.cleaned_data.get('is_active', True):
                continue
            if rel in paths:
                raise ValidationError(f'Đường dẫn NAS trùng: {rel}')
            paths.append(rel)


NasUserFolderAccessFormSet = modelformset_factory(
    NasUserFolderAccess,
    form=NasUserFolderAccessForm,
    formset=NasUserFolderAccessFormSet,
    extra=1,
    can_delete=True,
)


class NasAccessGroupForm(forms.ModelForm):
    class Meta:
        from nas_storage.models import NasAccessGroup

        model = NasAccessGroup
        fields = [
            'name',
            'nas_principal',
            'description',
            'sort_order',
            'is_active',
            'portal_browse_all',
            'portal_members',
            'portal_excluded_members',
        ]
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'SX'}),
            'nas_principal': forms.TextInput(attrs={**INPUT, 'placeholder': '@SX@ldap.justplay.local'}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'portal_browse_all': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'portal_members': forms.SelectMultiple(attrs={'class': 'd-none jp-user-picker-native'}),
            'portal_excluded_members': forms.SelectMultiple(attrs={'class': 'd-none jp-user-picker-native'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import User

        from hrm.user_search import exclude_hidden_hrm_users
        from nas_storage.portal_access import department_user_ids_for_nas_group

        base_qs = (
            exclude_hidden_hrm_users(User.objects.filter(is_active=True))
            .select_related('profile', 'profile__department', 'profile__division')
            .order_by('profile__full_name', 'username')
        )
        self.fields['portal_members'].queryset = base_qs
        self.fields['portal_members'].label = 'Thành viên bổ sung'
        self.fields['portal_members'].required = False

        group_name = ''
        if self.instance and self.instance.pk:
            group_name = self.instance.name
        elif self.data:
            group_name = (self.data.get('name') or '').strip()

        dept_ids = department_user_ids_for_nas_group(group_name)
        if dept_ids:
            self.fields['portal_excluded_members'].queryset = base_qs.filter(pk__in=dept_ids)
        else:
            self.fields['portal_excluded_members'].queryset = base_qs.none()
        self.fields['portal_excluded_members'].label = 'Loại trừ khỏi nhóm'
        self.fields['portal_excluded_members'].required = False

    def clean(self):
        cleaned = super().clean()
        members = set(cleaned.get('portal_members') or [])
        excluded = set(cleaned.get('portal_excluded_members') or [])
        overlap = members & excluded
        if overlap:
            names = ', '.join(sorted(u.username for u in overlap))
            raise ValidationError(
                f'Không thể vừa bổ sung vừa loại trừ cùng user: {names}.',
            )
        return cleaned


class NasShareFolderRootForm(forms.ModelForm):
    class Meta:
        from nas_storage.models import NasShareFolder

        model = NasShareFolder
        fields = [
            'share_name',
            'display_name',
            'volume_path',
            'description',
            'sort_order',
            'is_active',
        ]
        widgets = {
            'share_name': forms.TextInput(attrs={**INPUT, 'placeholder': '07_SAN_XUAT'}),
            'display_name': forms.TextInput(attrs={**INPUT}),
            'volume_path': forms.TextInput(attrs={**INPUT, 'placeholder': '/volume1/07_SAN_XUAT'}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'share_name': 'Portal tạo share mới trên NAS khi lưu (nếu chưa có). Hoặc dùng Quét từ NAS.',
        }

    def clean_share_name(self):
        name = (self.cleaned_data.get('share_name') or '').strip()
        if not name:
            raise ValidationError('Tên share NAS không được để trống.')
        return name

    def clean_volume_path(self):
        raw = self.cleaned_data.get('volume_path') or ''
        share = (self.cleaned_data.get('share_name') or '').strip()
        if not share and self.instance:
            share = (self.instance.share_name or '').strip()
        try:
            return normalize_volume_path(raw, share_name=share)
        except NasPathError as exc:
            raise ValidationError(str(exc)) from exc


class NasShareFolderChildForm(forms.ModelForm):
    class Meta:
        from nas_storage.models import NasShareFolder

        model = NasShareFolder
        fields = [
            'sub_path',
            'display_name',
            'description',
            'sort_order',
            'inherits_permissions',
            'is_active',
        ]
        labels = {
            'sub_path': 'Tên thư mục con',
            'inherits_permissions': 'Kế thừa phân quyền từ thư mục cha',
        }
        help_texts = {
            'sub_path': 'Portal tạo mới trên NAS khi lưu (vd. KD-MKT hoặc KD-MKT/_CHUNG).',
        }
        widgets = {
            'sub_path': forms.TextInput(attrs={**INPUT, 'placeholder': 'KD-MKT'}),
            'display_name': forms.TextInput(attrs={**INPUT}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'inherits_permissions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, parent=None, **kwargs):
        self.parent_folder = parent
        super().__init__(*args, **kwargs)
        if parent and not parent.is_root:
            self.fields['sub_path'].label = 'Tên thư mục (một cấp)'
            self.fields['sub_path'].help_text = (
                f'Tạo trong «{parent.display_name}» — chỉ nhập tên cấp này (vd. _CHUNG). Portal tạo trên NAS khi lưu.'
            )
            self.fields['sub_path'].widget.attrs['placeholder'] = '_CHUNG'
        elif parent:
            self.fields['sub_path'].help_text = (
                'Portal tạo mới trên NAS khi lưu. Có thể nhập một cấp (KD-MKT) hoặc nhiều cấp (KD-MKT/_CHUNG).'
            )

    def clean_sub_path(self):
        raw = (self.cleaned_data.get('sub_path') or '').strip()
        if not raw:
            raise ValidationError('Tên thư mục không được để trống.')
        try:
            segment = normalize_rel_path(raw)
        except NasPathError as exc:
            raise ValidationError(str(exc)) from exc
        if self.parent_folder and not self.parent_folder.is_root and '/' in segment:
            raise ValidationError('Thư mục lồng nhau: chỉ nhập tên một cấp (vd. _CHUNG).')
        return segment

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.parent_folder:
            obj.parent = self.parent_folder
        if commit:
            obj.save()
        return obj


NasShareFolderForm = NasShareFolderRootForm


class NasFolderPermissionForm(forms.ModelForm):
    ASSIGNEE_GROUP = 'group'
    ASSIGNEE_USER = 'user'

    assignee_type = forms.ChoiceField(
        choices=(
            (ASSIGNEE_GROUP, 'Nhóm quyền'),
            (ASSIGNEE_USER, 'Nhân viên cụ thể'),
        ),
        label='Áp dụng cho',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial=ASSIGNEE_GROUP,
    )
    preset = forms.ChoiceField(
        required=False,
        choices=(
            ('read_write', 'Đọc + Ghi'),
            ('read', 'Chỉ đọc'),
            ('full', 'Đầy đủ (quản trị)'),
            ('', 'Tuỳ chỉnh nâng cao'),
        ),
        label='Mức quyền',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        from nas_storage.models import NasFolderPermission

        model = NasFolderPermission
        fields = [
            'group',
            'user',
            'permission_type',
            'apply_to',
            'inherit_from_parent',
            'perm_traverse',
            'perm_list_read',
            'perm_read_attr',
            'perm_read_ext_attr',
            'perm_read_acl',
            'perm_create_files',
            'perm_create_folders',
            'perm_write_attr',
            'perm_write_ext_attr',
            'perm_delete_children',
            'perm_delete',
            'perm_change_acl',
            'perm_take_ownership',
        ]
        labels = {
            'group': 'Nhóm',
            'user': 'Nhân viên',
            'permission_type': 'Hành động',
            'apply_to': 'Phạm vi áp dụng',
            'inherit_from_parent': 'Kế thừa từ thư mục cha',
        }
        widgets = {
            'group': forms.Select(attrs=SELECT),
            'user': forms.Select(attrs={**SELECT, 'data-placeholder': 'Chọn account...'}),
            'permission_type': forms.Select(attrs=SELECT),
            'apply_to': forms.Select(attrs=SELECT),
            'inherit_from_parent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, folder=None, **kwargs):
        self.folder = folder
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import User

        from hrm.user_search import exclude_hidden_hrm_users
        from nas_storage.models import NasAccessGroup, NasFolderPermission
        from nas_storage.permission_defs import detect_preset_from_flags

        group_qs = NasAccessGroup.objects.filter(is_active=True).order_by('sort_order', 'name')
        user_qs = exclude_hidden_hrm_users(
            User.objects.filter(is_active=True).select_related('profile'),
        ).order_by('profile__full_name', 'username')
        if folder and not (self.instance and self.instance.pk):
            used_group_ids = NasFolderPermission.objects.filter(
                folder=folder,
                group__isnull=False,
            ).values_list('group_id', flat=True)
            used_user_ids = NasFolderPermission.objects.filter(
                folder=folder,
                user__isnull=False,
            ).values_list('user_id', flat=True)
            group_qs = group_qs.exclude(pk__in=used_group_ids)
            user_qs = user_qs.exclude(pk__in=used_user_ids)
        self.fields['group'].queryset = group_qs
        self.fields['group'].required = False
        self.fields['user'].queryset = user_qs
        self.fields['user'].required = False
        self.fields['user'].label_from_instance = self._user_label

        if self.instance and self.instance.pk:
            if self.instance.user_id:
                self.fields['assignee_type'].initial = self.ASSIGNEE_USER
            else:
                self.fields['assignee_type'].initial = self.ASSIGNEE_GROUP
            preset = detect_preset_from_flags(self.instance.permission_flags())
            if preset == 'custom':
                self.fields['preset'].initial = ''
            else:
                self.fields['preset'].initial = preset
        else:
            self.fields['preset'].initial = 'read_write'

        for name in (
            'perm_traverse', 'perm_list_read', 'perm_read_attr', 'perm_read_ext_attr', 'perm_read_acl',
            'perm_create_files', 'perm_create_folders', 'perm_write_attr', 'perm_write_ext_attr',
            'perm_delete_children', 'perm_delete', 'perm_change_acl', 'perm_take_ownership',
        ):
            self.fields[name].widget = forms.CheckboxInput(attrs={'class': 'form-check-input'})

    @staticmethod
    def _user_label(user) -> str:
        profile = getattr(user, 'profile', None)
        full_name = (profile.full_name if profile and profile.full_name else '').strip()
        if full_name:
            return f'{full_name} ({user.username})'
        return user.username

    def clean(self):
        cleaned = super().clean()
        preset = (cleaned.get('preset') or '').strip()
        if preset:
            from nas_storage.permission_defs import flags_from_preset

            for name, value in flags_from_preset(preset).items():
                cleaned[name] = value

        assignee_type = cleaned.get('assignee_type') or self.ASSIGNEE_GROUP
        group = cleaned.get('group')
        user = cleaned.get('user')
        folder = self.folder

        if assignee_type == self.ASSIGNEE_USER:
            cleaned['group'] = None
            if not user:
                self.add_error('user', 'Chọn nhân viên cần cấp quyền.')
        else:
            cleaned['user'] = None
            if not group:
                self.add_error('group', 'Chọn nhóm quyền.')

        group = cleaned.get('group')
        user = cleaned.get('user')
        if folder and group:
            from nas_storage.models import NasFolderPermission

            qs = NasFolderPermission.objects.filter(folder=folder, group=group)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'group',
                    f'Nhóm «{group.name}» đã có quyền trên thư mục này. Hãy sửa bản ghi hiện có.',
                )
        if folder and user:
            from nas_storage.models import NasFolderPermission

            qs = NasFolderPermission.objects.filter(folder=folder, user=user)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'user',
                    f'Nhân viên «{user.username}» đã có quyền trên thư mục này. Hãy sửa bản ghi hiện có.',
                )
        return cleaned


class NasUserFolderAclForm(forms.ModelForm):
    class Meta:
        model = NasUserFolderAcl
        fields = ['folder', 'sub_path', 'access_level', 'label', 'is_active']
        labels = {
            'folder': 'Share NAS',
            'sub_path': 'Thư mục con',
            'access_level': 'Quyền RaiDrive',
            'label': 'Ghi chú',
            'is_active': 'Bật',
        }
        widgets = {
            'folder': forms.Select(attrs=SELECT),
            'sub_path': forms.TextInput(attrs={**INPUT, 'placeholder': 'lvanhthu'}),
            'access_level': forms.Select(attrs=SELECT),
            'label': forms.TextInput(attrs={**INPUT, 'placeholder': 'Tuỳ chọn'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from nas_storage.models import NasShareFolder

        self.fields['folder'].queryset = NasShareFolder.objects.filter(is_active=True).order_by(
            'sort_order', 'share_name',
        )
        self.empty_permitted = True

    def clean_sub_path(self):
        raw = (self.cleaned_data.get('sub_path') or '').strip()
        if not raw:
            return ''
        try:
            return normalize_rel_path(raw)
        except NasPathError as exc:
            raise ValidationError(str(exc)) from exc


class NasUserFolderAclFormSet(BaseModelFormSet):
    def clean(self):
        super().clean()
        keys = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            sub = form.cleaned_data.get('sub_path')
            folder = form.cleaned_data.get('folder')
            if not sub or not folder or not form.cleaned_data.get('is_active', True):
                continue
            key = (folder.pk, sub)
            if key in keys:
                raise ValidationError(f'Trùng thư mục: {folder.share_name}/{sub}')
            keys.append(key)


NasUserFolderAclFormSet = modelformset_factory(
    NasUserFolderAcl,
    form=NasUserFolderAclForm,
    formset=NasUserFolderAclFormSet,
    extra=1,
    can_delete=True,
)

