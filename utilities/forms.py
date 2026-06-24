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
    remind_at = forms.DateTimeField(
        label='Thời gian nhắc',
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            },
            format='%Y-%m-%dT%H:%M',
        ),
    )

    class Meta:
        from utilities.models import ScheduleReminder

        model = ScheduleReminder
        fields = ('title', 'body', 'remind_at')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Họp ban sản xuất',
                'maxlength': 120,
            }),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Nội dung hiển thị trong thông báo push…',
            }),
        }

    def clean_remind_at(self):
        value = self.cleaned_data.get('remind_at')
        if value is None:
            return value
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        if value <= timezone.now():
            raise ValidationError('Chọn thời gian trong tương lai.')
        return value
