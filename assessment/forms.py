from django import forms
from django.db.models import Q
from .models import Exam, Question, Choice, User, ExamQuestion, CertificateTemplate, CertificateTemplateDescription
from django.forms import inlineformset_factory
from django.contrib.auth.models import User
from hrm.models import Profile

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            'title', 'description', 'start_time', 'end_time', 'duration_minutes',
            'pass_score', 'certificate_template', 'issue_certificate', 'is_active', 'assigned_users',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: Đánh giá kỹ thuật tiêm tĩnh mạch'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'end_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'pass_score': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0', 'max': '100'}),
            'certificate_template': forms.Select(attrs={'class': 'form-select'}),
            'issue_certificate': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_users': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from hrm.user_search import exclude_hidden_hrm_users

        user_filter = Q(is_active=True)
        if self.instance.pk:
            user_filter |= Q(pk__in=self.instance.assigned_users.values('pk'))
        self.fields['assigned_users'].queryset = (
            exclude_hidden_hrm_users(User.objects.filter(user_filter))
            .select_related('profile', 'profile__department', 'profile__division')
            .order_by('profile__full_name', 'username')
        )
        
        def get_user_label(obj):
            try:
                return f"{obj.profile.full_name} ({obj.profile.job_position})"
            except:
                return f"{obj.username} (Chưa cập nhật Profile)"
                
        self.fields['assigned_users'].label_from_instance = get_user_label
        
        self.fields['start_time'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_time'].input_formats = ['%Y-%m-%dT%H:%M']
        if 'certificate_template' in self.fields:
            self.fields['certificate_template'].queryset = CertificateTemplate.objects.filter(
                is_active=True,
            ).order_by('-is_default', 'name')
            self.fields['certificate_template'].required = False
            self.fields['certificate_template'].empty_label = '— Mẫu mặc định —'


class CertificateTemplateForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplate
        fields = [
            'name', 'heading', 'ribbon_text', 'presented_label', 'body_text', 'thank_you_text',
            'company_name', 'tax_code',
            'hr_signer_name', 'hr_signer_title', 'hr_signature',
            'director_signer_name', 'director_signer_title', 'director_signature',
            'issuer_name', 'issuer_title', 'seal_text', 'is_default', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'heading': forms.TextInput(attrs={'class': 'form-control'}),
            'ribbon_text': forms.TextInput(attrs={'class': 'form-control'}),
            'presented_label': forms.TextInput(attrs={'class': 'form-control'}),
            'body_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'thank_you_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_code': forms.TextInput(attrs={'class': 'form-control'}),
            'hr_signer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'hr_signer_title': forms.TextInput(attrs={'class': 'form-control'}),
            'hr_signature': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/png,image/jpeg'}),
            'director_signer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'director_signer_title': forms.TextInput(attrs={'class': 'form-control'}),
            'director_signature': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/png,image/jpeg'}),
            'issuer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'issuer_title': forms.TextInput(attrs={'class': 'form-control'}),
            'seal_text': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CertificateTemplateDescriptionForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplateDescription
        fields = ['course', 'exam', 'description']
        widgets = {
            'course': forms.Select(attrs={'class': 'form-select'}),
            'exam': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Mô tả hiện trên chứng chỉ của khóa/kỳ thi này'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from training.models import Course

        self.fields['course'].queryset = Course.objects.filter(is_active=True).order_by('title')
        self.fields['course'].required = False
        self.fields['course'].empty_label = '— Chọn khóa học —'
        self.fields['exam'].queryset = Exam.objects.filter(is_active=True, retry_of__isnull=True).order_by('title')
        self.fields['exam'].required = False
        self.fields['exam'].empty_label = '— Chọn kỳ thi —'
        self.fields['description'].required = False

    def clean(self):
        cleaned = super().clean()
        desc = (cleaned.get('description') or '').strip()
        course = cleaned.get('course')
        exam = cleaned.get('exam')
        if self.cleaned_data.get('DELETE'):
            return cleaned
        if not desc and not course and not exam:
            return cleaned
        if desc and not course and not exam:
            raise forms.ValidationError('Chọn khóa học hoặc kỳ thi cho mô tả này.')
        if (course or exam) and not desc:
            raise forms.ValidationError('Nhập mô tả khóa học.')
        cleaned['description'] = desc
        return cleaned


class CertificateDescriptionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen_courses = set()
        seen_exams = set()
        for form in self.forms:
            data = getattr(form, 'cleaned_data', None)
            if not data or data.get('DELETE'):
                continue
            course = data.get('course')
            exam = data.get('exam')
            if course:
                if course.pk in seen_courses:
                    raise forms.ValidationError('Mỗi khóa học chỉ được gắn một mô tả.')
                seen_courses.add(course.pk)
            if exam:
                if exam.pk in seen_exams:
                    raise forms.ValidationError('Mỗi kỳ thi chỉ được gắn một mô tả.')
                seen_exams.add(exam.pk)


CertificateDescriptionFormSetFactory = inlineformset_factory(
    CertificateTemplate,
    CertificateTemplateDescription,
    form=CertificateTemplateDescriptionForm,
    formset=CertificateDescriptionFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
)


class QuestionForm(forms.ModelForm):
    sort_order = forms.IntegerField(
        min_value=1,
        required=True,
        label='STT trong đề',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'step': 1,
            'placeholder': 'Ví dụ: 1',
        }),
    )

    class Meta:
        model = Question
        fields = ['competency', 'content', 'q_type', 'points', 'image_hint']
        widgets = {
            'competency': forms.Select(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'q_type': forms.Select(attrs={'class': 'form-control', 'id': 'id_q_type'}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0', 'max': '100'}),
            'image_hint': forms.FileInput(attrs={'class': 'form-control'}),
        }

def save_choice_formset_in_order(formset, question):
    """Lưu đáp án theo thứ tự dòng trong form."""
    order = 1
    for form in formset.forms:
        if not form.cleaned_data:
            continue
        if form.cleaned_data.get('DELETE'):
            if form.instance.pk:
                form.instance.delete()
            continue
        choice = form.save(commit=False)
        choice.question = question
        choice.sort_order = order
        choice.save()
        order += 1


class OrderedChoiceFormSet(forms.BaseInlineFormSet):
    def get_queryset(self):
        return super().get_queryset().order_by('sort_order', 'id')


ChoiceFormSet = inlineformset_factory(
    Question, Choice,
    fields=('text', 'is_correct'),
    extra=4,
    can_delete=True,
    formset=OrderedChoiceFormSet,
    widgets={
        'text': forms.TextInput(attrs={'class': 'form-control'}),
        'is_correct': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    }
)


class UserForm(forms.ModelForm):
    full_name = forms.CharField(
        label="Họ và tên", 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập họ và tên...'})
    )
    
    job_position = forms.CharField(
        label="Vị trí",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Công nhân may'}),
    )

    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                profile = self.instance.profile
                self.fields['full_name'].initial = profile.full_name
                self.fields['job_position'].initial = profile.job_position
            except Profile.DoesNotExist:
                pass

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = Profile.objects.get_or_create(user=user)
            profile.full_name = self.cleaned_data['full_name']
            profile.job_position = (self.cleaned_data.get('job_position') or '').strip()
            profile.save()
        return user
    
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['full_name', 'job_position']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'job_position': forms.TextInput(attrs={'class': 'form-control'}),
        }