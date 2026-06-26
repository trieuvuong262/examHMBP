from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet, modelformset_factory

from nas_storage.models import NasUserFolderAccess, NasUserFolderAcl
from nas_storage.nas_paths import NasPathError, normalize_rel_path

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
        ]
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'SX'}),
            'nas_principal': forms.TextInput(attrs={**INPUT, 'placeholder': '@SX@ldap.justplay.local'}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'portal_browse_all': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'portal_members': forms.SelectMultiple(attrs={**SELECT, 'size': 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import User

        from hrm.user_search import exclude_hidden_hrm_users

        self.fields['portal_members'].queryset = (
            exclude_hidden_hrm_users(User.objects.filter(is_active=True))
            .order_by('username')
        )
        self.fields['portal_members'].required = False
        self.fields['portal_browse_all'].help_text = (
            'Bật cho Ban Giám đốc (TGD): mọi thành viên nhóm xem tất cả share trên Portal. '
            'Tự gán quyền đọc trên mọi share khi lưu.'
        )


class NasShareFolderForm(forms.ModelForm):
    class Meta:
        from nas_storage.models import NasShareFolder

        model = NasShareFolder
        fields = ['share_name', 'display_name', 'volume_path', 'description', 'sort_order', 'is_active']
        widgets = {
            'share_name': forms.TextInput(attrs={**INPUT, 'placeholder': '07_SAN_XUAT'}),
            'display_name': forms.TextInput(attrs={**INPUT}),
            'volume_path': forms.TextInput(attrs={**INPUT, 'placeholder': '/volume1/07_SAN_XUAT'}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class NasFolderPermissionForm(forms.ModelForm):
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
            'permission_type': 'Hành động',
            'apply_to': 'Phạm vi áp dụng',
            'inherit_from_parent': 'Kế thừa từ thư mục cha',
        }
        widgets = {
            'group': forms.Select(attrs=SELECT),
            'permission_type': forms.Select(attrs=SELECT),
            'apply_to': forms.Select(attrs=SELECT),
            'inherit_from_parent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, folder=None, **kwargs):
        super().__init__(*args, **kwargs)
        from nas_storage.models import NasAccessGroup
        from nas_storage.permission_defs import detect_preset_from_flags

        self.fields['group'].queryset = NasAccessGroup.objects.filter(is_active=True).order_by(
            'sort_order', 'name',
        )
        for name in (
            'perm_traverse', 'perm_list_read', 'perm_read_attr', 'perm_read_ext_attr', 'perm_read_acl',
            'perm_create_files', 'perm_create_folders', 'perm_write_attr', 'perm_write_ext_attr',
            'perm_delete_children', 'perm_delete', 'perm_change_acl', 'perm_take_ownership',
        ):
            self.fields[name].widget = forms.CheckboxInput(attrs={'class': 'form-check-input'})

        if self.instance and self.instance.pk:
            preset = detect_preset_from_flags(self.instance.permission_flags())
            if preset != 'custom':
                self.fields['preset'].initial = preset
        else:
            self.fields['preset'].initial = 'read_write'

    def clean(self):
        cleaned = super().clean()
        preset = (cleaned.get('preset') or '').strip()
        if preset:
            from nas_storage.permission_defs import flags_from_preset

            for name, value in flags_from_preset(preset).items():
                cleaned[name] = value
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

