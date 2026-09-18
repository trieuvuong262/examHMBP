from django import forms

from company_trip.constants import (
    BREAKFAST_CHOICES,
    ROOM_2,
    ROOM_3,
    ROOM_CHOICES,
    ROOM_ORGANIZER,
    ROUTE_CHOICES,
    SHOPPING_CHOICES,
    VEGETARIAN_CHOICES,
)
from company_trip.models import TripEmailTemplate, TripRegistration, TripSettings
from hrm.models import Profile


class TripRegistrationForm(forms.ModelForm):
    companion1_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    companion2_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = TripRegistration
        fields = [
            'phone',
            'room_type',
            'vegetarian',
            'allergy_note',
            'pickup_point',
            'breakfast_choice',
            'route',
            'detail_route',
            'shopping',
            'note',
        ]
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Số điện thoại'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'vegetarian': forms.Select(attrs={'class': 'form-select'}),
            'allergy_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'pickup_point': forms.TextInput(attrs={'class': 'form-control'}),
            'breakfast_choice': forms.Select(attrs={'class': 'form-select'}),
            'route': forms.Select(attrs={'class': 'form-select'}),
            'detail_route': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'shopping': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, current_profile=None, **kwargs):
        self.current_profile = current_profile
        super().__init__(*args, **kwargs)
        self.fields['room_type'].choices = ROOM_CHOICES
        self.fields['vegetarian'].choices = VEGETARIAN_CHOICES
        self.fields['breakfast_choice'].choices = BREAKFAST_CHOICES
        self.fields['route'].choices = [('', '— Chọn lộ trình —')] + list(ROUTE_CHOICES)
        self.fields['shopping'].choices = SHOPPING_CHOICES
        self.fields['route'].required = True

    def clean(self):
        cleaned = super().clean()
        room_type = cleaned.get('room_type') or ROOM_ORGANIZER
        c1_id = cleaned.get('companion1_id') or None
        c2_id = cleaned.get('companion2_id') or None

        def _load(pk):
            if not pk:
                return None
            try:
                return Profile.objects.select_related('user', 'department').get(
                    pk=pk, is_employed=True, user__is_active=True,
                )
            except Profile.DoesNotExist:
                raise forms.ValidationError('Người cùng phòng không hợp lệ hoặc đã nghỉ việc.')

        companion1 = _load(c1_id)
        companion2 = _load(c2_id)

        if self.current_profile:
            for c in (companion1, companion2):
                if c and c.pk == self.current_profile.pk:
                    raise forms.ValidationError('Không thể chọn chính mình làm người cùng phòng.')

        if companion1 and companion2 and companion1.pk == companion2.pk:
            raise forms.ValidationError('Hai người cùng phòng không được trùng nhau.')

        # Phòng 2 = 2 người (bạn + 1); Phòng 3 = 3 người (bạn + 2).
        if room_type == ROOM_2 and not companion1:
            raise forms.ValidationError('Phòng 2 cần chọn đủ 2 người cùng phòng (bạn và 1 người nữa).')
        if room_type == ROOM_3 and (not companion1 or not companion2):
            raise forms.ValidationError('Phòng 3 cần chọn đủ 3 người cùng phòng (bạn và 2 người nữa).')
        if room_type == ROOM_ORGANIZER:
            companion1 = companion2 = None
        if room_type == ROOM_2:
            companion2 = None

        # Người đã có room_key khác (đã ghép phòng) không nhận thêm
        for c in (companion1, companion2):
            if not c:
                continue
            existing = TripRegistration.objects.filter(
                profile=c, status='registered',
            ).exclude(room_key='').first()
            if existing and existing.room_key:
                # Cho phép nếu cùng nhóm sẽ gán sau — chặn nếu đã thuộc key khác của người khác
                if self.current_profile:
                    my_reg = TripRegistration.objects.filter(profile=self.current_profile).first()
                    if my_reg and my_reg.room_key and existing.room_key == my_reg.room_key:
                        continue
                if existing.profile_id != (self.current_profile.pk if self.current_profile else None):
                    # Chỉ cảnh báo nhẹ nếu đã đăng ký với companion khác — vẫn cho phép BTC sắp xếp sau
                    pass

        cleaned['companion1_obj'] = companion1
        cleaned['companion2_obj'] = companion2
        cleaned['organized_committee'] = room_type == ROOM_ORGANIZER
        return cleaned


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


class RoomAssignForm(forms.Form):
    registration_id = forms.IntegerField(widget=forms.HiddenInput)
    room_key = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Để trống = tạo mã mới'}),
    )
    companion_ids = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        help_text='CSV profile ids',
    )
