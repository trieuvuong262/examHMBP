from django import forms

from .models import Exam, Question, Choice
from django.forms import inlineformset_factory
from .models import Exam, User

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['title', 'description', 'start_time', 'end_time', 'duration_minutes', 'is_active', 'assigned_users']
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
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_users': forms.SelectMultiple(attrs={'class': 'form-select select2-user'}),
        }

# assessment/forms.py

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_qs = User.objects.all().select_related('profile')
        self.fields['assigned_users'].queryset = user_qs
        
        # Hàm hiển thị an toàn: Nếu không có profile thì hiện Username
        def get_user_label(obj):
            try:
                return f"{obj.profile.full_name} ({obj.profile.position})"
            except:
                return f"{obj.username} (Chưa cập nhật Profile)"
                
        self.fields['assigned_users'].label_from_instance = get_user_label
        
        self.fields['start_time'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_time'].input_formats = ['%Y-%m-%dT%H:%M']
class QuestionForm(forms.ModelForm):
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

ChoiceFormSet = inlineformset_factory(
    Question, Choice,
    fields=('text', 'is_correct'),
    extra=4,
    can_delete=True,
    widgets={
        'text': forms.TextInput(attrs={'class': 'form-control'}),
        'is_correct': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    }
)
# assessment/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import Profile

class UserForm(forms.ModelForm):
    # Định nghĩa danh sách chức danh cố định
    POSITION_CHOICES = [
        ('', '--- Chọn chức danh ---'),
        ('Bác Sĩ', 'Bác Sĩ'),
        ('Điều Dưỡng', 'Điều Dưỡng'),
        ('Dược Sĩ', 'Dược Sĩ'),
        ('Kỹ Thuật viên', 'Kỹ Thuật viên'),
        ('Khối Hỗ trợ', 'Khối Hỗ trợ'),
    ]

    full_name = forms.CharField(
        label="Họ và tên", 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập họ và tên...'})
    )
    
    # Chuyển position từ TextInput sang ChoiceField (Select)
    position = forms.ChoiceField(
        label="Chức danh",
        choices=POSITION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}) # Dùng form-select của Bootstrap
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
                self.fields['position'].initial = profile.position
            except Profile.DoesNotExist:
                pass

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = Profile.objects.get_or_create(user=user)
            profile.full_name = self.cleaned_data['full_name']
            profile.position = self.cleaned_data['position']
            profile.save()
        return user
    
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['full_name', 'position']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),
        }