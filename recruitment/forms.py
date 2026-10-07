from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from hrm.choices import GENDER_FORM_CHOICES
from hrm.models import Department
from hrm.permissions import ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR, ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER

from .models import (
    CANDIDATE_FILE_TYPES,
    Candidate,
    CandidateFileKind,
    CandidateReview,
    CandidateSource,
    Interview,
    InterviewLocation,
    JobPosting,
)

MIN_WORKING_AGE = 15
# Người phỏng vấn: từ Tổ trưởng trở lên (vai trò chính hoặc kiêm nhiệm đang hiệu lực).
INTERVIEWER_ROLES = (ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR)


def _ctl(extra: str = '') -> dict:
    return {'class': f'form-control {extra}'.strip()}


def _gender_field(required=True):
    return forms.ChoiceField(
        label='Giới tính', choices=GENDER_FORM_CHOICES, required=required,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


def _dob_field(required=True):
    return forms.DateField(
        label='Ngày sinh', required=required,
        widget=forms.DateInput(
            attrs={**_ctl('jp-date-vn'), 'type': 'date', 'placeholder': 'dd/mm/yyyy'}, format='%Y-%m-%d',
        ),
    )


def _validate_dob(value):
    if not value:
        return value
    today = timezone.localdate()
    if value > today:
        raise forms.ValidationError('Ngày sinh không được ở tương lai.')
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < MIN_WORKING_AGE:
        raise forms.ValidationError(f'Ứng viên phải đủ {MIN_WORKING_AGE} tuổi.')
    if value.year < 1940:
        raise forms.ValidationError('Ngày sinh không hợp lệ.')
    return value


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Nhiều file một lần chọn; kiểm tra nội dung (magic bytes, virus) ở services."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('widget', MultipleFileInput(attrs={
            **_ctl(), 'accept': ','.join(CANDIDATE_FILE_TYPES),
        }))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        items = [d for d in (data if isinstance(data, (list, tuple)) else [data]) if d]
        if not items:
            if self.required:
                raise forms.ValidationError('Chọn ít nhất một file.')
            return []
        single = super().clean
        return [single(item, initial) for item in items]


class VndField(forms.IntegerField):
    """Số tiền nhập dạng «8.000.000» — bỏ mọi ký tự không phải số trước khi kiểm tra."""

    widget = forms.TextInput

    def __init__(self, **kwargs):
        kwargs.setdefault('min_value', 0)
        kwargs.setdefault('max_value', 2_000_000_000)
        super().__init__(**kwargs)

    def widget_attrs(self, widget):
        return {**_ctl(), 'inputmode': 'numeric', 'autocomplete': 'off', 'data-rc-money': '1'}

    def prepare_value(self, value):
        return f'{value:,}'.replace(',', '.') if isinstance(value, int) else value

    def to_python(self, value):
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        return super().to_python(digits)


