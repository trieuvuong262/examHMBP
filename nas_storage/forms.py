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
