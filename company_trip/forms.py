import re

from django import forms

from company_trip.constants import (
    DEFAULT_PICKUP_POINT,
    ROOM_CHOICES,
    ROOM_COLLEAGUE,
    ROOM_ORGANIZER,
    ROOM_RELATIVE,
    STATUS_REGISTERED,
)
from company_trip.models import TripEmailTemplate, TripRegistration, TripSettings
from company_trip.phones import domestic_phone
from hrm.choices import GENDER_FORM_CHOICES
from hrm.models import Profile


class TripRegistrationForm(forms.ModelForm):
    companion1_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    invite_email = forms.EmailField(
        label='Email',
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@congty.com',
            'autocomplete': 'email',
        }),
    )
    relative_gender = forms.ChoiceField(
        label='Giới tính',
        choices=GENDER_FORM_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = TripRegistration
        fields = [
            'phone',
            'room_type',
            'pickup_point',
            'note',
            'relative_full_name',
            'relative_cccd',
            'relative_phone',
            'relative_gender',
            'relative_date_of_birth',
        ]
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Số điện thoại'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'pickup_point': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',
            }),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'relative_full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Họ và tên'}),
            'relative_cccd': forms.TextInput(attrs={
                'class': 'form-control',
                'inputmode': 'numeric',
                'maxlength': '12',
                'placeholder': '12 chữ số',
                'autocomplete': 'off',
            }),
            'relative_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Số điện thoại'}),
            'relative_date_of_birth': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
        }

    def __init__(self, *args, current_profile=None, current_registration=None, **kwargs):
        self.current_profile = current_profile
        self.current_registration = current_registration
        super().__init__(*args, **kwargs)
        self.fields['room_type'].choices = ROOM_CHOICES
        self.fields['relative_date_of_birth'].required = False
        self.fields['relative_date_of_birth'].input_formats = ['%Y-%m-%d']
        for name in ('relative_full_name', 'relative_cccd', 'relative_phone'):
            self.fields[name].required = False
        self.initial['pickup_point'] = DEFAULT_PICKUP_POINT
        self.fields['pickup_point'].initial = DEFAULT_PICKUP_POINT
        if self.is_bound:
            data = self.data.copy()
            data[self.add_prefix('pickup_point')] = DEFAULT_PICKUP_POINT
            self.data = data

    def clean(self):
        cleaned = super().clean()
        cleaned['pickup_point'] = DEFAULT_PICKUP_POINT
        cleaned['phone'] = domestic_phone(cleaned.get('phone'))
        if not cleaned.get('room_type'):
            cleaned['companion1_obj'] = None
            cleaned['organized_committee'] = False
            return cleaned
        room_type = cleaned.get('room_type')
        companion1 = None

        if room_type == ROOM_COLLEAGUE:
            companion1 = self._load_colleague(cleaned.get('companion1_id') or None)
            if companion1 is None and not self.errors.get('companion1_id'):
                self.add_error('companion1_id', 'Chọn một đồng nghiệp để đăng ký chung.')
            self._clear_relative(cleaned)
        elif room_type == ROOM_RELATIVE:
            self._clean_relative(cleaned)
        else:
            self._clear_relative(cleaned)

        cleaned['companion1_obj'] = companion1
        cleaned['organized_committee'] = room_type == ROOM_ORGANIZER
        return cleaned

    def _load_colleague(self, pk):
        if not pk:
            return None
        try:
            profile = Profile.objects.select_related('user', 'department').get(
                pk=pk, is_employed=True, user__is_active=True,
            )
        except Profile.DoesNotExist:
            self.add_error('companion1_id', 'Đồng nghiệp không hợp lệ hoặc đã nghỉ việc.')
            return None

        if self.current_profile and profile.pk == self.current_profile.pk:
            self.add_error('companion1_id', 'Không thể chọn chính mình.')
            return None

        if TripRegistration.objects.filter(profile=profile, status=STATUS_REGISTERED).exists():
            self.add_error(
                'companion1_id',
                'Đồng nghiệp này đã tự đăng ký. Chỉ một người cần đăng ký cho cả hai.',
            )
            return None

        invited = TripRegistration.objects.filter(
            companion1=profile,
            status=STATUS_REGISTERED,
            room_type=ROOM_COLLEAGUE,
        )
        if self.current_registration is not None:
            invited = invited.exclude(pk=self.current_registration.pk)
        if invited.exists():
            self.add_error('companion1_id', 'Đồng nghiệp này đã được người khác đăng ký.')
            return None
        return profile

    def _clean_relative(self, cleaned):
        required = (
            ('relative_full_name', 'Nhập họ tên người thân.'),
            ('relative_cccd', 'Nhập số CCCD người thân.'),
            ('relative_phone', 'Nhập số điện thoại người thân.'),
            ('relative_gender', 'Chọn giới tính người thân.'),
            ('relative_date_of_birth', 'Nhập ngày sinh người thân.'),
        )
        for field, message in required:
            if field in self.errors:
                continue
            value = cleaned.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                self.add_error(field, message)

        name = (cleaned.get('relative_full_name') or '').strip()
        phone = (cleaned.get('relative_phone') or '').strip()
        cccd = re.sub(r'\D', '', cleaned.get('relative_cccd') or '')
        cleaned['relative_full_name'] = name
        cleaned['relative_phone'] = domestic_phone(phone)
        cleaned['relative_cccd'] = cccd
        if cccd and not re.fullmatch(r'\d{12}', cccd):
            self.add_error('relative_cccd', 'Số CCCD phải gồm 12 chữ số.')

    @staticmethod
    def _clear_relative(cleaned):
        cleaned['relative_full_name'] = ''
        cleaned['relative_cccd'] = ''
        cleaned['relative_phone'] = ''
        cleaned['relative_gender'] = ''
        cleaned['relative_date_of_birth'] = None


class TripSettingsForm(forms.ModelForm):
    class Meta:
        model = TripSettings
        fields = [
            'title', 'destination', 'start_date', 'end_date',
            'dates_display', 'registration_open',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'destination': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'dates_display': forms.TextInput(attrs={'class': 'form-control'}),
            'registration_open': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TripEmailTemplateForm(forms.ModelForm):
    class Meta:
        model = TripEmailTemplate
        fields = ['subject', 'body']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
        }

