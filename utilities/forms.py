from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from utilities.meal_rules import is_meal_order_window_open
from utilities.models import MealDish, MealOrder, MealOrderSettings, SalaryAdvanceRequest
from utilities.salary_rules import MAX_SALARY_ADVANCE, is_salary_advance_open


class MealDishForm(forms.ModelForm):
    class Meta:
        model = MealDish
        fields = ('name', 'sort_order', 'is_active')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MealOrderForm(forms.ModelForm):
    class Meta:
        model = MealOrder
        fields = ('dish', 'note')
        widgets = {
            'dish': forms.RadioSelect,
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ghi chú (tuỳ chọn)'}),
        }

    def __init__(self, *args, meal_date=None, offered_dish_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.meal_date = meal_date
        qs = MealDish.objects.filter(is_active=True)
        if offered_dish_ids is not None:
            qs = qs.filter(pk__in=offered_dish_ids)
        self.fields['dish'].queryset = qs.order_by('sort_order', 'name')

    def clean(self):
        cleaned = super().clean()
        if not self.meal_date:
            raise ValidationError('Không xác định được ngày đặt cơm.')
        if not is_meal_order_window_open(self.meal_date):
            raise ValidationError('Ngoài khung giờ đặt cơm (16h–20h ngày hôm trước).')
        return cleaned


class MealDayMenuForm(forms.Form):
    meal_date = forms.DateField(
        label='Ngày ăn',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )


class SalaryAdvanceForm(forms.ModelForm):
    class Meta:
        model = SalaryAdvanceRequest
        fields = ('amount', 'note')
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1000,
                'max': int(MAX_SALARY_ADVANCE),
                'step': 1000,
                'placeholder': 'Số tiền (VNĐ)',
            }),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lý do (tuỳ chọn)'}),
        }

    def __init__(self, *args, employee=None, request_month=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.request_month = request_month

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None:
            return amount
        if amount > MAX_SALARY_ADVANCE:
            raise ValidationError(f'Số tiền tối đa {MAX_SALARY_ADVANCE:,.0f}đ.')
        if amount <= 0:
            raise ValidationError('Số tiền phải lớn hơn 0.')
        return amount

    def clean(self):
        cleaned = super().clean()
        if not is_salary_advance_open():
            raise ValidationError('Ứng lương chỉ mở vào ngày 18 và 19 hàng tháng.')
        employee = self.employee or getattr(self.instance, 'employee', None)
        month = self.request_month or getattr(self.instance, 'request_month', None)
        if employee and month:
            from utilities.models import normalize_request_month
            month = normalize_request_month(month)
            qs = SalaryAdvanceRequest.objects.filter(employee=employee, request_month=month)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('Mỗi tài khoản chỉ được ứng lương 1 lần trong một tháng.')
        return cleaned


class MealOrderSettingsForm(forms.ModelForm):
    class Meta:
        model = MealOrderSettings
        fields = ('order_start_time', 'order_end_time', 'order_days_before')
        widgets = {
            'order_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'order_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'order_days_before': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 7,
                'step': 1,
            }),
        }
        labels = {
            'order_start_time': 'Giờ bắt đầu',
            'order_end_time': 'Giờ kết thúc',
            'order_days_before': 'Đặt trước ngày ăn',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('order_start_time')
        end = cleaned.get('order_end_time')
        if start and end and end <= start:
            raise ValidationError('Giờ kết thúc phải sau giờ bắt đầu.')
        return cleaned


class MealStatsFilterForm(forms.Form):
    PERIOD_WEEK = 'week'
    PERIOD_MONTH = 'month'
    PERIOD_CHOICES = (
        (PERIOD_WEEK, 'Theo tuần'),
        (PERIOD_MONTH, 'Theo tháng'),
    )
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        initial=PERIOD_WEEK,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    anchor_date = forms.DateField(
        label='Tham chiếu',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )


class ScheduleReminderForm(forms.ModelForm):
    weekdays = forms.MultipleChoiceField(
        label='Các thứ trong tuần',
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'jp-schedule-weekday-check'}),
    )
    once_date = forms.DateField(
        label='Ngày nhắc',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    remind_time = forms.TimeField(
        label='Giờ nhắc',
        widget=forms.TimeInput(
            attrs={'class': 'form-control', 'type': 'time'},
            format='%H:%M',
        ),
        input_formats=['%H:%M', '%H:%M:%S'],
    )

    class Meta:
        from utilities.models import ScheduleReminder

        model = ScheduleReminder
        fields = ('title', 'body', 'repeat_mode', 'weekdays', 'once_date', 'remind_time')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 120,
            }),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
            }),
            'repeat_mode': forms.RadioSelect(attrs={'class': 'jp-schedule-repeat-radio'}),
        }

    def __init__(self, *args, **kwargs):
        from utilities.schedule_reminder_logic import REPEAT_MODE_CHOICES, WEEKDAY_CHOICES

        super().__init__(*args, **kwargs)
        self.fields['repeat_mode'].choices = REPEAT_MODE_CHOICES
        self.fields['weekdays'].choices = WEEKDAY_CHOICES
        if self.instance and self.instance.pk:
            self.initial['weekdays'] = [str(d) for d in self.instance.weekday_list()]

    def clean_weekdays(self):
        from utilities.schedule_reminder_logic import normalize_weekdays

        return normalize_weekdays(self.cleaned_data.get('weekdays') or [])

    def clean(self):
        from utilities.models import ScheduleReminder
        from utilities.schedule_reminder_logic import validate_once_datetime

        cleaned = super().clean()
        repeat_mode = cleaned.get('repeat_mode')
        weekdays = cleaned.get('weekdays') or []
        once_date = cleaned.get('once_date')
        remind_time = cleaned.get('remind_time')

        if repeat_mode == ScheduleReminder.REPEAT_WEEKLY:
            if not weekdays:
                self.add_error('weekdays', 'Chọn ít nhất một thứ trong tuần.')
            cleaned['once_date'] = None
        elif repeat_mode == ScheduleReminder.REPEAT_ONCE:
            if not once_date:
                self.add_error('once_date', 'Chọn ngày nhắc.')
            elif remind_time:
                from django.core.exceptions import ValidationError

                try:
                    validate_once_datetime(once_date, remind_time)
                except ValidationError as exc:
                    self.add_error('once_date', exc)
            if once_date:
                cleaned['weekdays'] = [once_date.isoweekday()]
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.weekdays = self.cleaned_data.get('weekdays') or []
        if commit:
            instance.save()
        return instance
