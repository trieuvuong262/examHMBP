from django import forms
from .models import Exam, Question, Choice, User, ExamQuestion, CertificateTemplate
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
            'pass_score': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'certificate_template': forms.Select(attrs={'class': 'form-select'}),
            'issue_certificate': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_users': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_qs = User.objects.all().select_related('profile')
        self.fields['assigned_users'].queryset = user_qs
        
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
            'name', 'heading', 'ribbon_text', 'presented_label', 'body_text',
            'issuer_name', 'issuer_title', 'seal_text', 'is_default', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'heading': forms.TextInput(attrs={'class': 'form-control'}),
            'ribbon_text': forms.TextInput(attrs={'class': 'form-control'}),
            'presented_label': forms.TextInput(attrs={'class': 'form-control'}),
            'body_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'issuer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'issuer_title': forms.TextInput(attrs={'class': 'form-control'}),
            'seal_text': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


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
            'points': forms.NumberInput(attrs={'class': 'form-control'}),
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