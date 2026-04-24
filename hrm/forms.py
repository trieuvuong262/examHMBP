from django import forms

class CustomUserForm(forms.Form):
    POSITION_CHOICES = [
        ('', '-- Vui lòng chọn chức danh --'),
        ('Bác Sĩ', 'Bác Sĩ'),
        ('Điều Dưỡng', 'Điều Dưỡng'),
        ('Dược Sĩ', 'Dược Sĩ'),
        ('Kỹ Thuật viên', 'Kỹ Thuật viên'),
        ('Khối Hỗ trợ', 'Khối Hỗ trợ'),
    ]

    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'an.nguyen@hoanmy.com'}))
    password = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '••••••••'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'an.nguyen@hoanmy.com'}))
    full_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nguyễn Văn An'}))
    position = forms.ChoiceField(choices=POSITION_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))