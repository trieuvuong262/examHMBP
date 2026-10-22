from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from cham_cong.models import (
    AttendanceAdjustment, AttendancePolicy, AttendanceSupplement, Holiday, LeaveRequest,
    PayAdjustment, SalaryProfile, Shift, WorkSite,
)
from hrm.models import Department, Division


class TimeInput(forms.TimeInput):
    input_type = 'time'


class DateInput(forms.DateInput):
    input_type = 'date'


class SupplementForm(forms.ModelForm):
    class Meta:
        model = AttendanceSupplement
        fields = (
            'work_date', 'clock_in_time', 'clock_out_time',
            'break_out_time', 'break_in_time', 'reason',
        )
        widgets = {
            'work_date': DateInput(),
            'clock_in_time': TimeInput(),
            'clock_out_time': TimeInput(),
            'break_out_time': TimeInput(),
            'break_in_time': TimeInput(),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        work_date = cleaned.get('work_date')
        today = timezone.localdate()
        if work_date and work_date > today:
            self.add_error('work_date', 'Không bổ sung cho ngày trong tương lai.')
        if work_date and work_date < today - timedelta(days=45):
            self.add_error('work_date', 'Chỉ bổ sung trong 45 ngày gần nhất.')
        break_out = cleaned.get('break_out_time')
        break_in = cleaned.get('break_in_time')
        if bool(break_out) != bool(break_in):
            self.add_error('break_in_time', 'Nhập cả giờ ra nghỉ và giờ vào lại, hoặc để trống cả hai.')
        return cleaned


class AdjustmentForm(forms.ModelForm):
    class Meta:
        model = AttendanceAdjustment
        fields = (
            'work_date', 'clock_in_time', 'clock_out_time',
            'break_out_time', 'break_in_time', 'reason',
        )
        widgets = {
            'work_date': DateInput(),
            'clock_in_time': TimeInput(),
            'clock_out_time': TimeInput(),
            'break_out_time': TimeInput(),
            'break_in_time': TimeInput(),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        work_date = cleaned.get('work_date')
        today = timezone.localdate()
        if work_date and work_date > today:
            self.add_error('work_date', 'Không chỉnh ngày trong tương lai.')
        if work_date and work_date < today - timedelta(days=45):
            self.add_error('work_date', 'Chỉ chỉnh trong 45 ngày gần nhất.')
        break_out = cleaned.get('break_out_time')
        break_in = cleaned.get('break_in_time')
        if bool(break_out) != bool(break_in):
            self.add_error('break_in_time', 'Nhập cả giờ ra nghỉ và giờ vào lại, hoặc để trống cả hai.')
        return cleaned


class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ('kind', 'start_date', 'end_date', 'portion', 'reason')
        widgets = {
            'start_date': DateInput(),
            'end_date': DateInput(),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('kind')
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        portion = cleaned.get('portion') or LeaveRequest.PORTION_FULL
        today = timezone.localdate()
        if start and end and end < start:
            self.add_error('end_date', 'Ngày kết thúc phải từ ngày bắt đầu trở đi.')
        if start and start < today - timedelta(days=45):
            self.add_error('start_date', 'Chỉ gửi đơn trong 45 ngày gần đây hoặc cho ngày sắp tới.')
        if end and end > today + timedelta(days=366):
            self.add_error('end_date', 'Chỉ đặt nghỉ trong vòng một năm tới.')
        if kind in (LeaveRequest.KIND_LATE, LeaveRequest.KIND_EARLY):
            if start and end and start != end:
                self.add_error('end_date', 'Xin đi trễ hoặc về sớm chỉ cho một ngày.')
            cleaned['portion'] = LeaveRequest.PORTION_FULL
        elif start and end and start != end and portion != LeaveRequest.PORTION_FULL:
            self.add_error('portion', 'Nghỉ nhiều ngày phải chọn cả ngày. Nửa buổi chỉ dùng cho một ngày.')
        return cleaned


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = (
            'name', 'kind', 'start_time', 'end_time', 'break_start', 'break_end',
            'crosses_midnight', 'late_grace_minutes', 'early_grace_minutes',
            'saturday_start', 'saturday_end', 'is_active',
        )
        widgets = {
            'start_time': TimeInput(),
            'end_time': TimeInput(),
            'break_start': TimeInput(),
            'break_end': TimeInput(),
            'saturday_start': TimeInput(),
            'saturday_end': TimeInput(),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        crosses = cleaned.get('crosses_midnight')
        if start and end and not crosses and end <= start:
            self.add_error('end_time', 'Giờ ra phải sau giờ vào. Ca qua đêm thì bật ô Ca qua đêm.')
        break_start = cleaned.get('break_start')
        break_end = cleaned.get('break_end')
        if bool(break_start) != bool(break_end):
            self.add_error('break_end', 'Nhập cả giờ bắt đầu và giờ kết thúc nghỉ, hoặc để trống.')
        saturday_start = cleaned.get('saturday_start')
        saturday_end = cleaned.get('saturday_end')
        if saturday_start and saturday_end and saturday_end <= saturday_start:
            self.add_error('saturday_end', 'Giờ ra thứ 7 phải sau giờ vào.')
        return cleaned


class AssignmentForm(forms.Form):
    TARGET_DEPARTMENT = 'department'
    TARGET_DIVISION = 'division'
    TARGET_USER = 'user'
    target_type = forms.ChoiceField(
        label='Gán cho',
        choices=[
            (TARGET_DEPARTMENT, 'Phòng ban'),
            (TARGET_DIVISION, 'Bộ phận'),
            (TARGET_USER, 'Nhân viên'),
        ],
    )
    shift = forms.ModelChoiceField(label='Ca', queryset=Shift.objects.none())
    department = forms.ModelChoiceField(
        label='Phòng ban', queryset=Department.objects.none(), required=False,
    )
    division = forms.ModelChoiceField(
        label='Bộ phận', queryset=Division.objects.none(), required=False,
    )
    user = forms.ModelChoiceField(label='Nhân viên', queryset=User.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['shift'].queryset = Shift.objects.filter(is_active=True)
        self.fields['department'].queryset = Department.objects.filter(is_active=True).order_by('name')
        self.fields['division'].queryset = Division.objects.filter(is_active=True).select_related('department')
        self.fields['user'].queryset = (
            User.objects.filter(is_active=True, profile__is_employed=True)
            .select_related('profile')
            .order_by('profile__full_name', 'username')
        )
        self.fields['user'].label_from_instance = _user_label
        self.fields['division'].label_from_instance = lambda obj: (
            f'{obj.department.name} — {obj.name}' if obj.department_id else obj.name
        )

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get('target_type')
        if target == self.TARGET_DEPARTMENT and not cleaned.get('department'):
            self.add_error('department', 'Chọn phòng ban.')
        if target == self.TARGET_DIVISION and not cleaned.get('division'):
            self.add_error('division', 'Chọn bộ phận.')
        if target == self.TARGET_USER and not cleaned.get('user'):
            self.add_error('user', 'Chọn nhân viên.')
        return cleaned


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ('holiday_date', 'name')
        widgets = {'holiday_date': DateInput()}


class PolicyForm(forms.ModelForm):
    class Meta:
        model = AttendancePolicy
        fields = (
            'reminder_lead_minutes', 'annual_leave_days', 'leave_carry_max_days',
            'ot_weekday_rate', 'ot_sunday_rate', 'ot_holiday_rate',
        )


class SiteForm(forms.ModelForm):
    ip_text = forms.CharField(
        label='IP WiFi',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Mỗi dòng một IP công cộng hoặc dải CIDR. Khớp IP thì không cần định vị.',
    )

    class Meta:
        model = WorkSite
        fields = ('name', 'latitude', 'longitude', 'radius_m', 'is_active', 'note')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['ip_text'].initial = '\n'.join(
                self.instance.ips.order_by('cidr').values_list('cidr', flat=True),
            )

    def clean_latitude(self):
        value = self.cleaned_data['latitude']
        if value < -90 or value > 90:
            raise forms.ValidationError('Vĩ độ từ -90 đến 90.')
        return value

    def clean_longitude(self):
        value = self.cleaned_data['longitude']
        if value < -180 or value > 180:
            raise forms.ValidationError('Kinh độ từ -180 đến 180.')
        return value

    def clean_ip_text(self):
        import ipaddress

        lines = []
        for raw in (self.cleaned_data.get('ip_text') or '').splitlines():
            text = raw.strip()
            if not text:
                continue
            try:
                if '/' in text:
                    ipaddress.ip_network(text, strict=False)
                else:
                    ipaddress.ip_address(text)
            except ValueError:
                raise forms.ValidationError(f'IP không hợp lệ: {text}')
            if text not in lines:
                lines.append(text)
        return lines


def _user_label(user):
    profile = getattr(user, 'profile', None)
    name = getattr(profile, 'full_name', '') or user.username
    code = getattr(profile, 'employee_code', '') or ''
    return f'{code} · {name}' if code else name


class SalaryProfileForm(forms.ModelForm):
    class Meta:
        model = SalaryProfile
        fields = ('base_salary', 'meal_allowance', 'transport_allowance', 'phone_allowance')

    def clean(self):
        cleaned = super().clean()
        for name in ('base_salary', 'meal_allowance', 'transport_allowance', 'phone_allowance'):
            if cleaned.get(name) is not None and cleaned[name] < 0:
                self.add_error(name, 'Số tiền không được âm.')
        return cleaned


class PayAdjustmentForm(forms.ModelForm):
    class Meta:
        model = PayAdjustment
        fields = ('user', 'kind', 'amount', 'reason')

    def __init__(self, *args, users=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = users
        self.fields['user'].label_from_instance = _user_label
        self.fields['reason'].widget = forms.TextInput()
