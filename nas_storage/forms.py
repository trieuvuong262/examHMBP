from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet, modelformset_factory

from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import NasPathError, normalize_rel_path

INPUT = {'class': 'form-control form-control-sm'}
SELECT = {'class': 'form-select form-select-sm'}


class NasUserFolderAccessForm(forms.ModelForm):
    class Meta:
        model = NasUserFolderAccess
        fields = ['label', 'rel_path', 'description', 'sort_order', 'is_active']
        widgets = {
            'label': forms.TextInput(attrs={**INPUT, 'placeholder': 'Thư mục cá nhân'}),
            'rel_path': forms.TextInput(attrs={**INPUT, 'placeholder': 'HCNS/Annt'}),
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
        fields = ['name', 'nas_principal', 'description', 'sort_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**INPUT, 'placeholder': 'SX'}),
            'nas_principal': forms.TextInput(attrs={**INPUT, 'placeholder': '@SX@ldap.justplay.local'}),
            'description': forms.TextInput(attrs={**INPUT}),
            'sort_order': forms.NumberInput(attrs={**INPUT, 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


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
            ('', 'Tuỳ chỉnh'),
            ('read', 'Chỉ đọc'),
            ('read_write', 'Đọc + Ghi (mặc định)'),
            ('full', 'Đầy đủ (gồm Administration)'),
        ),
        label='Mẫu nhanh',
        widget=forms.Select(attrs=SELECT),
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
        widgets = {
            'group': forms.Select(attrs=SELECT),
            'permission_type': forms.Select(attrs=SELECT),
            'apply_to': forms.Select(attrs=SELECT),
            'inherit_from_parent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, folder=None, **kwargs):
        super().__init__(*args, **kwargs)
        from nas_storage.models import NasAccessGroup

        self.fields['group'].queryset = NasAccessGroup.objects.filter(is_active=True).order_by(
            'sort_order', 'name',
        )
        for name in (
            'perm_traverse', 'perm_list_read', 'perm_read_attr', 'perm_read_ext_attr', 'perm_read_acl',
            'perm_create_files', 'perm_create_folders', 'perm_write_attr', 'perm_write_ext_attr',
            'perm_delete_children', 'perm_delete', 'perm_change_acl', 'perm_take_ownership',
        ):
            self.fields[name].widget = forms.CheckboxInput(attrs={'class': 'form-check-input'})

    def clean(self):
        cleaned = super().clean()
        preset = (cleaned.get('preset') or '').strip()
        if preset:
            from nas_storage.permission_defs import flags_from_preset

            for name, value in flags_from_preset(preset).items():
                cleaned[name] = value
        return cleaned

