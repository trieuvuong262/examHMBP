from django import forms
from django.contrib.auth.models import User
from .models import Profile

class CustomUserForm(forms.Form):
    POSITION_CHOICES = [
        ('', '-- Vui lòng chọn chức danh --'),
        ('Bác Sĩ', 'Bác Sĩ'),
        ('Điều Dưỡng', 'Điều Dưỡng'),
        ('Dược Sĩ', 'Dược Sĩ'),
        ('Kỹ Thuật viên', 'Kỹ Thuật viên'),
        ('Khối Hỗ trợ', 'Khối Hỗ trợ'),
    ]

    # Tài khoản
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'an.nguyen@hoanmy.com'}))
    password = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'an.nguyen@hoanmy.com'}))
    
    # Thông tin cá nhân
    full_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nguyễn Văn An'}))
    position = forms.ChoiceField(choices=POSITION_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    
    # --- PHÂN QUYỀN MỚI ---
    role = forms.ChoiceField(
        choices=Profile.ROLE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='EMPLOYEE'
    )
    
    # Danh sách nhân viên dưới quyền (Dành cho HOD)
    subordinates = forms.ModelMultipleChoiceField(
        queryset=User.objects.all().order_by('first_name'),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select select2-multiple', # Thêm class để dễ gọi trong JS
        }),
        label="Nhân viên dưới quyền"
    )

    def __init__(self, *args, **kwargs):
        # Lấy instance user nếu đang trong chế độ Edit
        self.user_id = kwargs.pop('user_id', None)
        super().__init__(*args, **kwargs)
        
        # Nếu đang edit, loại bỏ chính user đó ra khỏi danh sách chọn cấp dưới (không thể quản lý chính mình)
        if self.user_id:
            self.fields['subordinates'].queryset = User.objects.exclude(id=self.user_id).order_by('first_name')
        
        # Tùy chỉnh hiển thị tên trong danh sách subordinates
        self.fields['subordinates'].label_from_instance = lambda obj: f"{obj.profile.full_name if hasattr(obj, 'profile') else obj.username} ({obj.username})"

    def clean_username(self):
        username = self.cleaned_data.get('username')
        qs = User.objects.filter(username=username)
        if self.user_id:
            # "Nè DB, tìm đứa nào trùng tên luu.dao nhưng TRỪ thằng có ID này ra nha"
            qs = qs.exclude(id=self.user_id) 
        if qs.exists():
            raise forms.ValidationError("Tên đăng nhập này đã tồn tại!")
        return username