class JobPostingForm(forms.ModelForm):
    salary_min = VndField(label='Lương từ', required=False)
    salary_max = VndField(label='Lương đến', required=False)

    class Meta:
        model = JobPosting
        fields = [
            'title', 'target_department', 'target_division', 'position', 'quantity', 'deadline',
            'salary_min', 'salary_max', 'salary_negotiable', 'description', 'requirements',
        ]
        widgets = {
            'title': forms.TextInput(attrs={**_ctl(), 'placeholder': 'VD: Công nhân may chuyền 2'}),
            'target_department': forms.Select(attrs={'class': 'form-select'}),
            'target_division': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={**_ctl(), 'min': 1}),
            'salary_negotiable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'deadline': forms.DateInput(
                attrs={**_ctl('jp-date-vn'), 'type': 'date', 'placeholder': 'dd/mm/yyyy'}, format='%Y-%m-%d',
            ),
            'description': forms.Textarea(attrs={
                **_ctl(), 'rows': 5, 'placeholder': 'Công việc chính, ca làm, nơi làm việc…',
            }),
            'requirements': forms.Textarea(attrs={
                **_ctl(), 'rows': 4, 'placeholder': 'Kinh nghiệm, tay nghề, độ tuổi, sức khỏe…',
            }),
        }
        labels = {'title': 'Tên vị trí', 'quantity': 'Số lượng cần tuyển', 'salary_negotiable': 'Thỏa thuận'}

    def __init__(self, *args, scope=None, **kwargs):
        super().__init__(*args, **kwargs)
        from hrm.models import Division

        self.scope = scope
        self.fields['position'].choices = [('', '— Chọn chức danh —')] + list(JobPosting.POSITION_CHOICES)
        departments = Department.objects.filter(is_active=True).order_by('sort_order', 'name')
        divisions = Division.objects.filter(is_active=True, department__isnull=False).select_related('department')
        if scope is not None and not scope.all:
            # Chỉ tạo / chuyển vị trí trong phạm vi mình phụ trách.
            div_dept_ids = set(
                Division.objects.filter(pk__in=scope.division_ids).values_list('department_id', flat=True)
            )
            departments = departments.filter(pk__in=scope.department_ids | div_dept_ids)
            divisions = divisions.filter(
                Q(department_id__in=scope.department_ids) | Q(pk__in=scope.division_ids)
            )
        self.fields['target_department'].queryset = departments
        self.fields['target_department'].required = True
        self.fields['target_department'].empty_label = '— Chọn phòng ban —'
        self.fields['target_division'].queryset = divisions.order_by('department__sort_order', 'sort_order', 'name')
        self.fields['target_division'].empty_label = '— Cả phòng ban —'
        self.fields['target_division'].label_from_instance = lambda d: f'{d.department.name} · {d.name}'

    def clean(self):
        cleaned = super().clean()
        lo, hi = cleaned.get('salary_min'), cleaned.get('salary_max')
        if lo and hi and hi < lo:
            self.add_error('salary_max', 'Lương đến phải lớn hơn hoặc bằng lương từ.')
        dept, div = cleaned.get('target_department'), cleaned.get('target_division')
        if dept and div and div.department_id != dept.pk:
            self.add_error('target_division', 'Bộ phận không thuộc phòng ban đã chọn.')
            return cleaned
        if dept and self.scope is not None:
            probe = JobPosting(target_department=dept, target_division=div)
            if not self.scope.contains(probe):
                self.add_error(
                    'target_division' if not div else 'target_department',
                    'Ngoài phạm vi bạn phụ trách — chọn bộ phận bạn quản lý.',
                )
        return cleaned
        self.fields['deadline'].required = True
        self.fields['description'].required = True

    def clean_deadline(self):
        deadline = self.cleaned_data.get('deadline')
        is_new_or_changed = not self.instance.pk or 'deadline' in self.changed_data
        if deadline and is_new_or_changed and deadline < timezone.localdate():
            raise forms.ValidationError('Hạn nộp không được ở quá khứ.')
        return deadline


