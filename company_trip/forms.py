import re
from datetime import datetime

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
from company_trip.relatives import MAX_RELATIVES
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
    class Meta:
        model = TripRegistration
        fields = [
            'phone',
            'room_type',
            'pickup_point',
            'note',
        ]
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Số điện thoại'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'pickup_point': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',
            }),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, current_profile=None, current_registration=None, **kwargs):
        self.current_profile = current_profile
        self.current_registration = current_registration
        super().__init__(*args, **kwargs)
        self.fields['room_type'].choices = ROOM_CHOICES
        self.relative_slots = self._posted_relative_slots() if self.is_bound else self._initial_relative_slots()
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
            cleaned['relatives'] = []
        elif room_type == ROOM_RELATIVE:
            cleaned['relatives'] = self._clean_relatives()
        else:
            cleaned['relatives'] = []

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

    def _blank_relative_slot(self, index, **values):
        slot = {
            'index': index,
            'full_name': '',
            'cccd': '',
            'phone': '',
            'gender': '',
            'date_of_birth': '',
            'errors': {},
            'visible': index == 1,
        }
        slot.update(values)
        return slot

    def _slot_filled(self, slot) -> bool:
        return any(slot[key] for key in ('full_name', 'cccd', 'phone', 'gender', 'date_of_birth'))

    def _initial_relative_slots(self):
        people = list(self.initial.get('relatives') or [])
        slots = []
        for index in range(1, MAX_RELATIVES + 1):
            person = people[index - 1] if index - 1 < len(people) else {}
            dob = person.get('date_of_birth') or ''
            if hasattr(dob, 'isoformat'):
                dob = dob.isoformat()
            slot = self._blank_relative_slot(
                index,
                full_name=(person.get('full_name') or '').strip(),
                cccd=(person.get('cccd') or '').strip(),
                phone=(person.get('phone') or '').strip(),
                gender=(person.get('gender') or '').strip(),
                date_of_birth=dob,
            )
            slot['visible'] = index == 1 or self._slot_filled(slot)
            slots.append(slot)
        return slots

    def _posted_relative_slots(self):
        slots = []
        for index in range(1, MAX_RELATIVES + 1):
            prefix = f'relative_{index}_'
            slot = self._blank_relative_slot(
                index,
                full_name=(self.data.get(prefix + 'full_name') or '').strip(),
                cccd=re.sub(r'\D', '', self.data.get(prefix + 'cccd') or ''),
                phone=domestic_phone(self.data.get(prefix + 'phone') or ''),
                gender=(self.data.get(prefix + 'gender') or '').strip(),
                date_of_birth=(self.data.get(prefix + 'date_of_birth') or '').strip(),
            )
            slot['visible'] = index == 1 or self._slot_filled(slot)
            slots.append(slot)
        return slots

    def _clean_relatives(self):
        slots = self._posted_relative_slots()
        people = []
        seen_cccd = set()
        has_error = False
        for slot in slots:
            if slot['index'] != 1 and not self._slot_filled(slot):
                slot['visible'] = False
                continue
            slot['visible'] = True
            errors = {}
            if not slot['full_name']:
                errors['full_name'] = 'Nhập họ tên người thân.'
            if not re.fullmatch(r'\d{12}', slot['cccd'] or ''):
                errors['cccd'] = 'Số CCCD phải gồm 12 chữ số.'
            elif slot['cccd'] in seen_cccd:
                errors['cccd'] = 'Số CCCD trùng người thân khác.'
            else:
                seen_cccd.add(slot['cccd'])
            if not slot['phone']:
                errors['phone'] = 'Nhập số điện thoại người thân.'
            if slot['gender'] not in {'M', 'F'}:
                errors['gender'] = 'Chọn giới tính người thân.'
            dob = None
            if not slot['date_of_birth']:
                errors['date_of_birth'] = 'Nhập ngày sinh người thân.'
            else:
                try:
                    dob = datetime.strptime(slot['date_of_birth'], '%Y-%m-%d').date()
                except ValueError:
                    errors['date_of_birth'] = 'Ngày sinh không hợp lệ.'
            slot['errors'] = errors
            if errors:
                has_error = True
                continue
            people.append({
                'full_name': slot['full_name'],
                'cccd': slot['cccd'],
                'phone': slot['phone'],
                'gender': slot['gender'],
                'date_of_birth': dob,
            })
        self.relative_slots = slots
        if has_error or not people:
            self.add_error(None, 'Điền đủ thông tin người thân. Tối đa 3 người.')
            return []
        return people


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