class CandidateForm(forms.Form):
    job_posting = forms.ModelChoiceField(
        label='Vị trí ứng tuyển', queryset=JobPosting.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='— Chọn vị trí đang tuyển —',
    )
    source = forms.ChoiceField(label='Nguồn hồ sơ', widget=forms.Select(attrs={'class': 'form-select'}))
    full_name = forms.CharField(
        label='Họ và tên', max_length=255, widget=forms.TextInput(attrs={**_ctl(), 'autocomplete': 'off'}),
    )
    gender = _gender_field()
    date_of_birth = _dob_field()
    phone = forms.CharField(
        label='Số điện thoại', max_length=20,
        widget=forms.TextInput(attrs={**_ctl(), 'inputmode': 'tel', 'autocomplete': 'off'}),
    )
    email = forms.EmailField(
        label='Email', required=False, widget=forms.EmailInput(attrs={**_ctl(), 'autocomplete': 'off'}),
    )
    files = MultipleFileField(label='CV / hồ sơ (PDF, Word, ảnh)')
    note = forms.CharField(label='Ghi chú', required=False, widget=forms.Textarea(attrs={**_ctl(), 'rows': 3}))

    def __init__(self, *args, jobs=None, referral=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['job_posting'].queryset = jobs if jobs is not None else JobPosting.objects.none()
        if referral:
            # Quản lý đề xuất — nguồn cố định; HR bổ sung giới tính / ngày sinh khi onboard.
            del self.fields['source']
            self.fields['gender'].required = False
            self.fields['date_of_birth'].required = False
        else:
            # Nguồn hệ thống (Quản lý đề xuất) chỉ gán tự động, HR không chọn.
            self.fields['source'].choices = [('', '— Chọn nguồn hồ sơ —')] + list(
                CandidateSource.objects.filter(is_active=True, is_system=False).values_list('code', 'name')
            )

    def clean_date_of_birth(self):
        return _validate_dob(self.cleaned_data.get('date_of_birth'))


class CandidateFileForm(forms.Form):
    kind = forms.ChoiceField(label='Loại', widget=forms.Select(attrs={'class': 'form-select'}))
    files = MultipleFileField(label='Chọn file', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].choices = list(
            CandidateFileKind.objects.filter(is_active=True).values_list('code', 'name')
        )


class TransitionForm(forms.Form):
    to_status = forms.ChoiceField(choices=Candidate.STATUS_CHOICES, widget=forms.HiddenInput)
    reason = forms.CharField(label='Lý do', required=False, widget=forms.Textarea(attrs={**_ctl(), 'rows': 3}))
    interview_time = forms.DateTimeField(
        label='Bắt đầu', required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={**_ctl(), 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    interview_end = forms.DateTimeField(
        label='Kết thúc', required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={**_ctl(), 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    location = forms.CharField(label='Địa điểm', required=False, max_length=255, widget=forms.TextInput(attrs=_ctl()))
    interviewers = forms.ModelMultipleChoiceField(
        label='Người phỏng vấn', required=False, queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interviewers'].queryset = (
            User.objects.filter(is_active=True, profile__is_employed=True)
            .filter(
                Q(profile__role__in=INTERVIEWER_ROLES)
                | Q(profile__concurrent_positions__is_active=True,
                    profile__concurrent_positions__role__in=INTERVIEWER_ROLES)
            )
            .distinct()
            .select_related('profile', 'profile__department').order_by('profile__full_name', 'username')
        )
        self.fields['interviewers'].label_from_instance = (
            lambda u: getattr(getattr(u, 'profile', None), 'full_name', '') or u.username
        )


class InterviewResultForm(forms.Form):
    result = forms.ChoiceField(
        label='Kết quả',
        choices=[c for c in Interview.RESULT_CHOICES if c[0] != Interview.RESULT_PENDING],
        widget=forms.RadioSelect,
    )
    notes = forms.CharField(label='Nhận xét', required=False, widget=forms.Textarea(attrs={**_ctl(), 'rows': 3}))


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(
        label='Kết luận', widget=forms.RadioSelect,
        choices=[c for c in CandidateReview.DECISION_CHOICES if c[0] in CandidateReview.ACTIVE_DECISIONS],
    )
    rating = forms.TypedChoiceField(
        label='Điểm hồ sơ', required=False, coerce=int, empty_value=None,
        choices=[('', '—')] + [(i, f'{i}/5') for i in range(1, 6)],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    comment = forms.CharField(label='Nhận xét', required=False, widget=forms.Textarea(attrs={**_ctl(), 'rows': 3}))


class OnboardForm(forms.Form):
    """Xác nhận thông tin tài khoản — điền sẵn từ hồ sơ ứng viên, HR sửa / bổ sung trước khi tạo."""

    email = forms.EmailField(label='Email tài khoản', widget=forms.EmailInput(attrs={**_ctl(), 'autocomplete': 'off'}))
    gender = _gender_field()
    date_of_birth = _dob_field()
    join_date = forms.DateField(
        label='Ngày nhận việc', initial=timezone.localdate,
        widget=forms.DateInput(attrs={**_ctl('jp-date-vn'), 'type': 'date'}, format='%Y-%m-%d'),
    )

    def __init__(self, *args, candidate=None, suggested_email='', **kwargs):
        if candidate is not None and not kwargs.get('data') and not args:
            kwargs.setdefault('initial', {
                'email': candidate.email or suggested_email,
                'gender': candidate.gender,
                'date_of_birth': candidate.date_of_birth,
            })
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(f'Email {email} đã thuộc một tài khoản khác.')
        return email

    def clean_date_of_birth(self):
        return _validate_dob(self.cleaned_data.get('date_of_birth'))


# ---------------------------------------------------------------- Thiết lập

class _OptionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sort_order'].required = False
        self.fields['sort_order'].help_text = ''
        if not self.instance.pk:
            self.initial.pop('sort_order', None)
            self.fields['sort_order'].initial = None
            self.fields['sort_order'].widget.attrs['placeholder'] = 'Cuối'

    def clean_name(self):
        name = ' '.join((self.cleaned_data.get('name') or '').split())
        if not name:
            raise forms.ValidationError('Nhập tên.')
        dup = type(self.instance).objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError(f'«{name}» đã có trong danh mục.')
        return name


_NAME = forms.TextInput(attrs={**_ctl(), 'maxlength': 120, 'autocomplete': 'off'})
_ORDER = forms.NumberInput(attrs={**_ctl(), 'min': 0, 'style': 'max-width: 6rem;'})


class InterviewLocationForm(_OptionForm):
    class Meta:
        model = InterviewLocation
        fields = ['name', 'note', 'sort_order']
        labels = {'name': 'Tên địa điểm'}
        widgets = {'name': _NAME, 'note': forms.TextInput(attrs=_ctl()), 'sort_order': _ORDER}


class CandidateSourceForm(_OptionForm):
    class Meta:
        model = CandidateSource
        fields = ['name', 'sort_order']
        labels = {'name': 'Tên nguồn'}
        widgets = {'name': _NAME, 'sort_order': _ORDER}


class CandidateFileKindForm(_OptionForm):
    class Meta:
        model = CandidateFileKind
        fields = ['name', 'is_cv', 'sort_order']
        labels = {'name': 'Tên loại hồ sơ', 'is_cv': 'Là CV (dùng cho nút «Xem CV»)'}
        widgets = {'name': _NAME, 'is_cv': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                   'sort_order': _ORDER}
